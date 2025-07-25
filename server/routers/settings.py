# server/routers/settings.py
import json
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from loguru import logger
from docker import errors
from models import (
    Application,
    BaseResponse,
    User,
    EnvironmentVariable,
    CORSConfig,
    NotificationConfig,
    AIConfig,
)
from core.dependence_manager import dependence_manager
from core.docker_manager import docker_manager
from core.jwt_auth import get_current_user
from core.config import settings
from core.update_manager import update_manager
from core.exceptions import APIException


class DependenceSearchRequest(BaseModel):
    appId: str
    name: str
    forceUpdate: bool = False


class DependenceUpdateRequest(BaseModel):
    appId: str


class PackageInfoRequest(BaseModel):
    appId: str
    name: str


class PackageAddRequest(BaseModel):
    appId: str
    name: str
    version: str
    restart: bool = False


class PackageRemoveRequest(BaseModel):
    appId: str
    name: str
    restart: bool = False


class AppDependenciesRequest(BaseModel):
    appId: str


class EnvAddRequest(BaseModel):
    appId: str
    key: str
    value: str


class EnvRemoveRequest(BaseModel):
    appId: str
    key: str


class CORSDataRequest(BaseModel):
    appId: str


class CORSUpdateRequest(BaseModel):
    appId: str
    config: CORSConfig


class NotificationDataRequest(BaseModel):
    appId: str


class NotificationUpdateRequest(BaseModel):
    appId: str
    config: NotificationConfig


class ApplicationStatusRequest(BaseModel):
    appId: str


class AIConfigDataRequest(BaseModel):
    appId: str


class AIConfigUpdateRequest(BaseModel):
    appId: str
    config: AIConfig


router = APIRouter(
    prefix="/settings",
    tags=["Settings Management"],
    responses={404: {"description": "Not found"}},
)


def get_app_system_dependencies(app: Application) -> list[dict]:
    system_deps = []
    container_name = f"hyac-app-runtime-{app.app_id.lower()}"
    exit_code, output = docker_manager.exec_in_container(
        container_name, "uv pip list --format=json --system"
    )

    if exit_code == 0 and output:
        try:
            # The output of `uv pip list` may contain non-JSON text at the beginning.
            # We need to find the start of the JSON array `[` to parse it correctly.
            json_start_index = output.find("[")
            if json_start_index != -1:
                json_output = output[json_start_index:]
                system_deps = json.loads(json_output)
            else:
                logger.error(
                    f"Could not find JSON start in 'uv pip list' output for container {container_name}"
                )
        except json.JSONDecodeError:
            logger.error(
                f"Failed to parse JSON from 'uv pip list' for container {container_name}: {output}"
            )
    elif exit_code != 0:
        logger.error(f"Failed to execute 'uv pip list' in {container_name}: {output}")
    return system_deps


@router.post("/dependence_search", response_model=BaseResponse)
async def dependence_search(
    data: DependenceSearchRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )
    if data.forceUpdate:
        await dependence_manager.packages_update()
    dep_list = await dependence_manager.package_search(data.name)
    if len(dep_list) != 0:
        return BaseResponse(code=0, msg="success", data=dep_list)
    else:
        return BaseResponse(code=1, msg="dependence not found")


@router.post("/package_info", response_model=BaseResponse)
async def package_info(
    data: PackageInfoRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )
    dep_list = await dependence_manager.package_info(data.name)
    return BaseResponse(code=0, msg="success", data=dep_list)


