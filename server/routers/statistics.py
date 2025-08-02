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
    FunctionRankingItem,
)
from core.jwt_auth import get_current_user
from core.database_dynamic import dynamic_db
from core.minio_manager import minio_manager

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
        {"$match": {"app_id": app.app_id, "function_name": {"$ne": "Unknown"}}},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }
        },
    ]
    requests_result = await FunctionMetric.aggregate(requests_pipeline).to_list()

    success_calls = 0
    error_calls = 0
    for res in requests_result:
        if res["_id"] == CallStatus.SUCCESS:
            success_calls = res["count"]
        elif res["_id"] == CallStatus.ERROR:
            error_calls = res["count"]

    # --- Unknown Requests ---
    unknown_requests_pipeline = [
        {"$match": {"app_id": app.app_id}},
        {
            "$lookup": {
                "from": "functions",
                "localField": "function_id",
                "foreignField": "function_id",
                "as": "function_info",
            }
        },
        {"$match": {"function_info": []}},
        {"$count": "count"},
    ]
    unknown_requests_result = await FunctionMetric.aggregate(
        unknown_requests_pipeline
    ).to_list()
    unknown_calls = (
        unknown_requests_result[0]["count"] if unknown_requests_result else 0
    )

    total_calls = success_calls + error_calls + unknown_calls

    # --- Overall Average Execution Time ---
    overall_avg_time_pipeline = [
        {"$match": {"app_id": app.app_id}},
        {
            "$group": {
                "_id": None,
                "avg_time": {"$avg": "$execution_time"},
            }
        },
    ]
    overall_avg_time_result = await FunctionMetric.aggregate(
        overall_avg_time_pipeline
    ).to_list()
    overall_average_execution_time = (
        (overall_avg_time_result[0]["avg_time"] * 1000)
        if overall_avg_time_result and overall_avg_time_result[0]["avg_time"]
        else 0
    )

    # --- Function Ranking ---
    ranking_pipeline_base = [
        {"$match": {"app_id": app.app_id}},
        {
            "$group": {
                "_id": "$function_id",
                "count": {"$sum": 1},
                "avg_time": {"$avg": "$execution_time"},
            }
        },
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
                "function_id": "$_id",
                "function_name": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$function_info.function_name", 0]},
                        "Unknown",
                    ]
                },
                "count": 1,
                "average_execution_time": {
                    "$multiply": ["$avg_time", 1000]
                },  # Convert to ms
                "_id": 0,
            }
        },
    ]

    # Ranking by count
    ranking_by_count_pipeline = ranking_pipeline_base + [
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    ranking_by_count_result = await FunctionMetric.aggregate(
        ranking_by_count_pipeline
    ).to_list()

    # Ranking by time
    ranking_by_time_pipeline = ranking_pipeline_base + [
        {"$sort": {"average_execution_time": -1}},
        {"$limit": 5},
    ]
    ranking_by_time_result = await FunctionMetric.aggregate(
        ranking_by_time_pipeline
    ).to_list()

    function_stats = FunctionStats(
        count=function_count,
        requests=RequestStats(
            total=total_calls,
            success=success_calls,
            error=error_calls,
            unknown=unknown_calls,
        ),
        overall_average_execution_time=overall_average_execution_time,
        ranking_by_count=[
            FunctionRankingItem(**item) for item in ranking_by_count_result
        ],
        ranking_by_time=[
            FunctionRankingItem(**item) for item in ranking_by_time_result
        ],
    )

    # --- Database Statistics ---
    db = dynamic_db.app_db(data.appId)
    collection_names = await db.list_collection_names()
    db_stats = DatabaseStats(count=len(collection_names), collections=[])
    for name in collection_names:
        count = await db[name].count_documents({})
        db_stats.collections.append(CollectionStats(name=name, count=count))

    # --- Storage Statistics ---
    total_usage_bytes = 0
    try:
        # MinIO bucket names must be lowercase
        bucket_name = data.appId.lower()
        objects = await minio_manager.list_objects(
            bucket_name=bucket_name, recursive=True
        )
        if objects:
            # Filter out directories, which have a size of 0
            total_usage_bytes = sum(
                obj.get("size", 0) for obj in objects if obj and not obj.get("is_dir")
            )
    except Exception as e:
        # Log the error but don't fail the whole request
        print(f"Could not calculate storage usage for {data.appId}: {e}")

    total_usage_mb = total_usage_bytes / (1024 * 1024)
    storage_stats = StorageStats(total_usage_mb=total_usage_mb)

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
    days: int = Query(7, ge=1, le=30),
    functionId: str = Query(None),
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
    match_filter = {
        "app_id": app.app_id,
        "timestamp": {"$gte": time_ago},
    }
    if functionId and functionId != "all":
        match_filter["function_id"] = functionId

    pipeline = [
        {"$match": match_filter},
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
