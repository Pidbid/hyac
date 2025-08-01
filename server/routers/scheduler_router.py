from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel
import asyncio

from models.scheduled_tasks_model import ScheduledTask, TriggerType
from models.common_model import BaseResponse
from core.scheduler_manager import scheduler_manager
from models.users_model import User
from core.jwt_auth import get_current_user
from models.applications_model import Application
from models.functions_model import Function, FunctionType
from core.scheduled_runner import run_function
from core.exceptions import APIException


def admin_required(current_user: User = Depends(get_current_user)):
    if "admin" not in current_user.roles:
        raise APIException(code=403, msg="Administrator access required.")
    return current_user


router = APIRouter(
    prefix="/scheduler", tags=["Scheduler"], dependencies=[Depends(admin_required)]
)


class TaskRequest(BaseModel):
    appId: str
    functionId: str


class ScheduledTaskUpsert(BaseModel):
    appId: str
    functionId: str
    name: str
    trigger: TriggerType
    trigger_config: dict
    params: Optional[dict] = {}
    body: Optional[dict] = {}
    enabled: bool = False
    description: Optional[str] = None


@router.post("/get", response_model=BaseResponse)
async def get_task_for_function(req: TaskRequest):
    task = await ScheduledTask.find_one(
        ScheduledTask.app_id == req.appId, ScheduledTask.function_id == req.functionId
    )
    return BaseResponse(code=0, msg="Success", data=task)


@router.post("/upsert", response_model=BaseResponse)
async def upsert_task_for_function(req: ScheduledTaskUpsert):
    # Validate function type before upserting a task
    target_function = await Function.find_one(
        Function.app_id == req.appId, Function.function_id == req.functionId
    )
    if not target_function:
        raise APIException(code=302, msg="Target function not found.")

    if target_function.function_type == FunctionType.COMMON:
        raise APIException(
            code=311, msg="Common functions cannot have scheduled tasks."
        )

    task = await ScheduledTask.find_one(
        ScheduledTask.app_id == req.appId, ScheduledTask.function_id == req.functionId
    )

    update_data = req.model_dump(exclude={"appId", "functionId"})

    if task:
        await task.update({"$set": update_data})
        updated_task = await ScheduledTask.find_one(
            ScheduledTask.app_id == req.appId,
            ScheduledTask.function_id == req.functionId,
        )
    else:
        updated_task = ScheduledTask(
            app_id=req.appId, function_id=req.functionId, **update_data
        )
        await updated_task.insert()

    await scheduler_manager.add_job(updated_task)
    return BaseResponse(code=0, msg="Success", data=updated_task)


@router.post("/delete", response_model=BaseResponse)
async def delete_task_for_function(req: TaskRequest):
    task = await ScheduledTask.find_one(
        ScheduledTask.app_id == req.appId, ScheduledTask.function_id == req.functionId
    )
    if task:
        await scheduler_manager.remove_job(task.task_id)
        await task.delete()
    return BaseResponse(code=0, msg="Task deleted successfully.")


@router.post("/trigger", response_model=BaseResponse)
async def trigger_task_for_function(req: TaskRequest):
    task = await ScheduledTask.find_one(
        ScheduledTask.app_id == req.appId, ScheduledTask.function_id == req.functionId
    )
    if not task:
        raise APIException(code=302, msg="Task not found for this function.")

    try:
        # The app_id is now directly available in the task object.
        asyncio.create_task(
            run_function(
                task.app_id,
                req.functionId,
                getattr(task, "params", None) or {},
                task.body or {},
            )
        )
        return BaseResponse(code=0, msg=f"Task '{task.name}' triggered successfully.")
    except Exception as e:
        raise APIException(310, str(e))
