# core/docker_manager.py
import asyncio
import os
from typing import Any, Dict, List, Optional
import time

import docker
from docker import errors
from docker.models import containers
from loguru import logger
import socket

from core.config import settings
from models import Application, Function
from core.minio_manager import minio_manager
from core.database_dynamic import dynamic_db
from core.cache import code_cache


class DockerManager:
    """
    A manager for handling Docker operations such as creating, starting, stopping,
    and removing containers.
    """

    def __init__(self):
        """
        Initializes the Docker client from environment variables.
        """
        try:
            self.client = docker.from_env()
            logger.info("Docker client initialized successfully.")
        except errors.DockerException as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self.client = None

    def _check_client(self) -> bool:
        """
        Checks if the Docker client is initialized.
        """
        if not self.client:
            logger.error(
                "Docker client is not initialized. Cannot perform Docker operations."
            )
            return False
        return True

    def create_container(
        self,
        image: str,
        name: str,
        ports: Optional[Dict[str, Any]] = None,
        environment: Optional[Dict[str, str]] = None,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        network: Optional[str] = None,
        restart: bool = False,
        healthcheck: Optional[Dict[str, Any]] = None,
    ) -> Optional[containers.Container]:
        """
        Creates and returns a Docker container.

        Args:
            image: The name of the image (e.g., 'ubuntu:latest').
            name: The name of the container.
            ports: Port mappings (e.g., {'80/tcp': 8080}).
            environment: Environment variables (e.g., {'MY_VAR': 'my_value'}).
            volumes: Volume mappings (e.g., {'/host/path': {'bind': '/container/path', 'mode': 'rw'}}).

        Returns:
            The created container object, or None if creation fails.
        """
        if not self._check_client():
            return None
        assert self.client is not None
        try:
            container = self.client.containers.create(
                image=image,
                name=name,
                ports=ports,
                environment=environment,
                volumes=volumes,
                network=network,
                healthcheck=healthcheck,
                detach=True,
                restart_policy=(
                    {"Name": "always", "MaximumRetryCount": 0}
                    if restart
                    else {"Name": "unless-stopped"}
                ),
            )
            logger.info(f"Container '{name}' created from image '{image}'.")
            return container
        except errors.ImageNotFound:
            logger.error(f"Image '{image}' not found.")
        except errors.APIError as e:
            logger.error(f"Failed to create container '{name}': {e}")
        return None

    def start_container(self, name: str) -> bool:
        """
        Starts a Docker container.

        Args:
            name: The name of the container.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            container = self.client.containers.get(name)
            container.start()
            logger.info(f"Container '{name}' started.")
            return True
        except errors.NotFound:
            logger.warning(f"Container '{name}' not found.")
        except errors.APIError as e:
            logger.error(f"Failed to start container '{name}': {e}")
        return False

    async def stop_container(self, name: str) -> bool:
        """
        Stops a Docker container asynchronously.

        Args:
            name: The name of the container.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None

        def _stop():
            try:
                container = self.client.containers.get(name)
                if container.status == "exited":
                    logger.info(f"Container '{name}' is already stopped.")
                    return True
                container.stop()
                logger.info(f"Container '{name}' stopped.")
                return True
            except errors.NotFound:
                logger.info(f"Container '{name}' not found, consider it as stopped.")
                return True  # Success if not found
            except errors.APIError as e:
                logger.error(f"Failed to stop container '{name}': {e}")
                return False

        return await asyncio.to_thread(_stop)

    async def restart_container(self, name: str) -> bool:
        """
        Restarts a Docker container.

        Args:
            name: The name of the container.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            container = self.client.containers.get(name)
            container.restart()
            # Wait for the container to be in 'running' state
            restarted_container = self.client.containers.get(name)
            while restarted_container.status != "running":
                await asyncio.sleep(0.5)
                restarted_container.reload()  # Refresh container state
            logger.info(f"Container '{name}' restarted.")
            return True
        except errors.NotFound:
            logger.warning(f"Container '{name}' not found.")
        except errors.APIError as e:
            logger.error(f"Failed to restart container '{name}': {e}")
        return False

    async def remove_container(self, name: str, force: bool = False) -> bool:
        """
        Removes a Docker container asynchronously.

        Args:
            name: The name of the container.
            force: Whether to force removal even if the container is running.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None

        def _remove():
            try:
                container = self.client.containers.get(name)
                container.remove(force=force)
                logger.info(f"Container '{name}' removed.")
                return True
            except errors.NotFound:
                logger.info(f"Container '{name}' not found, consider it as removed.")
                return True  # Success if not found
            except errors.APIError as e:
                logger.error(f"Failed to remove container '{name}': {e}")
                return False

        return await asyncio.to_thread(_remove)

    def list_containers(self, all: bool = False) -> List[Dict]:
        """
        Lists Docker containers.

        Args:
            all: Whether to list all containers (including stopped ones).

        Returns:
            A list of dictionaries, where each dictionary represents a container.
        """
        if not self._check_client():
            return []
        assert self.client is not None
        try:
            containers_list = self.client.containers.list(all=all)
            result_list = []
            for container in containers_list:
                health_status = None
                try:
                    health_status = container.attrs["State"]["Health"]["Status"]
                except (KeyError, AttributeError):
                    # Container might not have a health check configured
                    pass

                result_list.append(
                    {
                        "id": container.id,
                        "name": container.name,
                        "image": (
                            container.image.tags[0] if container.image.tags else ""
                        ),
                        "status": container.status,
                        "health_status": health_status,
                        "ports": container.ports,
                        "labels": container.labels,
                        "short_id": container.short_id,
                    }
                )
            logger.debug(f"Listed {len(result_list)} Docker containers.")
            return result_list
        except errors.APIError as e:
            logger.error(f"Failed to list containers: {e}")
        return []

    def build_image(self, path: str, tag: str) -> bool:
        """
        Builds a Docker image from a Dockerfile.

        Args:
            path: The path to the directory containing the Dockerfile.
            tag: The tag for the image (e.g., 'my-image:latest').

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            logger.info(f"Building image '{tag}' from path '{path}'...")
            self.client.images.build(path=path, tag=tag, rm=True)
            logger.info(f"Image '{tag}' built successfully.")
            return True
        except errors.BuildError as e:
            logger.error(f"Failed to build image '{tag}': {e}")
            for line in e.build_log:
                if "stream" in line:
                    logger.error(line["stream"].strip())
        except errors.APIError as e:
            logger.error(f"Failed to build image '{tag}': {e}")
        return False

    def exec_in_container(self, container_name: str, command: str) -> tuple[int, str]:
        """
        Executes a command inside a running container.

        Args:
            container_name: The name of the container.
            command: The command to execute.

        Returns:
            A tuple containing the exit code and the output string.
        """
        if not self._check_client():
            return -1, "Docker client not initialized."
        assert self.client is not None
        try:
            container = self.client.containers.get(container_name)
            exit_code, output = container.exec_run(command)
            return exit_code, output.decode("utf-8")
        except errors.NotFound:
            logger.warning(f"Container '{container_name}' not found for exec command.")
            return -1, f"Container '{container_name}' not found."
        except errors.APIError as e:
            logger.error(f"Failed to execute command in '{container_name}': {e}")
            return -1, str(e)


docker_manager = DockerManager()

# --- FaaS Specific High-Level Functions ---

APP_IMAGE_NAME = "hyac_app:latest"
# In-memory store for running app containers. A more robust solution might use Redis.
running_apps: Dict[str, Dict[str, Any]] = {}


def find_free_port() -> int:
    """
    Finds a free port on the host machine.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


