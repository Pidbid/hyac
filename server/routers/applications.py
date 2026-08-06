# routers/services/applications.py
import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from core.environment_contract import filter_user_environment_variables
from core.database import mongodb_manager
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
from models.tasks_model import Task, TaskAction
from loguru import logger
from typing import List

router = APIRouter(
    prefix="/applications",
    tags=["Applications Administration"],
    responses={404: {"description": "Application not found"}},
)


def serialize_application(application: Application) -> dict:
    """Return console-safe application metadata without internal credentials."""
    data = application.model_dump(mode="json", by_alias=True)
    data.pop("db_password", None)
    data.pop("runtime_token_hash", None)
    data.pop("pending_traefik_cleanup_generation", None)
    data.pop("runtime_cleanup_task_id", None)
    data.pop("runtime_cleanup_lease_owner", None)
    data.pop("runtime_cleanup_lease_expires_at", None)
    data.pop("lifecycle_completed_task_id", None)
    if isinstance(data.get("ai_config"), dict):
        data["ai_config"].pop("api_key", None)
    notification = data.get("notification")
    if isinstance(notification, dict) and isinstance(notification.get("email"), dict):
        notification["email"].pop("password", None)
    data["environment_variables"] = filter_user_environment_variables(
        data.get("environment_variables", [])
    )
    return data


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


async def _transition_and_enqueue(
    app: Application,
    username: str,
    *,
    action: TaskAction,
    status: ApplicationStatus,
    set_fields: Optional[dict] = None,
    reject_active_actions: Optional[set[TaskAction]] = None,
) -> Task:
    """Atomically claim a lifecycle revision and publish its durable task."""
    expected_status = app.status
    expected_revision = app.lifecycle_revision
    next_revision = expected_revision + 1
    updated_at = datetime.now()
    task = Task(
        app_id=app.app_id,
        action=action,
        payload={
            "app_id": app.app_id,
            "lifecycle_revision": next_revision,
        },
    )
    update_fields = {
        "status": status,
        "lifecycle_completed_task_id": None,
        "updated_at": updated_at,
        **(set_fields or {}),
    }

    async def persist_transition(session):
        if reject_active_actions:
            active_task = await mongodb_manager.get_collection(Task).find_one(
                {
                    "app_id": app.app_id,
                    "action": {"$in": list(reject_active_actions)},
                    "status": {"$in": ["pending", "running"]},
                },
                session=session,
            )
            if active_task:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Application has an active lifecycle task; retry after "
                        "it finishes."
                    ),
                )
        result = await mongodb_manager.get_collection(Application).update_one(
            {
                "app_id": app.app_id,
                "users": username,
                "status": expected_status,
                "lifecycle_revision": expected_revision,
            },
            {
                "$set": update_fields,
                "$inc": {"lifecycle_revision": 1},
            },
            session=session,
        )
        if result.matched_count == 0:
            raise HTTPException(
                status_code=409,
                detail="Application lifecycle changed; retry the operation.",
            )
        await task.insert(session=session)

    async with mongodb_manager.client.start_session() as session:
        # The driver retries TransientTransactionError callbacks and resolves
        # UnknownTransactionCommitResult by retrying only the commit. The task
        # is constructed above so callback retries keep the same durable ID.
        await session.with_transaction(persist_transition)

    app.status = status
    app.lifecycle_revision = next_revision
    app.lifecycle_completed_task_id = None
    app.updated_at = updated_at
    return task


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
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        notification=NotificationConfig(),
        status=ApplicationStatus.STARTING,
        lifecycle_revision=1,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    task = Task(
        app_id=new_app.app_id,
        action=TaskAction.START_APP,
        payload={
            "app_id": new_app.app_id,
            "lifecycle_revision": new_app.lifecycle_revision,
        },
    )

    async def persist_creation(session):
        await new_app.insert(session=session)
        await task.insert(session=session)

    try:
        async with mongodb_manager.client.start_session() as session:
            # Keep both documents stable across callback retries so a transient
            # transaction failure cannot publish a second task identity.
            await session.with_transaction(persist_creation)
    except DuplicateKeyError as exc:
        # The initial name check is advisory; the unique index is the arbiter
        # when concurrent requests both pass it.
        raise HTTPException(
            status_code=409,
            detail=f"Application with name '{app_name}' already exists",
        ) from exc

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

    if app.status == ApplicationStatus.DELETING:
        raise HTTPException(
            status_code=409,
            detail="Application deletion is already in progress.",
        )

    task = await _transition_and_enqueue(
        app,
        current_user.username,
        action=TaskAction.DELETE_APP,
        status=ApplicationStatus.DELETING,
        reject_active_actions={
            TaskAction.START_APP,
            TaskAction.RESTART_APP,
        },
    )

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

    if app.status not in {
        ApplicationStatus.STOPPED,
        ApplicationStatus.ERROR,
    }:
        return BaseResponse(
            code=400,
            msg=f"Application cannot start while status is '{app.status.value}'.",
        )

    task = await _transition_and_enqueue(
        app,
        current_user.username,
        action=TaskAction.START_APP,
        status=ApplicationStatus.STARTING,
    )

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

    task = await _transition_and_enqueue(
        app,
        current_user.username,
        action=TaskAction.STOP_APP,
        status=ApplicationStatus.STOPPING,
    )

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

    task = await _transition_and_enqueue(
        app,
        current_user.username,
        action=TaskAction.RESTART_APP,
        status=ApplicationStatus.STARTING,
    )

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
    result = await mongodb_manager.get_collection(Application).update_one(
        {"app_id": app.app_id, "users": current_user.username},
        {
            "$set": {
                "description": app.description,
                "updated_at": app.updated_at,
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Application changed before description update",
        )

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
    if app.status in {
        ApplicationStatus.STARTING,
        ApplicationStatus.STOPPING,
        ApplicationStatus.DELETING,
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "Application dependencies cannot change during a lifecycle "
                "transition."
            ),
        )

    task = await _transition_and_enqueue(
        app,
        current_user.username,
        action=TaskAction.RESTART_APP,
        status=ApplicationStatus.STARTING,
        set_fields={
            "common_dependencies": [
                dependency.model_dump(mode="python", by_alias=True)
                for dependency in data.dependencies
            ]
        },
    )
    app.common_dependencies = data.dependencies

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

    return BaseResponse(code=0, msg="success", data=serialize_application(app))


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
            "data": [serialize_application(app) for app in data_list],
            "pageNum": page_num,
            "pageSize": data.length,
            "total": total_count,
        },
    )
