# core/runtime_status_manager.py
from loguru import logger
from typing import List

from core.docker_manager import docker_manager
from models.applications_model import Application, ApplicationStatus


async def sync_runtime_status():
    """
    Synchronizes the status of applications with the status of their corresponding
    Docker containers using Docker's native health check status.
    """
    # logger.info(
    #     "Starting runtime status synchronization based on Docker health checks..."
    # )
    try:
        # 1. Get all containers from Docker, including their health status
        all_containers = docker_manager.list_containers(all=True)
        container_info_map = {c["name"]: c for c in all_containers}

        # 2. Get all applications from the database
        all_apps: List[Application] = await Application.find_all().to_list()

        # 3. Iterate through applications and update their status
        for app in all_apps:
            # If the application is in a transitional state, skip synchronization
            # to allow the task worker to complete its operation.
            if app.status in [
                ApplicationStatus.STOPPING,
                ApplicationStatus.STOPPED,
                ApplicationStatus.DELETING,
            ]:
                logger.debug(
                    f"Skipping sync for app '{app.app_name}' (ID: {app.app_id}) because its status is '{app.status}'."
                )
                continue

            container_name = f"hyac-app-runtime-{app.app_id.lower()}"
            container_info = container_info_map.get(container_name)

            new_status: ApplicationStatus

            if container_info:
                # Container exists, determine status from its state and health
                docker_status = container_info.get("status")
                health_status = container_info.get("health_status")

                if docker_status == "running":
                    if health_status == "healthy":
                        new_status = ApplicationStatus.RUNNING
                    elif health_status == "unhealthy":
                        logger.warning(
                            f"Container '{container_name}' is running but unhealthy."
                        )
                        new_status = ApplicationStatus.ERROR
                    else:  # 'starting' or None
                        new_status = ApplicationStatus.STARTING
                elif docker_status in ["created", "restarting"]:
                    new_status = ApplicationStatus.STARTING
                else:  # 'exited', 'dead', 'paused'
                    new_status = ApplicationStatus.STOPPED
            else:
                # Container does not exist
                new_status = ApplicationStatus.STOPPED

            # 4. Update status in the database if it has changed
            if app.status != new_status:
                await app.set({Application.status: new_status})
                logger.info(
                    f"Application '{app.app_name}' (ID: {app.app_id}) status changed from '{app.status}' to '{new_status}'."
                )

        # logger.info("Runtime status synchronization finished successfully.")

    except Exception as e:
        logger.error(f"An error occurred during runtime status synchronization: {e}")