async def reload_nginx(target_appid: str = "") -> bool:
    """
    Reloads the Nginx configuration gracefully, ensuring the config file exists first.
    """
    if not docker_manager.client:
        return False

    try:
        nginx_container = docker_manager.client.containers.get("hyac_nginx")
        config_filename = f"app-{target_appid.lower()}.conf"
        config_path_in_container = f"/etc/nginx/user_conf.d/{config_filename}"

        # 1. Poll to ensure the config file exists inside the Nginx container.
        # This prevents race conditions with volume mounts.
        file_exists = False
        for i in range(5):  # Poll for up to 5 seconds
            exit_code, _ = nginx_container.exec_run(
                f"test -f {config_path_in_container}"
            )
            if exit_code == 0:
                logger.info(
                    f"Nginx config '{config_filename}' found in container (Attempt {i+1}/5)."
                )
                file_exists = True
                break
            logger.info(
                f"Waiting for Nginx config '{config_filename}' to appear in container... (Attempt {i+1}/5)"
            )
            await asyncio.sleep(1)

        if not file_exists:
            logger.error(
                f"Nginx config '{config_filename}' did not appear in container after waiting."
            )
            return False

        # 2. Test the new configuration syntax.
        test_exit_code, test_output = nginx_container.exec_run("nginx -t")
        if test_exit_code != 0:
            logger.error(
                f"Nginx configuration test failed: {test_output.decode('utf-8')}"
            )
            return False
        logger.info("Nginx configuration test successful.")

        # 3. Send SIGHUP to trigger a live reload.
        logger.info("Sending SIGHUP signal to Nginx for a live reload...")
        nginx_container.kill(signal="SIGHUP")
        await asyncio.sleep(2)  # Give Nginx a moment to reload

        logger.info("Nginx reloaded successfully.")
        return True

    except errors.NotFound:
        logger.error("Nginx container 'hyac_nginx' not found.")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred while reloading Nginx: {e}")
        return False


