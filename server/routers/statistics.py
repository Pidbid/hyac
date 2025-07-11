# routers/services/statistics.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from models.applications_model import Application
from models.common_model import BaseResponse
from models.functions_model import Function
from models.statistics_model import (
    FunctionMetric,
    CallStatus,
    StatisticsSummary,
    FunctionStats,
    RequestStats,
    DatabaseStats,
    StorageStats,
    CollectionStats,
    FunctionStatsOther,
    FunctionRequestStats,
)
from core.jwt_auth import get_current_user
from core.database_dynamic import dynamic_db

router = APIRouter(
    prefix="/statistics",
    tags=["Statistics"],
    responses={404: {"description": "Not found"}},
)


class StatisticsRequest(BaseModel):
    appId: str


@router.post("/summary", response_model=BaseResponse)
async def get_statistics_summary(
    data: StatisticsRequest,
    current_user=Depends(get_current_user),
):
    """
    Get a structured statistics summary for a given application.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        return BaseResponse(code=404, msg="Application not found")

    # --- Function Statistics ---
    function_count = await Function.find(Function.app_id == app.app_id).count()

    requests_pipeline = [
        {"$match": {"app_id": app.app_id}},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }
        },
    ]
    requests_result = await FunctionMetric.aggregate(requests_pipeline).to_list()

    total_calls = 0
    success_calls = 0
    error_calls = 0
    for res in requests_result:
        if res["_id"] == CallStatus.SUCCESS:
            success_calls = res["count"]
        elif res["_id"] == CallStatus.ERROR:
            error_calls = res["count"]
    total_calls = success_calls + error_calls

    # last 24 hours function request count
    last_24_hours_request = 0
    time_ago = datetime.now() - timedelta(days=-1)
    pipeline = [
        {
            "$match": {
                "app_id": app.app_id,
                "timestamp": {"$gte": time_ago},
            }
        },
        {
            "$group": {
                "_id": "$function_id",
                "count": {"$sum": 1},
            }
        },
        # {"$sort": {"_id": 1}},
    ]
    function_request_result = await FunctionMetric.aggregate(pipeline).to_list()
    print(function_request_result)
    if function_request_result:
        last_24_hours_request = function_request_result[0]["count"]
    pipeline = [
        {
            "$match": {
                "app_id": data.appId,
                "timestamp": {
                    "$gte": time_ago,
                },
            }
        },
        {
            "$group": {
                "_id": {"function_id": "$function_id", "app_id": "$app_id"},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"count": -1}},  # 降序排序
        {
            "$project": {
                "_id": 0,
                "function_id": "$_id.function_id",
                "app_id": "$_id.app_id",
                "count": "$count",
            }
        },
    ]

    function_request_result = await FunctionMetric.aggregate(pipeline).to_list()
    function_request_sort = []
    print(function_request_result)
    if function_request_result:
        function_request_sort = [
            FunctionRequestStats(
                function_name=i["function_name"], request_count=i["count"]
            )
            for i in function_request_result
        ]
    function_stats = FunctionStats(
        count=function_count,
        requests=RequestStats(
            total=total_calls, success=success_calls, error=error_calls
        ),
        other=FunctionStatsOther(
            last_24_hours=last_24_hours_request, request_sort=function_request_sort
        ),
    )

    # --- Database Statistics ---
    db = dynamic_db.app_db(data.appId)
    collection_names = await db.list_collection_names()
    db_stats = DatabaseStats(count=len(collection_names), collections=[])
    for name in collection_names:
        count = await db[name].count_documents({})
        db_stats.collections.append(CollectionStats(name=name, count=count))

    # --- Storage Statistics (Mocked) ---
    # In a real scenario, this would be calculated based on actual storage usage.
    storage_stats = StorageStats(total_usage_mb=952.7)

    summary = StatisticsSummary(
        functions=function_stats,
        database=db_stats,
        storage=storage_stats,
    )

    return BaseResponse(code=0, msg="Success", data=summary)


class FunctionRequestsResponse(BaseModel):
    date: str
    count: int


@router.get(
    "/function_requests",
    response_model=BaseResponse,
)
async def get_function_requests_over_time(
    appId: str,
    functionId: str,
    days: int = Query(7, ge=1, le=30),
    current_user=Depends(get_current_user),
):
    """
    Get the number of requests for a specific function over a period of time.
    """
    app = await Application.find_one(
        Application.app_id == appId, Application.users == current_user.username
    )
    if not app:
        return BaseResponse(code=404, msg="Application not found")

    time_ago = datetime.now() - timedelta(days=days)
    pipeline = [
        {
            "$match": {
                "app_id": app.app_id,
                "function_id": functionId,
                "timestamp": {"$gte": time_ago},
            }
        },
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
        {"$project": {"date": "$_id", "count": 1, "_id": 0}},
    ]
    result = await FunctionMetric.aggregate(pipeline).to_list()

    return BaseResponse(code=0, msg="Success", data=result)


class TopFunctionResponse(BaseModel):
    function_name: str
    count: int


@router.get("/top_functions", response_model=BaseResponse)
async def get_top_functions(
    appId: str,
    limit: int = Query(5, ge=1, le=20),
    current_user=Depends(get_current_user),
):
    """
    Get the top N functions by request count.
    """
    app = await Application.find_one(
        Application.app_id == appId, Application.users == current_user.username
    )
    if not app:
        return BaseResponse(code=404, msg="Application not found")

    pipeline = [
        {"$match": {"app_id": app.app_id}},
        {"$group": {"_id": "$function_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "functions",
                "localField": "_id",
                "foreignField": "function_id",
                "as": "function_info",
            }
        },
        {
            "$project": {
                "function_name": {"$arrayElemAt": ["$function_info.function_name", 0]},
                "count": 1,
                "_id": 0,
            }
        },
    ]
    result = await FunctionMetric.aggregate(pipeline).to_list()

    return BaseResponse(code=0, msg="Success", data=result)
