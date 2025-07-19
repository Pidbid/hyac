# core/docker_manager.py
import asyncio
import os
from typing import Any, Dict, List, Optional

import docker
from docker import errors
from docker.models import containers
from loguru import logger
import socket

from core.config import settings
from models import Application, Function, FunctionTemplate
from core.minio_manager import minio_manager
from core.database_dynamic import dynamic_db


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
        labels: Optional[Dict[str, str]] = None,
    ) -> Optional[containers.Container]:
        """
        Creates and returns a Docker container.

        Args:
            image: The name of the image (e.g., 'ubuntu:latest').
            name: The name of the container.
            ports: Port mappings (e.g., {'80/tcp': 8080}).
            environment: Environment variables (e.g., {'MY_VAR': 'my_value'}).
            volumes: Volume mappings (e.g., {'/host/path': {'bind': '/container/path', 'mode': 'rw'}}).
            labels: Docker labels for the container.

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
                labels=labels,
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

    def build_image(self, path: str, tag: str, target: Optional[str] = None) -> bool:
        """
        Builds a Docker image from a Dockerfile.

        Args:
            path: The path to the directory containing the Dockerfile.
            tag: The tag for the image (e.g., 'my-image:latest').
            target: The target build stage to build.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            build_kwargs = {"path": path, "tag": tag, "rm": True}
            if target:
                build_kwargs["target"] = target
            logger.info(
                f"Building image '{tag}' from path '{path}' (target: {target or 'default'})..."
            )
            self.client.images.build(**build_kwargs)
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

APP_IMAGE_NAME = "wicos/hyac_app:latest"  # Default production image
if settings.DEV_MODE:
    APP_IMAGE_NAME = "hyac_app:dev"  # Local development image

# In-memory store for running app containers. A more robust solution might use Redis.
running_apps: Dict[str, Dict[str, Any]] = {}


def find_free_port() -> int:
    """
    Finds a free port on the host machine.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def create_traefik_console_config():
    """Generates the Traefik config for the main console service."""
    domain_name = settings.DOMAIN_NAME
    if not domain_name:
        logger.warning(
            "DOMAIN_NAME not set, skipping console Traefik config generation."
        )
        return

    config_dir = "/traefik/dynamic"
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "console.yml")
    bucket_name = "console"

    config_content = f"""
http:
  routers:
    console-router:
      rule: "Host(`{bucket_name}.{domain_name}`)"
      entryPoints: ["websecure"]
      service: "console-service"
      tls:
        certResolver: "myresolver"
      middlewares:
        - "console-chain"

  services:
    console-service:
      loadBalancer:
        servers:
          - url: "http://minio:9000"

  middlewares:
    console-chain:
      chain:
        middlewares:
          - "console-headers"
          - "console-rewrite-root"
          - "console-add-prefix"
          - "console-spa"
    console-headers:
      headers:
        customRequestHeaders:
          x-amz-content-sha256: "UNSIGNED-PAYLOAD"
          Host: "minio:9000"
    console-rewrite-root:
      replacePathRegex:
        regex: "^/?$"
        replacement: "/index.html"
    console-add-prefix:
      addPrefix:
        prefix: "/{bucket_name}"
    console-spa:
      errors:
        status: ["404"]
        service: "console-service"
        query: "/{bucket_name}/index.html"
"""
    with open(config_path, "w") as f:
        f.write(config_content)
    logger.info(f"Traefik console config created at {config_path}.")


def create_traefik_web_config(app_id: str, domain_name: str):
    config_dir = (
        "/traefik/dynamic"  # This is the path accessible inside the server container
    )
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, f"web-{app_id}.yml")

    bucket_name = f"web-{app_id.lower()}"
    chain_name = f"web-chain-{app_id}"
    headers_name = f"web-headers-{app_id}"
    rewrite_name = f"web-rewrite-{app_id}"
    prefix_name = f"web-prefix-{app_id}"
    spa_name = f"web-spa-{app_id}"
    service_name = f"web-service-{app_id}"
    router_name = f"web-router-{app_id}"

    config_content = f"""
http:
  routers:
    {router_name}:
      rule: "Host(`{bucket_name}.{domain_name}`)"
      entryPoints: ["websecure"]
      service: "{service_name}"
      tls:
        certResolver: "myresolver"
      middlewares:
        - "{chain_name}"

  services:
    {service_name}:
      loadBalancer:
        servers:
          - url: "http://minio:9000"

  middlewares:
    {chain_name}:
      chain:
        middlewares:
          - "{headers_name}"
          - "{rewrite_name}"
          - "{prefix_name}"
          - "{spa_name}"
    {headers_name}:
      headers:
        customRequestHeaders:
          x-amz-content-sha256: "UNSIGNED-PAYLOAD"
          Host: "minio:9000"
    {rewrite_name}:
      replacePathRegex:
        regex: "^/?$"
        replacement: "/index.html"
    {prefix_name}:
      addPrefix:
        prefix: "/{bucket_name}"
    {spa_name}:
      errors:
        status: ["404"]
        service: "{service_name}"
        query: "/{bucket_name}/index.html"