async def create_app_nginx_config(app_id: str, container_name: str) -> bool:
    """
    Creates an Nginx server block and its symbolic link for a dynamic application.
    """
    domain_name = settings.DOMAIN_NAME or "localhost"
    server_name = f"{app_id.lower()}.{domain_name}"
    config_filename = f"app-{app_id.lower()}.conf"
    real_config_path = f"/server/nginx/conf.d/{config_filename}"
    user_conf_path = f"/etc/nginx/user_conf.d/{config_filename}"
    symlink_path = f"/etc/nginx/conf.d/{config_filename}"

    config_content = f"""server {{
    listen 80;
    listen [::]:80;
    server_name {server_name};

    location / {{
        proxy_pass http://{container_name}:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}"""

    # 1. Write the actual config file to the volume shared with the server container.
    try:
        with open(real_config_path, "w", encoding="utf-8") as f:
            f.write(config_content)
        logger.info(f"Nginx config for app '{app_id}' created at {real_config_path}.")
    except IOError as e:
        logger.error(f"Failed to write Nginx config for app '{app_id}': {e}")
        return False

    # 2. Manually create the symbolic link inside the Nginx container.
    # This is necessary because the `jonasal/nginx-certbot` image only creates symlinks on startup.
    symlink_command = f"ln -s {user_conf_path} {symlink_path}"
    exit_code, output = await asyncio.to_thread(
        docker_manager.exec_in_container, "hyac_nginx", symlink_command
    )

    if exit_code == 0:
        logger.info(
            f"Successfully created symlink for '{config_filename}' in Nginx container."
        )
        return True
    else:
        # If the link already exists, it's not a critical error.
        if "File exists" in output:
            logger.warning(f"Symlink for '{config_filename}' already exists.")
            return True
        logger.error(
            f"Failed to create symlink for '{config_filename}'. Exit code: {exit_code}, Output: {output}"
        )
        return False


async def remove_app_nginx_config(app_id: str) -> bool:
    """
    Removes the Nginx config file and its symbolic link for an application.
    """
    config_filename = f"app-{app_id.lower()}.conf"
    real_config_path = f"/server/nginx/conf.d/{config_filename}"
    symlink_path = f"/etc/nginx/conf.d/{config_filename}"

    # 1. Remove the symbolic link from inside the Nginx container.
    unlink_command = f"rm {symlink_path}"
    exit_code, output = await asyncio.to_thread(
        docker_manager.exec_in_container, "hyac_nginx", unlink_command
    )
    if exit_code != 0 and "No such file or directory" not in output:
        logger.error(
            f"Failed to remove symlink '{symlink_path}'. Exit code: {exit_code}, Output: {output}"
        )
        # Continue to attempt to delete the real file anyway.
    else:
        logger.info(f"Successfully removed symlink for '{config_filename}'.")

    # 2. Remove the actual config file.
    try:
        if os.path.exists(real_config_path):
            os.remove(real_config_path)
            logger.info(f"Nginx config file '{real_config_path}' removed.")
        return True
    except IOError as e:
        logger.error(f"Failed to remove Nginx config file '{real_config_path}': {e}")
        return False