@router.post("/package_add", response_model=BaseResponse)
async def package_add(
    data: PackageAddRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    system_deps = get_app_system_dependencies(app)
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )
    elif data.name in [d["name"] for d in system_deps]:
        return BaseResponse(
            code=105, msg="Add failed, because system dependencies already exist"
        )
    elif data.name in [d["name"] for d in app.common_dependencies]:
        # await app.update(
        #     {"$set": {"common_dependencies.$[elem].version": data.version}},
        #     array_filters=[{"elem.name": data.name}],
        # )
        return BaseResponse(
            code=106, msg="Add failed, because dependencies already exist"
        )
    else:
        await app.update(
            {
                "$push": {
                    "common_dependencies": {"name": data.name, "version": data.version}
                }
            }
        )

    if data.restart:
        container_name = f"hyac-app-runtime-{app.app_id.lower()}"
        logger.info(
            f"Restarting container {container_name} to apply dependency changes."
        )
        if not docker_manager.restart_container(container_name):
            logger.warning(f"Could not restart container {container_name}.")
            return BaseResponse(
                code=1, msg="Add package success, but failed to restart container."
            )
        return BaseResponse(code=0, msg="Add package success and container restarted.")

    return BaseResponse(code=0, msg="add package success")


@router.post("/package_remove", response_model=BaseResponse)
async def package_remove(
    data: PackageRemoveRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )
    await app.update({"$pull": {"common_dependencies": {"name": data.name}}})
    system_deps = get_app_system_dependencies(app)
    if data.name in [d["name"] for d in system_deps]:
        container_name = f"hyac-app-runtime-{app.app_id.lower()}"
        command = f"uv pip uninstall {data.name} --system"
        docker_manager.exec_in_container(container_name, command)

    if data.restart:
        container_name = f"hyac-app-runtime-{app.app_id.lower()}"
        logger.info(
            f"Restarting container {container_name} to apply dependency changes."
        )
        if not docker_manager.restart_container(container_name):
            logger.warning(f"Could not restart container {container_name}.")
            return BaseResponse(
                code=1, msg="Remove package success, but failed to restart container."
            )
        return BaseResponse(
            code=0, msg="Remove package success and container restarted."
        )

    return BaseResponse(code=0, msg="remove package success")


@router.post("/dependence_update", response_model=BaseResponse)
async def dependence_update(
    data: DependenceUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )
    up_res = await dependence_manager.packages_update()
    if up_res:
        return BaseResponse(code=0, msg="Update dependencies successful")
    else:
        return BaseResponse(code=1, msg="failed")


