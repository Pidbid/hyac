# routers/runtime.py
from fastapi import APIRouter, Depends
from models.common_model import BaseResponse
from core.jwt_auth import get_current_user
from core.runtime_status_manager import sync_runtime_status
from models.applications_model import Application
from typing import List

router = APIRouter(
    prefix="/runtimes",
    tags=["Runtimes Administration"],
    responses={404: {"description": "Not found"}},
)


@router.get("/status/sync", response_model=BaseResponse)
async def trigger_runtime_status_sync(current_user=Depends(get_current_user)):
    """
    Manually triggers the synchronization of runtime statuses.
    """
    await sync_runtime_status()
    return BaseResponse(
        code=0, msg="Runtime status synchronization triggered successfully.", data={}
    )


@router.get("/status", response_model=BaseResponse)
async def get_all_runtimes_status(current_user=Depends(get_current_user)):
    """
    Retrieves the current status of all applications.
    """
    all_apps: List[Application] = await Application.find(
        Application.users == current_user.username
    ).to_list()

    status_data = [
        {"app_id": app.app_id, "app_name": app.app_name, "status": app.status}
        for app in all_apps
    ]

    return BaseResponse(code=0, msg="success", data=status_data)