async def build_app_image_if_not_exists():
    """
    Builds the 'hyac_app' Docker image if it doesn't already exist.
    """
    if not docker_manager.client:
        logger.error("Docker client not initialized.")
        return
    try:
        docker_manager.client.images.get(APP_IMAGE_NAME)
        logger.info(f"Docker image '{APP_IMAGE_NAME}' already exists.")
    except errors.ImageNotFound:
        logger.warning(f"Docker image '{APP_IMAGE_NAME}' not found. Building...")
        # Assuming the build context is the project root.
        docker_manager.build_image(path=".", tag=APP_IMAGE_NAME)


async def start_app_container(app: Application) -> Optional[Dict[str, Any]]:
    """
    Starts a dedicated container for a specific application.
    """
    if not docker_manager.client:
        return None

    container_name = f"hyac-app-runtime-{app.app_id.lower()}"

    # Check if container is already running
    if app.app_id in running_apps:
        logger.info(f"Container for app '{app.app_id}' is already running.")
        return running_apps[app.app_id]

    # Stop and remove any stale container with the same name
    if await docker_manager.stop_container(container_name):
        await docker_manager.remove_container(container_name)

    # When running inside Docker, the app container needs to connect to other services
    # using their service names as hostnames.
    environment = {
        "APP_ID": app.app_id,  # Pass the app_id to the container
        "MONGODB_USERNAME": settings.MONGODB_USERNAME,
        "MONGODB_PASSWORD": settings.MONGODB_PASSWORD,
        "MINIO_ACCESS_KEY": settings.MINIO_ACCESS_KEY,
        "MINIO_SECRET_KEY": settings.MINIO_SECRET_KEY,
        "SECRET_KEY": settings.SECRET_KEY,
        "DEV_MODE": settings.DEV_MODE,
        "DEBUG": True,
    }

    # Add user-defined environment variables
    for env_var in app.environment_variables:
        environment[env_var.key] = env_var.value

    # Define the healthcheck for the app container
    healthcheck = {
        "test": ["CMD", "curl", "-f", "http://localhost:8001/__runtime_health__"],
        "interval": 10 * 1000000000,  # 10 seconds
        "timeout": 5 * 1000000000,  # 5 seconds
        "retries": 5,
        "start_period": 15 * 1000000000,  # 15-second grace period
    }

    container = docker_manager.create_container(
        image=APP_IMAGE_NAME,
        name=container_name,
        environment=environment,
        network="hyac_hyac_network",
        volumes={},
        restart=False,
        healthcheck=healthcheck,
    )
    if not container or not docker_manager.start_container(container_name):
        return None

    # New health check logic based on Docker's health status
    is_ready = False
    logger.info(f"Waiting for container '{container_name}' to become healthy...")
    for i in range(30):  # Wait for up to 60 seconds
        try:
            container.reload()
            health_status = container.attrs["State"]["Health"]["Status"]
            logger.info(
                f"Container '{container_name}' health status: {health_status} (Attempt {i+1}/30)"
            )
            if health_status == "healthy":
                logger.info(f"Container '{container_name}' is healthy.")
                is_ready = True
                break
            elif health_status == "unhealthy":
                logger.error(f"Container '{container_name}' is unhealthy. Aborting.")
                is_ready = False
                break
            # If status is 'starting', continue waiting
            await asyncio.sleep(2)
        except KeyError:
            # This can happen if the health status is not yet available
            logger.info(
                f"Health status for '{container_name}' not available yet. Waiting... (Attempt {i+1}/30)"
            )
            await asyncio.sleep(2)
        except errors.NotFound:
            logger.error(f"Container '{container_name}' not found during health check.")
            return None

    if not is_ready:
        logger.error(f"Container '{container_name}' did not become healthy in time.")
        await docker_manager.stop_container(container_name)
        await docker_manager.remove_container(container_name)
        return None

    # Create and reload Nginx config now that the service is confirmed to be up
    if await create_app_nginx_config(app.app_id, container_name):
        reload_success = False
        for i in range(3):  # Retry up to 3 times
            logger.info(f"Attempting to reload Nginx (Attempt {i+1}/3)...")
            if await reload_nginx(app.app_id):
                reload_success = True
                break
            logger.warning(
                f"Nginx reload attempt {i+1}/3 failed. Retrying in 3 seconds..."
            )
            await asyncio.sleep(3)

        if reload_success:
            container_info = {
                "name": container_name,
                "id": container.id,
            }
            running_apps[app.app_id] = container_info
            logger.info(
                f"Started container for app '{app.app_id}'. Nginx proxy configured."
            )
            return container_info
        else:
            logger.error(
                f"Failed to reload Nginx for app '{app.app_id}' after multiple attempts. Rolling back..."
            )
            # Rollback: stop and remove the container, but keep the Nginx config for debugging
            await docker_manager.stop_container(container_name)
            await docker_manager.remove_container(container_name)
            # We don't remove the nginx config here, to allow for debugging.
            # It will be cleaned up when the app is properly deleted.
            return None

    return None


