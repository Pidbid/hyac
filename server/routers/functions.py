# routers/services/functions.py
import math
import re
import httpx
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from bson import ObjectId

from fastapi import APIRouter, Depends, HTTPException, Response
from loguru import logger
from pydantic import BaseModel, Field

from core.config import settings
from core.jwt_auth import get_current_user
from models.applications_model import Application
from models.common_model import BaseResponse
from models.functions_history_model import FunctionsHistory
from models.functions_model import Function, FunctionStatus
from models.function_template_model import FunctionTemplate
from models.statistics_model import FunctionMetric
from models.users_model import User

router = APIRouter(
    prefix="/function",
    tags=["Function Management"],
    responses={404: {"description": "Not found"}},
)

# A client that can make requests to other services
http_client = httpx.AsyncClient()


class ProxyRequest(BaseModel):
    target_url: str = Field(..., description="The target URL to proxy the request to")
    method: str = Field(..., description="HTTP method")
    headers: Dict[str, str] = Field(default_factory=dict, description="Request headers")
    query_params: Dict[str, Any] = Field(
        default_factory=dict, description="Query parameters"
    )
    body: Any = Field(None, description="Request body")


from models.functions_model import Function, FunctionStatus, FunctionType


class CreateFunctionRequest(BaseModel):
    """Request model for creating a function."""

    appId: str
    name: str
    type: str = "endpoint"
    description: str = ""
    tags: list[str] = []
    language: str = "zh-CN"
    template_id: Optional[str] = None


class UpdateFunctionRequest(BaseModel):
    """Request model for updating a function's properties."""

    code: Optional[str] = None
    method: Optional[str] = None
    status: Optional[FunctionStatus] = None
    dependencies: Optional[list[str]] = None
    memory_limit: Optional[int] = None
    timeout: Optional[int] = None
    requires_auth: Optional[bool] = None


class FunctionDataRequestModel(BaseModel):
    """Request model for paginating through functions."""

    appId: str
    page: int = 1
    length: int = 10


class FunctionUpdateCodeModel(BaseModel):
    """Request model for updating a function's code."""

    appId: str
    id: str
    code: str


class DeleteFunctionRequest(BaseModel):
    """Request model for deleting a function."""

    appId: str
    id: str


class GetFunctionUrlRequest(BaseModel):
    """Request model for getting function url."""

    appId: str
    id: str


class FunctionHistoryRequest(BaseModel):
    """Request model for function histories."""

    appId: str
    id: str


