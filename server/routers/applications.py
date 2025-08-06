# routers/services/applications.py
import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from core.jwt_auth import get_current_user
from core.utils import generate_short_id
from models.applications_model import (
    Application,
    CORSConfig,
    Dependency,
    NotificationConfig,
    ApplicationStatus,
)
from models.common_model import BaseResponse
from models.functions_model import Function, FunctionStatus
from models.tasks_model import Task, TaskAction
from loguru import logger
from core.docker_manager import docker_manager, start_app_container, stop_app_container
from typing import List

router = APIRouter(
    prefix="/applications",
    tags=["Applications Administration"],
    responses={404: {"description": "Application not found"}},
)


class CreateApplicationRequest(BaseModel):
    """Request model for creating an application."""

    appName: str
    description: Optional[str] = None


class UpdateApplicationDescriptionRequest(BaseModel):
    """Request model for updating an application's description."""

    appId: str
    description: str


class UpdateApplicationDependenciesRequest(BaseModel):
    """Request model for updating an application's common dependencies."""

    appId: str
    dependencies: List[Dependency]


class DeleteApplicationRequest(BaseModel):
    """Request model for deleting an application."""

    appId: str


class ApplicationOperationRequest(BaseModel):
    """Request model for application operations like start/stop."""

    appId: str


class GetApplicationsData(BaseModel):
    """Request model for paginating through applications."""

    page: int = 1
    length: int = 10


class ApplicationInfoRequestModel(BaseModel):
    """Request model for getting information about a single application."""

    appId: str


@router.post("/create", response_model=BaseResponse)
async def create_application(
    data: CreateApplicationRequest,
    current_user=Depends(get_current_user),
):
    """
    Accepts the request to create a new application and starts the container in the background.
    """
    app_name = data.appName
    if await Application.find_one(Application.app_name == app_name):
        raise HTTPException(
            status_code=409, detail=f"Application with name '{app_name}' already exists"
        )

    new_app = Application(
        app_name=app_name,
        description=data.description,
        users=[current_user.username],
        common_dependencies=[],
        environment_variables=[],
        db_password=generate_short_id(16),
        cors=CORSConfig(
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        notification=NotificationConfig(),
        status=ApplicationStatus.STARTING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    await new_app.insert()

    # Create a task to start the container
    task = Task(
        action=TaskAction.START_APP,
        payload={"app_id": new_app.app_id},
    )
    await task.insert()

    logger.info(
        f"App '{new_app.app_name}' creation request accepted. Task '{task.task_id}' created."
    )

    return BaseResponse(
        code=0,
        msg="Application creation task has been created and is being processed.",
        data={"app_id": new_app.app_id, "task_id": task.task_id},
    )


@router.post("/delete", response_model=BaseResponse)
async def delete_application(
    data: DeleteApplicationRequest,
    current_user=Depends(get_current_user),
):
    """
    Initiates the deletion of an application by creating a background task.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )

    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or you don't have permission"
        )

    # Update status to prevent other operations
    app.status = ApplicationStatus.DELETING
    await app.save()

    # Create a task to delete the application
    task = Task(
        action=TaskAction.DELETE_APP,
        payload={"app_id": app.app_id},
    )
    await task.insert()

    logger.info(
        f"App '{app.app_name}' deletion request accepted. Task '{task.task_id}' created."
    )

    return BaseResponse(
        code=0,
        msg=f"Application '{data.appId}' deletion task has been created.",
        data={"task_id": task.task_id},
    )


@router.post("/start", response_model=BaseResponse)
async def start_application(
    data: ApplicationOperationRequest,
    current_user=Depends(get_current_user),
):
    """
    Starts a stopped application by creating a background task.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        return BaseResponse(
            code=202, msg="Application not found or you don't have permission"
        )

    if app.status == ApplicationStatus.RUNNING:
        return BaseResponse(code=400, msg="Application is already running.")

    app.status = ApplicationStatus.STARTING
    await app.save()

    # Create a task to start the application
    task = Task(
        action=TaskAction.START_APP,
        payload={"app_id": app.app_id},
    )
    await task.insert()

    return BaseResponse(
        code=0,
        msg="Application start task has been created and is being processed.",
        data={"app_id": app.app_id, "task_id": task.task_id},
    )


@router.post("/stop", response_model=BaseResponse)
async def stop_application(
    data: ApplicationOperationRequest,
    current_user=Depends(get_current_user),
):
    """
    Stops a running application by creating a background task.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or you don't have permission"
        )

    if app.status != ApplicationStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Application is not running.")

    app.status = ApplicationStatus.STOPPING
    await app.save()

    # Create a task to stop the application
    task = Task(
        action=TaskAction.STOP_APP,
        payload={"app_id": app.app_id},
    )
    await task.insert()

    return BaseResponse(
        code=0,
        msg="Application stop task has been created and is being processed.",
        data={"app_id": app.app_id, "task_id": task.task_id},
    )


@router.post("/restart", response_model=BaseResponse)
async def restart_application(
    data: ApplicationOperationRequest,
    current_user=Depends(get_current_user),
):
    """
    Restarts a running application by creating a background task.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or you don't have permission"
        )

    if app.status != ApplicationStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Application is not running.")

    # Create a task to restart the application
    task = Task(
        action=TaskAction.RESTART_APP,
        payload={"app_id": app.app_id},
    )
    await task.insert()
    # Set Application status to STARTING
    app.status = ApplicationStatus.STARTING
    await app.save()

    return BaseResponse(
        code=0,
        msg="Application restart task has been created and is being processed.",
        data={"app_id": app.app_id, "task_id": task.task_id},
    )


@router.post("/update_description", response_model=BaseResponse)
async def update_application_description(
    data: UpdateApplicationDescriptionRequest, current_user=Depends(get_current_user)
):
    """
    Updates the description of an application.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )

    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or you don't have permission"
        )

    app.description = data.description
    app.update_timestamp()
    await app.save()

    return BaseResponse(
        code=0, msg="Application description updated successfully", data={}
    )


@router.post("/update_dependencies", response_model=BaseResponse)
async def update_application_dependencies(
    data: UpdateApplicationDependenciesRequest, current_user=Depends(get_current_user)
):
    """
    Updates the common dependencies of an application and creates a task to restart its container.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )

    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or you don't have permission"
        )

    app.common_dependencies = data.dependencies
    app.update_timestamp()
    await app.save()

    # Create a task to restart the application
    task = Task(
        action=TaskAction.RESTART_APP,
        payload={"app_id": app.app_id},
    )
    await task.insert()

    return BaseResponse(
        code=0,
        msg="Application dependencies updated. A task has been created to restart the container.",
        data={"task_id": task.task_id},
    )


@router.post("/info", response_model=BaseResponse)
async def get_application(
    data: ApplicationInfoRequestModel, user=Depends(get_current_user)
):
    """
    Retrieves information about a single application.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == user.username
    )
    if not app:
        return BaseResponse(code=404, msg="Application not found")

    return BaseResponse(code=0, msg="success", data=app)


@router.post("/data", response_model=BaseResponse)
async def data_applications(data: GetApplicationsData, user=Depends(get_current_user)):
    """
    Retrieves a paginated list of applications for the current user.
    """
    skip = (data.page - 1) * data.length
    query = Application.find(Application.users == user.username)
    data_list = await query.skip(skip).limit(data.length).to_list()
    total_count = await query.count()

    page_num = math.ceil(total_count / data.length) if data.length > 0 else 0

    return BaseResponse(
        code=0,
        msg="success",
        data={
            "data": data_list,
            "pageNum": page_num,
            "pageSize": data.length,
            "total": total_count,
        },
    )