async def stop_app_container(app_id: str):
    """
    Stops and removes the container for a specific application.
    """
    if app_id in running_apps:
        container_name = running_apps[app_id]["name"]
        logger.info(f"Stopping container for app '{app_id}'...")
        if await docker_manager.stop_container(container_name):
            await docker_manager.remove_container(container_name)

        # Remove Nginx config and reload
        if await remove_app_nginx_config(app_id):
            await reload_nginx()

        del running_apps[app_id]
        logger.info(
            f"Container for app '{app_id}' stopped and removed. Nginx proxy updated."
        )


async def delete_application_background(app: Application):
    """
    Performs all deletion operations in the background.
    """
    logger.info(f"Starting background deletion for app '{app.app_name}' ({app.app_id})")

    # 1. Stop and remove the application container
    try:
        await stop_app_container(app.app_id)
        logger.info(f"Container for app '{app.app_id}' stopped and removed.")
    except Exception as e:
        logger.error(f"Error stopping container for app '{app.app_id}': {e}")

    # 2. Delete all functions associated with the application
    try:
        functions_to_delete = await Function.find(
            Function.app_id == app.app_id
        ).to_list()
        for func in functions_to_delete:
            code_cache.invalidate(func.app_id, func.function_id)
            await func.delete()
        logger.info(
            f"Deleted {len(functions_to_delete)} functions for app '{app.app_id}'."
        )
    except Exception as e:
        logger.error(f"Error deleting functions for app '{app.app_id}': {e}")

    # 3. Delete MinIO buckets
    try:
        # Delete the main app bucket
        bucket_name = app.app_id
        if await minio_manager.bucket_exists(bucket_name):
            objects = await minio_manager.list_objects(bucket_name, recursive=True)
            if objects:
                for obj in objects:
                    await minio_manager.delete_object(bucket_name, obj["name"])
            await minio_manager.remove_bucket(bucket_name)
            logger.info(f"Deleted MinIO bucket '{bucket_name}'.")

        # Delete the web hosting bucket
        web_bucket_name = f"web_{app.app_id}"
        if await minio_manager.bucket_exists(web_bucket_name):
            objects = await minio_manager.list_objects(web_bucket_name, recursive=True)
            if objects:
                for obj in objects:
                    await minio_manager.delete_object(web_bucket_name, obj["name"])
            await minio_manager.remove_bucket(web_bucket_name)
            logger.info(f"Deleted MinIO bucket '{web_bucket_name}'.")
    except Exception as e:
        logger.error(f"Error deleting MinIO buckets for app '{app.app_id}': {e}")

    # 4. Drop the application's dedicated database
    try:
        await dynamic_db.db_client.drop_database(app.app_id)
        logger.info(f"Dropped database '{app.app_id}'.")
    except Exception as e:
        logger.error(f"Error dropping database for app '{app.app_id}': {e}")

    # 5. Delete the application document itself
    try:
        await app.delete()
        logger.info(f"Deleted application document for '{app.app_name}'.")
    except Exception as e:
        logger.error(f"Error deleting application document for '{app.app_name}': {e}")

    logger.info(f"Background deletion for app '{app.app_name}' completed.")