@router.post("/dependencies_data", response_model=BaseResponse)
async def dependencies_data(
    data: AppDependenciesRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    system_all_deps = get_app_system_dependencies(app)
    system_deps = [
        d
        for d in system_all_deps
        if d["name"] not in [i.name for i in app.common_dependencies]
    ]
    response_data = {
        "common": app.common_dependencies,
        "system": system_deps,
    }

    return BaseResponse(code=0, msg="Get dependencies data success", data=response_data)


@router.post("/envs_data", response_model=BaseResponse)
async def envs_data(
    data: AppDependenciesRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    # 1. User variables are sourced directly from the database.
    user_envs = [env.model_dump() for env in app.environment_variables]
    user_env_keys = {env.key for env in app.environment_variables}

    # 2. System variables are determined from the container's startup config,
    #    excluding any keys that are defined as user variables.
    container_name = f"hyac-app-runtime-{app.app_id.lower()}"
    try:
        container = docker_manager.client.containers.get(container_name)
        startup_envs = container.attrs["Config"]["Env"]
    except errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")

    system_envs = []
    for env_str in startup_envs:
        key, value = env_str.split("=", 1)
        if key not in user_env_keys:
            system_envs.append({"key": key, "value": value})

    response_data = {
        "user": user_envs,
        "system": system_envs,
    }

    return BaseResponse(code=0, msg="Get envs data success", data=response_data)


@router.post("/env_add", response_model=BaseResponse)
async def env_add(
    data: EnvAddRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    # Update database for persistence
    env_found = False
    for env in app.environment_variables:
        if env.key == data.key:
            env.value = data.value
            env_found = True
            break
    if not env_found:
        app.environment_variables.append(
            EnvironmentVariable(key=data.key, value=data.value)
        )
    await app.save()

    return BaseResponse(code=0, msg="Environment variable added successfully.")


@router.post("/env_remove", response_model=BaseResponse)
async def env_remove(
    data: EnvRemoveRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    # Update database for persistence
    app.environment_variables = [
        env for env in app.environment_variables if env.key != data.key
    ]
    await app.save()

    return BaseResponse(code=0, msg="Environment variable removed successfully.")


@router.post("/cors_data", response_model=BaseResponse)
async def cors_data(
    data: CORSDataRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    return BaseResponse(code=0, msg="Get CORS data success", data=app.cors)


@router.post("/cors_update", response_model=BaseResponse)
async def cors_update(
    data: CORSUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    app.cors = data.config
    await app.save()

    return BaseResponse(code=0, msg="CORS updated successfully.")


@router.post("/notification_data", response_model=BaseResponse)
async def notification_data(
    data: NotificationDataRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    return BaseResponse(
        code=0, msg="Get notification data success", data=app.notification
    )


@router.post("/notification_update", response_model=BaseResponse)
async def notification_update(
    data: NotificationUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    app.notification = data.config
    await app.save()

    return BaseResponse(code=0, msg="Notification updated successfully.")


@router.post("/application_status", response_model=BaseResponse)
async def application_status(
    data: ApplicationStatusRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )
    return BaseResponse(code=0, msg="Get application status success", data=app.status)


@router.get("/domain", response_model=BaseResponse)
async def get_domain(current_user: User = Depends(get_current_user)):
    domain = settings.DOMAIN_NAME
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not configured")
    return BaseResponse(code=0, msg="Get domain success", data=domain)


@router.post("/ai_config_data", response_model=BaseResponse)
async def ai_config_data(
    data: AIConfigDataRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    return BaseResponse(code=0, msg="Get AI config data success", data=app.ai_config)


@router.post("/ai_config_update", response_model=BaseResponse)
async def ai_config_update(
    data: AIConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    app.ai_config = data.config
    await app.save()

    return BaseResponse(code=0, msg="AI config updated successfully.")


class UpdateCheckRequest(BaseModel):
    proxy: str | None = None


@router.post("/system/check_update", response_model=BaseResponse)
async def check_for_updates(
    request: UpdateCheckRequest, current_user: User = Depends(get_current_user)
):
    """
    Checks for system updates by comparing local version with the latest GitHub release.
    """
    if "admin" not in current_user.roles:
        raise APIException(code=104, msg="Only superusers can perform this action")
    update_status = await update_manager.check_for_updates(proxy=request.proxy)
    if not update_status.get("latest_version_info") and update_status.get("message"):
        return BaseResponse(code=1, msg=update_status["message"], data=update_status)
    return BaseResponse(code=0, msg="Update check complete", data=update_status)


@router.post("/system/changelogs", response_model=BaseResponse)
async def get_changelogs(
    request: UpdateCheckRequest, current_user: User = Depends(get_current_user)
):
    """
    Fetches all system changelogs from GitHub releases.
    """
    if "admin" not in current_user.roles:
        raise APIException(code=104, msg="Only superusers can perform this action")
    changelogs = await update_manager.get_changelogs(proxy=request.proxy)
    if changelogs is None:
        return BaseResponse(code=1, msg="Failed to fetch changelogs", data=[])
    return BaseResponse(code=0, msg="Changelogs fetched successfully", data=changelogs)


class ManualUpdateTags(BaseModel):
    server: str = ""
    app: str = ""
    lsp: str = ""
    web: str = ""


@router.post("/system/update", status_code=202, response_model=BaseResponse)
async def update_system(
    tags: ManualUpdateTags,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """
    Triggers a system update. Can be a general update or a manual update with specific tags.
    """
    return BaseResponse(
        code=1,
        msg="This is a testing feature, currently in development, and is not usable for now.",
    )
    if "admin" not in current_user.roles:
        raise APIException(code=104, msg="Only superusers can perform this action")

    tags_dict = tags.model_dump()
    background_tasks.add_task(update_manager.run_update_script, tags=tags_dict)
    return BaseResponse(
        code=0, msg="System update initiated. This may take a few minutes."
    )