"""
    with open(config_path, "w") as f:
        f.write(config_content)
    logger.info(f"Traefik web config for app '{app_id}' created at {config_path}.")


def remove_traefik_web_config(app_id: str):
    config_path = f"/traefik/dynamic/web-{app_id}.yml"
    if os.path.exists(config_path):
        os.remove(config_path)
        logger.info(f"Removed Traefik web config: {config_path}")


async def build_app_image_if_not_exists():
    """
    Checks if the 'hyac_app' Docker image exists, as it should be pre-built
    by docker-compose in the development environment.
    """
    if not docker_manager.client:
        logger.error("Docker client not initialized.")
        return
    try:
        docker_manager.client.images.get(APP_IMAGE_NAME)
        logger.info(f"Docker image '{APP_IMAGE_NAME}' found and ready to use.")
    except errors.ImageNotFound:
        logger.error(
            f"Docker image '{APP_IMAGE_NAME}' not found. "
            f"Please ensure it was built correctly by running 'docker-compose -f docker-compose.dev.yml build app'."
        )


async def start_app_container(app: Application) -> Optional[Dict[str, Any]]:
    """
    Starts a dedicated container for a specific application.
    """
    if not docker_manager.client:
        return None

    container_name = f"hyac-app-runtime-{app.app_id.lower()}"
    domain_name = settings.DOMAIN_NAME or "localhost"

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

    # Determine volumes based on DEV_MODE
    volumes = {}
    if settings.DEV_MODE:
        if settings.APP_CODE_PATH_ON_HOST:
            # In DEV_MODE, we mount the local app code directory into the container for hot-reloading.
            # This path should be the absolute path to the 'app' directory on the host machine.
            volumes = {
                settings.APP_CODE_PATH_ON_HOST: {
                    "bind": "/app",
                    "mode": "rw",
                }
            }
            logger.info(
                f"DEV_MODE: Mounting app code from '{os.path.abspath(settings.APP_CODE_PATH_ON_HOST)}' to '/app'."
            )
        else:
            logger.warning(
                "DEV_MODE is enabled, but APP_CODE_PATH_ON_HOST is not set. "
                "Hot-reloading for the app container will not work."
            )

    # --- Dynamic Network Attachment ---
    # Find the network of the current (server) container to attach the new app container to it.
    network_name = "hyac_network"  # Default fallback
    try:
        server_container = docker_manager.client.containers.get("hyac_server")
        # Get the first network name from the list of networks
        network_name = list(
            server_container.attrs["NetworkSettings"]["Networks"].keys()
        )[0]
        logger.info(
            f"Server container is on network '{network_name}'. Attaching app container to the same network."
        )
    except (errors.NotFound, KeyError, IndexError) as e:
        logger.warning(
            f"Could not dynamically determine server network (error: {e}). "
            f"Falling back to default network 'hyac_network'. "
            "This might fail if the project name in docker-compose is not 'hyac'."
        )

    # --- Traefik Labels for the runtime container ---
    traefik_labels = {
        "traefik.enable": "true",
        f"traefik.http.routers.{container_name}.rule": f"Host(`{app.app_id.lower()}.{domain_name}`)",
        f"traefik.http.routers.{container_name}.entrypoints": "websecure",
        f"traefik.http.routers.{container_name}.tls.certresolver": "myresolver",
        f"traefik.http.services.{container_name}.loadbalancer.server.port": "8001",
    }

    container = docker_manager.create_container(
        image=APP_IMAGE_NAME,
        name=container_name,
        environment=environment,
        network=network_name,
        volumes=volumes,
        restart=False,
        healthcheck=healthcheck,
        labels=traefik_labels,
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

    # --- New: Network Readiness Check ---
    # Even if healthy, wait for Docker's internal DNS to resolve the container name.
    logger.info(f"Verifying network readiness for container '{container_name}'...")
    network_ready = False
    for i in range(15):  # Wait for up to 15 seconds for DNS to propagate
        try:
            # This runs in a thread to avoid blocking the async event loop.
            await asyncio.to_thread(socket.gethostbyname, container_name)
            logger.info(
                f"Successfully resolved hostname for '{container_name}'. Network is ready."
            )
            network_ready = True
            break
        except socket.gaierror:
            logger.warning(
                f"DNS resolution for '{container_name}' failed. Retrying... (Attempt {i+1}/15)"
            )
            await asyncio.sleep(1)

    if not network_ready:
        logger.error(
            f"Could not resolve hostname for '{container_name}' after multiple attempts. Aborting."
        )
        await docker_manager.stop_container(container_name)
        await docker_manager.remove_container(container_name)
        return None

    # Initialize function templates for the newly created app
    from core.initialization import create_function_templates_for_app

    await create_function_templates_for_app(app.app_id)

    # Create Traefik config for web hosting
    create_traefik_web_config(app.app_id, domain_name)

    container_info = {
        "name": container_name,
        "id": container.id,
    }
    running_apps[app.app_id] = container_info
    logger.info(f"Started container for app '{app.app_id}'. Traefik proxy configured.")
    return container_info


async def stop_app_container(app_id: str):
    """
    Stops and removes the container for a specific application.
    """
    if app_id in running_apps:
        container_name = running_apps[app_id]["name"]
        logger.info(f"Stopping container for app '{app_id}'...")
        if await docker_manager.stop_container(container_name):
            await docker_manager.remove_container(container_name)

        # Remove Traefik web config file
        remove_traefik_web_config(app_id)

        del running_apps[app_id]
        logger.info(
            f"Container for app '{app_id}' stopped and removed. Traefik proxy updated."
        )


async def delete_application_background(app: Application):
    """
    Performs all deletion operations in the background.
    """
    logger.info(f"Starting background deletion for app '{app.app_name}' ({app.app_id})")

    # 1. Cancel any pending startup tasks for this app
    from models.tasks_model import Task, TaskAction, TaskStatus

    try:
        pending_start_tasks = await Task.find(
            {"payload.app_id": app.app_id, "action": TaskAction.START_APP}
        ).to_list()

        if pending_start_tasks:
            for task in pending_start_tasks:
                await task.delete()
                logger.info(
                    f"Deleted pending start task '{task.task_id}' for app '{app.app_id}'."
                )
    except Exception as e:
        logger.error(f"Error deleting pending start tasks for app '{app.app_id}': {e}")

    # 2. Stop and remove the application container
    try:
        await stop_app_container(app.app_id)
        logger.info(f"Container for app '{app.app_id}' stopped and removed.")
    except Exception as e:
        logger.error(f"Error stopping container for app '{app.app_id}': {e}")

    # 3. Delete all functions associated with the application
    try:
        functions_to_delete = await Function.find(
            Function.app_id == app.app_id
        ).to_list()
        for func in functions_to_delete:
            await func.delete()
        logger.info(
            f"Deleted {len(functions_to_delete)} functions for app '{app.app_id}'."
        )
    except Exception as e:
        logger.error(f"Error deleting functions for app '{app.app_id}': {e}")

    # 4. Delete all function templates associated with the application
    try:
        templates_to_delete = await FunctionTemplate.find(
            FunctionTemplate.app_id == app.app_id
        ).to_list()
        for template in templates_to_delete:
            await template.delete()
        logger.info(
            f"Deleted {len(templates_to_delete)} function templates for app '{app.app_id}'."
        )
    except Exception as e:
        logger.error(f"Error deleting function templates for app '{app.app_id}': {e}")

    # 5. Delete MinIO buckets
    try:
        # Delete the main app bucket
        bucket_name = app.app_id.lower()
        if await minio_manager.bucket_exists(bucket_name):
            objects = await minio_manager.list_objects(bucket_name, recursive=True)
            if objects:
                for obj in objects:
                    await minio_manager.delete_object(bucket_name, obj["name"])
            await minio_manager.remove_bucket(bucket_name)
            logger.info(f"Deleted MinIO bucket '{bucket_name}'.")

        # Delete the web hosting bucket
        web_bucket_name = f"web-{app.app_id.lower()}"
        if await minio_manager.bucket_exists(web_bucket_name):
            objects = await minio_manager.list_objects(web_bucket_name, recursive=True)
            if objects:
                for obj in objects:
                    await minio_manager.delete_object(web_bucket_name, obj["name"])
            await minio_manager.remove_bucket(web_bucket_name)
            logger.info(f"Deleted MinIO bucket '{web_bucket_name}'.")

        # Also remove the web hosting Traefik config
        remove_traefik_web_config(app.app_id)

    except Exception as e:
        logger.error(f"Error deleting MinIO buckets for app '{app.app_id}': {e}")

    # 6. Drop the application's dedicated database
    try:
        await dynamic_db.db_client.drop_database(app.app_id)
        logger.info(f"Dropped database '{app.app_id}'.")
    except Exception as e:
        logger.error(f"Error dropping database for app '{app.app_id}': {e}")

    # 7. Delete the application document itself
    try:
        await app.delete()
        logger.info(f"Deleted application document for '{app.app_name}'.")
    except Exception as e:
        logger.error(f"Error deleting application document for '{app.app_name}': {e}")

    logger.info(f"Background deletion for app '{app.app_name}' completed.")
