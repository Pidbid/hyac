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

    def stop_container(self, name: str) -> bool:
        """
        Stops a Docker container.

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
            container.stop()
            logger.info(f"Container '{name}' stopped.")
            return True
        except errors.NotFound:
            logger.warning(f"Container '{name}' not found.")
        except errors.APIError as e:
            logger.error(f"Failed to stop container '{name}': {e}")
        return False

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

    def remove_container(self, name: str, force: bool = False) -> bool:
        """
        Removes a Docker container.

        Args:
            name: The name of the container.
            force: Whether to force removal even if the container is running.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            container = self.client.containers.get(name)
            container.remove(force=force)
            logger.info(f"Container '{name}' removed.")
            return True
        except errors.NotFound:
            logger.warning(f"Container '{name}' not found.")
        except errors.APIError as e:
            logger.error(f"Failed to remove container '{name}': {e}")
        return False

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
    Reloads the Nginx configuration gracefully, with a fallback to restarting the container.
    """
    if not docker_manager.client:
        return False

    try:
        nginx_container = docker_manager.client.containers.get("hyac_nginx")
        domain_to_check = f"{target_appid.lower()}.{settings.DOMAIN_NAME}"

        # 1. Test the new configuration syntax
        test_exit_code, test_output = nginx_container.exec_run("nginx -t")
        if test_exit_code != 0:
            logger.error(
                f"Nginx configuration test failed: {test_output.decode('utf-8')}"
            )
            return False
        logger.info("Nginx configuration test successful.")

        # 2. Attempt to gracefully reload Nginx
        reload_exit_code, reload_output = nginx_container.exec_run("nginx -s reload")
        if reload_exit_code != 0:
            logger.warning(
                f"Nginx reload command failed: {reload_output.decode('utf-8')}. "
                "Will try restarting the container."
            )
        else:
            logger.info("Nginx reload command sent successfully.")
            await asyncio.sleep(2)  # Give Nginx a moment to reload

        # 3. Verify that the new configuration is active
        if target_appid:
            verify_exit_code, verify_output = nginx_container.exec_run("nginx -T")
            if verify_exit_code == 0 and domain_to_check in verify_output.decode(
                "utf-8"
            ):
                logger.info(
                    f"Nginx configuration for '{domain_to_check}' verified successfully after reload."
                )
                return True
            else:
                logger.warning(
                    f"Configuration for '{domain_to_check}' not found after reload. "
                    "Proceeding to restart Nginx container."
                )

        # 4. If reload failed or verification didn't pass, restart the container
        logger.info("Restarting Nginx container to apply new configuration...")
        if not docker_manager.restart_container("hyac_nginx"):
            logger.error("Failed to restart Nginx container.")
            return False

        await asyncio.sleep(2)  # Wait for Nginx to initialize after restart

        # 5. Final verification after restart
        if target_appid:
            final_verify_exit, final_verify_output = nginx_container.exec_run(
                "nginx -T"
            )
            if (
                final_verify_exit == 0
                and domain_to_check in final_verify_output.decode("utf-8")
            ):
                logger.info(
                    f"Nginx configuration for '{domain_to_check}' verified successfully after restart."
                )
                return True
            else:
                logger.error(
                    f"Failed to verify Nginx configuration for '{domain_to_check}' even after restart."
                )
                return False

        logger.info("Nginx container restarted and configuration reloaded.")
        return True

    except errors.NotFound:
        logger.error("Nginx container 'hyac_nginx' not found.")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred while reloading Nginx: {e}")
        return False


def create_app_nginx_config(app_id: str, container_name: str):
    """
    Creates a specific Nginx server block for an application with SSL.
    """
    """
    server {{
        # Listen to port 443 on both IPv4 and IPv6.
        listen 443 ssl;
        listen [::]:443 ssl;

        # Domain names this server should respond to.
        server_name {server_name};

        # Load the certificate files.
        ssl_certificate         /etc/letsencrypt/live/{server_name}/fullchain.pem;
        ssl_certificate_key     /etc/letsencrypt/live/{server_name}/privkey.pem;
        ssl_trusted_certificate /etc/letsencrypt/live/{server_name}/chain.pem;

        # Load the Diffie-Hellman parameter.
        ssl_dhparam /etc/letsencrypt/dhparams/dhparam.pem;

        location / {{
            proxy_pass http://{container_name}:8001;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # WebSocket support
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }}
    }}
    """
    domain_name = settings.DOMAIN_NAME or "localhost"
    server_name = f"{app_id}.{domain_name}"

    config_content = f"""server {{
    listen 80;
    listen [::]:80;

    server_name {server_name.lower()};

    location / {{
        proxy_pass http://{container_name}:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}"""

    try:
        config_path = f"/server/nginx/conf.d/app-{app_id.lower()}.conf"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)
        logger.info(f"Nginx config for app '{app_id}' created at {config_path}.")
        return True
    except IOError as e:
        logger.error(f"Failed to write Nginx config for app '{app_id}': {e}")
        return False


def remove_app_nginx_config(app_id: str):
    """
    Removes the Nginx configuration file for an application.
    """
    import os

    try:
        config_path = f"/server/nginx/conf.d/app-{app_id}.conf"
        if os.path.exists(config_path):
            os.remove(config_path)
            logger.info(f"Nginx config for app '{app_id}' removed.")
        return True
    except IOError as e:
        logger.error(f"Failed to remove Nginx config for app '{app_id}': {e}")
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
    if docker_manager.stop_container(container_name):
        docker_manager.remove_container(container_name)

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
        docker_manager.stop_container(container_name)
        docker_manager.remove_container(container_name)
        return None

    # Create and reload Nginx config now that the service is confirmed to be up
    if create_app_nginx_config(app.app_id, container_name):
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
            # Rollback: remove config and container
            remove_app_nginx_config(app.app_id)
            docker_manager.stop_container(container_name)
            docker_manager.remove_container(container_name)
            return None

    return None


async def stop_app_container(app_id: str):
    """
    Stops and removes the container for a specific application.
    """
    if app_id in running_apps:
        container_name = running_apps[app_id]["name"]
        logger.info(f"Stopping container for app '{app_id}'...")
        if docker_manager.stop_container(container_name):
            docker_manager.remove_container(container_name)

        # Remove Nginx config and reload
        if remove_app_nginx_config(app_id):
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