@router.post("/url", response_model=BaseResponse)
async def function_url(
    data: GetFunctionUrlRequest, current_user=Depends(get_current_user)
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        return BaseResponse(code=404, msg="Application not found")
    func_result = await Function.find_one(
        Function.id == ObjectId(data.id), Function.app_id == app.app_id
    )
    if not func_result:
        raise HTTPException(status_code=404, detail="Function not found")
    function_url = f"{data.appId}.{settings.DOMAIN_NAME}/{data.id}"
    return BaseResponse(code=0, msg="Get function url success", data=function_url)


@router.post("/create", response_model=BaseResponse)
async def create_function(
    data: CreateFunctionRequest, current_user=Depends(get_current_user)
):
    """
    Creates a new function within an application.
    """
    # Find the application by app_id to get the app_id.
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        return BaseResponse(code=404, msg="Application not found")

    # Check if the function already exists in the application.
    if await Function.find_one(
        Function.function_name == data.name, Function.app_id == app.app_id
    ):
        return BaseResponse(code=309, msg="Function with this name already exists")

    # Check if the common function name contains Chinese characters.
    if data.type == FunctionType.COMMON and re.search(r"[\u4e00-\u9fa5]", data.name):
        return BaseResponse(
            code=308,
            msg="Common function name can only be in English.",
        )

    code = ""
    if data.template_id:
        template = await FunctionTemplate.find_one(
            FunctionTemplate.id == ObjectId(data.template_id)
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Check if the template's function type is compatible.
        if FunctionType(data.type) != template.function_type:
            raise HTTPException(
                status_code=400,
                detail="The selected template is not applicable for the chosen function type.",
            )
        code = template.code
    else:
        # If no template is specified, find a default system template from the DB.
        default_template = await FunctionTemplate.find_one(
            FunctionTemplate.type == "system",
            FunctionTemplate.function_type == FunctionType(data.type),
        )
        if default_template:
            code = default_template.code
        else:
            # Fallback if no default template is found in the database
            raise HTTPException(
                status_code=404,
                detail=f"No default template found for function type '{data.type}'. Please create a template first.",
            )

    new_func = Function(
        function_name=data.name,
        app_id=app.app_id,
        function_type=FunctionType(data.type),
        description=data.description,
        tags=data.tags,
        users=[current_user.username],  # Associate the current user
        status=FunctionStatus.PUBLISHED,  # Default status is published
        code=code,
    )
    await new_func.insert()

    return BaseResponse(
        code=0,
        msg="Function created successfully",
        data={
            "function_id": new_func.function_id,
            "function_name": new_func.function_name,
            "app_id": new_func.app_id,
        },
    )


@router.post("/data", response_model=BaseResponse)
async def list_functions(
    data: FunctionDataRequestModel,
    current_user=Depends(get_current_user),
):
    """
    Lists all functions for a given application with pagination.
    """
    # Find the application by app_id to ensure it exists.
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        return BaseResponse(code=404, msg="Application not found")

    # Build the query based on user authentication.
    if not current_user:
        query = Function.find(
            Function.app_id == app.app_id, Function.requires_auth == False
        )
    else:
        query = Function.find(Function.app_id == app.app_id)

    total_count = await query.count()
    items = await query.skip((data.page - 1) * data.length).limit(data.length).to_list()
    page_num = math.ceil(total_count / data.length) if data.length > 0 else 0

    return BaseResponse(
        code=0,
        msg="success",
        data={
            "data": items,
            "total": total_count,
            "pageNum": page_num,
            "pageSize": data.length,
        },
    )


@router.post("/update_code", response_model=BaseResponse)
async def update_function_code(
    data: FunctionUpdateCodeModel, current_user=Depends(get_current_user)
):
    """
    Updates the code of a specific function and records the change in history.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    function_id = data.id
    code = data.code

    if not function_id or not code:
        raise HTTPException(status_code=400, detail="Function ID and code are required")

    func = await Function.find_one(
        Function.function_id == function_id,
        Function.app_id == app.app_id,
        Function.users == current_user.username,
    )
    if not func:
        raise HTTPException(
            status_code=404, detail="Function not found or permission denied"
        )

    # Record the code change in the history.
    await FunctionsHistory(
        function_id=func.function_id,
        old_code=func.code,
        new_code=code,
        updated_by=current_user.username,
        updated_at=datetime.now(),
    ).insert()

    func.code = code
    func.update_timestamp()
    await func.save()

    # The cache in the 'app' service will be invalidated by the cache_watcher.
    # No need to invalidate here as the 'server' and 'app' caches are separate.

    return BaseResponse(code=0, msg="Function code updated successfully", data={})


@router.post("/delete", response_model=BaseResponse)
async def delete_function(
    data: DeleteFunctionRequest, current_user=Depends(get_current_user)
):
    """
    Deletes a function from the database and clears its cache.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    function_id = data.id

    if not function_id:
        raise HTTPException(status_code=400, detail="Function ID is required")

    func = await Function.find_one(
        Function.function_id == function_id,
        Function.app_id == app.app_id,
        Function.users == current_user.username,
    )
    if not func:
        raise HTTPException(
            status_code=404, detail="Function not found or you don't have permission"
        )

    # Delete the function from the database.
    await func.delete()

    # Delete the function history from the database.
    await FunctionsHistory.find(FunctionsHistory.function_id == function_id).delete()
    # Delete the function statistics from the database.
    await FunctionMetric.find(FunctionMetric.function_id == function_id).delete()

    return BaseResponse(code=0, msg="Function deleted successfully", data={})


@router.post("/function_history", response_model=BaseResponse)
async def function_history(
    data: FunctionHistoryRequest, current_user=Depends(get_current_user)
):
    """
    Get function histories.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    function_id = data.id

    if not function_id:
        raise HTTPException(status_code=400, detail="Function ID is required")

    func = await Function.find_one(
        Function.function_id == function_id,
        Function.app_id == app.app_id,
        Function.users == current_user.username,
    )
    if not func:
        raise HTTPException(
            status_code=404, detail="Function not found or permission denied"
        )

    function_histories = await FunctionsHistory.find(
        FunctionsHistory.function_id == function_id
    ).to_list()

    return BaseResponse(
        code=0,
        msg="Get function histories successfully",
        data={"data": function_histories},
    )


@router.post("/proxy_test")
async def test_function(
    proxy_request: ProxyRequest, current_user: User = Depends(get_current_user)
):
    """
    A secure proxy for testing functions from the console.
    It validates the target URL and ensures the user owns the application.
    """
    target_url = proxy_request.target_url
    parsed_url = urlparse(target_url)
    host = parsed_url.netloc

    base_domain = settings.DOMAIN_NAME
    if not base_domain or not host.endswith(f".{base_domain}"):
        return BaseResponse(
            code=307, msg="DOMAIN_NAME is not configured on the server."
        )

    # Security Check: Ensure the user owns the application
    app_id = host.replace(f".{base_domain}", "")
    app = await Application.find_one(
        Application.app_id == app_id, Application.users == current_user.username
    )
    if not app:
        return BaseResponse(
            code=202,
            msg=f"Application '{app_id}' not found or you do not have permission to access it.",
        )

    try:
        logger.info(
            f"User '{current_user.username}' is testing function at {target_url}"
        )

        # Forward the request
        local_url = target_url.replace(
            f"s://{parsed_url.netloc}", f"://hyac-app-runtime-{app_id.lower()}:8001"
        )
        logger.info(f"Function test target local url: {local_url}")
        proxied_response = await http_client.request(
            method=proxy_request.method,
            url=local_url,
            headers=proxy_request.headers,
            params=proxy_request.query_params,
            json=proxy_request.body,
            timeout=60.0,
        )

        return BaseResponse(
            code=0,
            msg="function test success",
            data={
                "status_code": proxied_response.status_code,
                "content": proxied_response.content,
                "headers": dict(proxied_response.headers),
            },
        )
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy test request to {target_url}: {e}")
        return BaseResponse(code=306, msg="Function test failed")
