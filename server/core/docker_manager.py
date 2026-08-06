# core/docker_manager.py
import asyncio
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import docker
from docker import errors
from docker.models import containers
from loguru import logger
import socket

from core.config import settings
from models import (
    Application,
    Function,
    FunctionTemplate,
    StorageStatus,
)
from models.applications_model import ApplicationStatus
from models.tasks_model import Task, TaskStatus
from core.app_storage import app_storage_service
from core.database import mongodb_manager
from core.database_dynamic import dynamic_db
from core.environment_contract import LEGACY_PLATFORM_ENV_KEYS, RESERVED_ENV_KEYS


GENERIC_RUNTIME_OWNER_LEASE_SECONDS = 120


def runtime_container_matches_ingress(container: Dict[str, Any], app_id: str) -> bool:
    """Return whether an observed runtime still targets the configured domain."""
    container_name = f"hyac-app-runtime-{app_id.lower()}"
    rule_key = f"traefik.http.routers.{container_name}.rule"
    labels = container.get("labels") or {}
    observed_rule = labels.get(rule_key)
    if observed_rule is None:
        # Some test doubles and legacy inventories do not expose labels. Other
        # runtime checks remain authoritative for those observations.
        return True
    domain_name = settings.DOMAIN_NAME or "localhost"
    return observed_rule == f"Host(`{app_id.lower()}.{domain_name}`)"


def _runtime_owner_deadline() -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        seconds=GENERIC_RUNTIME_OWNER_LEASE_SECONDS
    )


def _available_generic_runtime_owner_query(now: datetime) -> dict:
    """Match an unused, expired, or pre-expiry generic owner slot."""
    return {
        "runtime_cleanup_task_id": None,
        "$or": [
            {
                "runtime_cleanup_lease_owner": None,
            },
            {
                "runtime_cleanup_lease_expires_at": {"$lte": now},
            },
            {
                "runtime_cleanup_lease_expires_at": None,
            },
        ]
    }


def generic_runtime_owner_is_expired(application: Application) -> bool:
    owner = getattr(application, "runtime_cleanup_lease_owner", None)
    if not owner or getattr(application, "runtime_cleanup_task_id", None) is not None:
        return False
    expires_at = getattr(
        application, "runtime_cleanup_lease_expires_at", None
    )
    if expires_at is None:
        return True
    now = datetime.now(
        expires_at.tzinfo if getattr(expires_at, "tzinfo", None) else None
    )
    return expires_at <= now


async def clear_expired_generic_runtime_owner(application: Application) -> bool:
    """Clear only the exact expired generic claim observed by the caller."""
    if not generic_runtime_owner_is_expired(application):
        return False
    owner = application.runtime_cleanup_lease_owner
    expires_at = getattr(application, "runtime_cleanup_lease_expires_at", None)
    query = {
        "app_id": application.app_id,
        "runtime_generation": application.runtime_generation,
        "runtime_cleanup_task_id": None,
        "runtime_cleanup_lease_owner": owner,
    }
    if expires_at is None:
        query["runtime_cleanup_lease_expires_at"] = None
    else:
        comparison_now = datetime.now(
            expires_at.tzinfo if getattr(expires_at, "tzinfo", None) else None
        )
        query["runtime_cleanup_lease_expires_at"] = {"$lte": comparison_now}
    result = await mongodb_manager.get_collection(Application).update_one(
        query,
        {
            "$set": {
                "runtime_cleanup_lease_owner": None,
                "runtime_cleanup_lease_expires_at": None,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    if result.matched_count:
        application.runtime_cleanup_lease_owner = None
        application.runtime_cleanup_lease_expires_at = None
        return True
    return False


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
        mem_limit: Optional[str] = None,
        nano_cpus: Optional[int] = None,
        pids_limit: Optional[int] = None,
        read_only: bool = False,
        tmpfs: Optional[Dict[str, str]] = None,
        cap_drop: Optional[List[str]] = None,
        security_opt: Optional[List[str]] = None,
        user: Optional[str] = None,
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
                mem_limit=mem_limit,
                nano_cpus=nano_cpus,
                pids_limit=pids_limit,
                read_only=read_only,
                tmpfs=tmpfs,
                cap_drop=cap_drop,
                security_opt=security_opt,
                user=user,
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
                if container.status in {"created", "exited", "dead"}:
                    logger.info(f"Container '{name}' is already stopped.")
                    return True
                container.stop()
                logger.info(f"Container '{name}' stopped.")
                return True
            except errors.NotFound:
                logger.info(f"Container '{name}' not found, consider it as stopped.")
                return True  # Success if not found
            except errors.APIError as e:
                if e.status_code == 304:
                    logger.info(f"Container '{name}' is already stopped.")
                    return True
                logger.error(f"Failed to stop container '{name}': {e}")
                return False

        return await _run_blocking_call(_stop)

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

        return await _run_blocking_call(_remove)

    def list_containers(self, all: bool = False) -> List[Dict]:
        """
        Lists Docker containers.

        Args:
            all: Whether to list all containers (including stopped ones).

        Returns:
            A list of dictionaries, where each dictionary represents a container.
        """
        if not self._check_client():
            raise errors.DockerException("Docker client is not initialized")
        assert self.client is not None
        try:
            containers_list = self.client.containers.list(all=all)
        except errors.APIError as e:
            # An unavailable inventory is not an empty inventory.  Callers use
            # an empty list as proof that runtimes are missing, so propagate
            # daemon/list failures and let the reconciliation pass abort.
            logger.error(f"Failed to list containers: {e}")
            raise

        result_list = []
        for container in containers_list:
            health_status = None
            try:
                health_status = container.attrs["State"]["Health"]["Status"]
            except (KeyError, AttributeError):
                # Container might not have a health check configured
                pass

            configured_image = container.attrs.get("Config", {}).get("Image", "")
            try:
                image_tags = container.image.tags
                image_name = image_tags[0] if image_tags else configured_image
            except errors.NotFound as e:
                # A running container can outlive the exact image manifest
                # used to create it (for example after rebuilding the same
                # local tag).  Docker SDK resolves ``container.image`` via a
                # separate image-inspect request, so this specific stale-image
                # condition falls back to the immutable container config.
                logger.warning(
                    "Could not inspect image metadata for container '{}'; "
                    "using its configured image reference: {}",
                    container.name,
                    e,
                )
                image_name = configured_image

            result_list.append(
                {
                    "id": container.id,
                    "name": container.name,
                    "image": image_name,
                    "status": container.status,
                    "health_status": health_status,
                    "ports": container.ports,
                    "labels": container.labels,
                    "short_id": container.short_id,
                }
            )
        logger.debug(f"Listed {len(result_list)} Docker containers.")
        return result_list

    def get_container_environment(self, name: str) -> Optional[Dict[str, str]]:
        """
        Returns a container's configured environment variables without logging values.
        """
        if not self._check_client():
            raise errors.DockerException("Docker client is not initialized")
        assert self.client is not None
        try:
            container = self.client.containers.get(name)
            env_map = {}
            for item in container.attrs["Config"].get("Env", []):
                key, value = item.split("=", 1)
                env_map[key] = value
            return env_map
        except errors.NotFound:
            logger.info(f"Container '{name}' not found while reading environment.")
            raise
        except (KeyError, ValueError) as e:
            logger.warning(f"Could not read environment for container '{name}': {e}")
        except errors.APIError as e:
            logger.error(f"Failed to inspect container '{name}': {e}")
            raise
        return None

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

    def pull_image(self, image_name: str) -> bool:
        """
        Pulls a Docker image from a registry.

        Args:
            image_name: The name of the image to pull (e.g., 'ubuntu:latest').

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            logger.info(f"Pulling image '{image_name}'...")
            self.client.images.pull(image_name)
            logger.info(f"Image '{image_name}' pulled successfully.")
            return True
        except errors.ImageNotFound:
            logger.error(f"Image '{image_name}' not found in the registry.")
            return False
        except errors.APIError as e:
            logger.error(f"Failed to pull image '{image_name}': {e}")
            return False

    async def recreate_service(self, service_name: str, new_image_tag: str) -> bool:
        """
        Recreates a service container with a new image tag, preserving its configuration.
        This simulates 'docker-compose up -d <service>'.

        Args:
            service_name: The name of the service to recreate (e.g., 'server', 'web').
            new_image_tag: The new image tag to use for the service.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None

        container_name = f"hyac_{service_name}"
        try:
            # 1. Get the old container to preserve its configuration
            old_container = self.client.containers.get(container_name)

            # Extract essential configuration
            container_config = old_container.attrs["Config"]
            host_config = old_container.attrs["HostConfig"]
            network_settings = old_container.attrs["NetworkSettings"]["Networks"]

            # Construct the new image name
            # Assumes image name format is 'wicos/hyac_<service_name>:<tag>'
            image_base_name = container_config["Image"].split(":")[0]
            new_image_name = f"{image_base_name}:{new_image_tag}"

            # 2. Pull the new image
            logger.info(
                f"Pulling new image for service '{service_name}': {new_image_name}"
            )
            if not self.pull_image(new_image_name):
                logger.error(
                    f"Failed to pull new image for {service_name}. Aborting recreate."
                )
                return False

            # 3. Stop and remove the old container
            logger.info(f"Stopping and removing old container '{container_name}'...")
            await self.stop_container(container_name)
            await self.remove_container(container_name)
            logger.info(f"Old container '{container_name}' removed.")

            # 4. Create the new container with the preserved configuration
            logger.info(
                f"Recreating container '{container_name}' with image '{new_image_name}'..."
            )

            # Get the primary network name
            network_name = list(network_settings.keys())[0]

            new_container = self.client.containers.create(
                image=new_image_name,
                name=container_name,
                environment=container_config.get("Env"),
                volumes=[
                    mount["Source"] for mount in host_config.get("Mounts", [])
                ],  # This is a simplification
                labels=container_config.get("Labels"),
                hostname=container_config.get("Hostname"),
                detach=True,
                restart_policy=host_config.get("RestartPolicy"),
            )

            # Attach the container to the original network
            network = self.client.networks.get(network_name)
            network.connect(new_container)

            new_container.start()

            logger.info(
                f"Service '{service_name}' recreated and started successfully with tag '{new_image_tag}'."
            )
            return True

        except errors.NotFound:
            logger.error(
                f"Container for service '{service_name}' (named '{container_name}') not found."
            )
            return False
        except errors.APIError as e:
            logger.error(f"Failed to recreate service '{service_name}': {e}")
            return False
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while recreating service '{service_name}': {e}"
            )
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


def get_app_image_name() -> str:
    """
    Determines the appropriate image name for the 'hyac_app' container.
    """
    if settings.DEV_MODE:
        return "hyac_app:dev"  # Use local dev image

    # The image tag is now directly sourced from settings
    return f"wicos/hyac_app:{settings.APP_IMAGE_TAG}"


def _use_acme_certresolver() -> bool:
    """
    Avoid ACME when a local certificate is supplied by development or CI.
    """
    return (
        settings.RUNTIME_INGRESS_TLS
        and not settings.DEV_MODE
        and not settings.CI_SMOKE_MODE
    )


def _router_tls_yaml_block(indent: str = "      ") -> str:
    """
    Build router tls config block for Traefik dynamic file provider.
    """
    if not settings.RUNTIME_INGRESS_TLS:
        return ""
    if _use_acme_certresolver():
        return (
            f"{indent}tls:\n"
            f'{indent}  certResolver: "myresolver"'
        )
    return f"{indent}tls: {{}}"


# In-memory store for running app containers. A more robust solution might use Redis.
running_apps: Dict[str, Dict[str, Any]] = {}
# In-memory lock to prevent race conditions when starting the same app container.
_app_start_locks: Dict[str, asyncio.Lock] = {}
TRAEFIK_DYNAMIC_CONFIG_DIR = "/traefik/dynamic"
_TRAEFIK_GENERATION_PREFIX = "# hyac-runtime-generation: "
_STARTABLE_APPLICATION_STATUSES = frozenset(
    {ApplicationStatus.STARTING, ApplicationStatus.RUNNING}
)


async def _await_tracked_task(task: asyncio.Task):
    """Finish an already-started operation before propagating cancellation."""
    pending_cancel = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            pending_cancel = pending_cancel or exc
        except BaseException:
            if pending_cancel is not None:
                logger.exception(
                    "Tracked operation failed while its caller was being cancelled"
                )
                raise pending_cancel
            raise

    try:
        result = task.result()
    except BaseException:
        if pending_cancel is not None:
            logger.exception(
                "Tracked operation failed while its caller was being cancelled"
            )
            raise pending_cancel
        raise
    if pending_cancel is not None:
        raise pending_cancel
    return result


async def _run_blocking_call(function, *args, **kwargs):
    """Run synchronous SDK work without abandoning its thread on cancellation."""
    operation = asyncio.create_task(
        asyncio.to_thread(function, *args, **kwargs)
    )
    return await _await_tracked_task(operation)


async def _run_cleanup_non_cancellable(cleanup_coro):
    """Collect cleanup even if the startup owner receives another cancellation."""
    cleanup = asyncio.create_task(cleanup_coro)
    return await _await_tracked_task(cleanup)


async def _cleanup_runtime_generation(
    app_id: str,
    container_name: str,
    runtime_generation: int,
    container_id: Optional[str],
    expected_token_hash: Optional[str] = None,
    *,
    cleanup_task_id: Optional[str] = None,
    cleanup_lease_owner: Optional[str] = None,
) -> bool:
    """Fence one generation in MongoDB before any destructive cleanup."""
    application_collection = mongodb_manager.get_collection(Application)
    owner = (
        f"cleanup:{cleanup_lease_owner}:{secrets.token_urlsafe(16)}"
        if cleanup_task_id and cleanup_lease_owner
        else f"cleanup:{secrets.token_urlsafe(16)}"
    )
    owner_task_id = cleanup_task_id

    async def acquire_cleanup(session) -> bool:
        now = datetime.now(timezone.utc)
        owner_expires_at = None
        if cleanup_task_id:
            if not cleanup_lease_owner:
                return False
            task = await mongodb_manager.get_collection(Task).find_one(
                {
                    "task_id": cleanup_task_id,
                    "status": TaskStatus.RUNNING,
                    "lease_owner": cleanup_lease_owner,
                    "lease_expires_at": {"$gt": datetime.now(timezone.utc)},
                    "published_at": None,
                },
                session=session,
            )
            if not task:
                return False
            owner_expires_at = (
                task.get("lease_expires_at")
                if isinstance(task, dict)
                else getattr(task, "lease_expires_at", None)
            )
            ownership_query = {
                "$or": [
                    {
                        "runtime_cleanup_task_id": None,
                        "runtime_cleanup_lease_owner": None,
                    },
                    # A reclaimed lease for the same durable Task may take
                    # over cleanup left behind by the crashed worker.
                    {"runtime_cleanup_task_id": cleanup_task_id},
                    # A durable lifecycle task may also recover cleanup left
                    # behind by an expired proxy/adoption owner.
                    _available_generic_runtime_owner_query(now),
                ]
            }
        else:
            ownership_query = _available_generic_runtime_owner_query(now)
            owner_expires_at = _runtime_owner_deadline()
        result = await application_collection.update_one(
            {
                "app_id": app_id,
                "runtime_generation": runtime_generation,
                **ownership_query,
            },
            {
                "$set": {
                    "runtime_cleanup_task_id": owner_task_id,
                    "runtime_cleanup_lease_owner": owner,
                    "runtime_cleanup_lease_expires_at": owner_expires_at,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            session=session,
        )
        return result.matched_count > 0

    async with mongodb_manager.client.start_session() as session:
        async with await session.start_transaction():
            acquired = await acquire_cleanup(session)
    if not acquired:
        logger.info(
            "Skipped cleanup for app {} generation {}; ownership advanced",
            app_id,
            runtime_generation,
        )
        return False

    owner_query = {
        "app_id": app_id,
        "runtime_generation": runtime_generation,
        "runtime_cleanup_task_id": owner_task_id,
        "runtime_cleanup_lease_owner": owner,
    }

    async def cleanup_still_owned() -> bool:
        if cleanup_task_id:
            task = await mongodb_manager.get_collection(Task).find_one(
                {
                    "task_id": cleanup_task_id,
                    "status": TaskStatus.RUNNING,
                    "lease_owner": cleanup_lease_owner,
                    "lease_expires_at": {"$gt": datetime.now(timezone.utc)},
                    "published_at": None,
                }
            )
            if not task:
                return False
        renewal = {"updated_at": datetime.now(timezone.utc)}
        if cleanup_task_id is None:
            renewal["runtime_cleanup_lease_expires_at"] = _runtime_owner_deadline()
        result = await application_collection.update_one(
            owner_query,
            {"$set": renewal},
        )
        return result.matched_count > 0

    async def release_cleanup(*, completed: bool) -> None:
        fields = {
            "runtime_cleanup_task_id": None,
            "runtime_cleanup_lease_owner": None,
            "runtime_cleanup_lease_expires_at": None,
            "updated_at": datetime.now(timezone.utc),
        }
        if completed:
            fields["pending_traefik_cleanup_generation"] = None
        await application_collection.update_one(
            owner_query,
            {"$set": fields},
        )

    if not await cleanup_still_owned():
        return False

    cleanup_failures = []
    try:
        token_query = dict(owner_query)
        if expected_token_hash is not None:
            token_query["runtime_token_hash"] = expected_token_hash
        revoke_result = await application_collection.update_one(
            token_query,
            {
                "$set": {
                    "runtime_token_hash": None,
                    "pending_traefik_cleanup_generation": runtime_generation,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        if revoke_result.matched_count == 0:
            retry_result = await application_collection.update_one(
                {
                    **owner_query,
                    "runtime_token_hash": None,
                    "pending_traefik_cleanup_generation": runtime_generation,
                },
                {"$set": {"updated_at": datetime.now(timezone.utc)}},
            )
            if retry_result.matched_count == 0:
                await release_cleanup(completed=False)
                return False
    except Exception:
        logger.exception(
            "Failed to revoke runtime token for app {} generation {}",
            app_id,
            runtime_generation,
        )
        cleanup_failures.append("failed to revoke runtime token")

    if not cleanup_failures and container_id:
        if not await cleanup_still_owned():
            return False
        try:
            if not await docker_manager.stop_container(container_id):
                cleanup_failures.append(f"failed to stop container {container_id}")
        except Exception as exc:
            logger.exception(
                "Failed to stop container {} for app {} generation {}",
                container_id,
                app_id,
                runtime_generation,
            )
            cleanup_failures.append(str(exc))
        if not cleanup_failures and not await cleanup_still_owned():
            return False
        try:
            if not await docker_manager.remove_container(container_id):
                cleanup_failures.append(f"failed to remove container {container_id}")
        except Exception as exc:
            logger.exception(
                "Failed to remove container {} for app {} generation {}",
                container_id,
                app_id,
                runtime_generation,
            )
            cleanup_failures.append(str(exc))

    if not cleanup_failures and not await cleanup_still_owned():
        return False

    registry_entry = running_apps.get(app_id)
    owned_registry = bool(
        registry_entry
        and (
            registry_entry.get("generation") == runtime_generation
            or (container_id and registry_entry.get("id") == container_id)
        )
    )
    if not cleanup_failures and owned_registry:
        running_apps.pop(app_id, None)

    if not cleanup_failures:
        if not await cleanup_still_owned():
            return False
        try:
            remove_traefik_web_config_for_generation(
                app_id, runtime_generation
            )
        except Exception as exc:
            logger.exception(
                "Failed to remove Traefik config for app {} generation {}",
                app_id,
                runtime_generation,
            )
            cleanup_failures.append(str(exc))

    if cleanup_failures:
        try:
            await release_cleanup(completed=False)
        except Exception:
            logger.exception(
                "Failed to release cleanup owner for app {} generation {}",
                app_id,
                runtime_generation,
            )
        raise RuntimeError(
            f"Runtime cleanup failed for {container_name} generation "
            f"{runtime_generation}: {'; '.join(cleanup_failures)}"
        )
    await release_cleanup(completed=True)
    return True


async def _acquire_runtime_adoption(
    app: Application,
    *,
    lifecycle_status: ApplicationStatus,
    lifecycle_revision: int,
    cleanup_task_id: Optional[str],
    cleanup_lease_owner: Optional[str],
) -> tuple[Optional[str], str] | None:
    """Fence healthy-runtime adoption against generation cleanup."""
    owner = f"adopt:{cleanup_lease_owner or 'generic'}:{secrets.token_urlsafe(16)}"
    owner_task_id = cleanup_task_id
    application_collection = mongodb_manager.get_collection(Application)

    async def acquire(session):
        now = datetime.now(timezone.utc)
        owner_expires_at = None
        if cleanup_task_id:
            if not cleanup_lease_owner:
                return False
            task = await mongodb_manager.get_collection(Task).find_one(
                {
                    "task_id": cleanup_task_id,
                    "status": TaskStatus.RUNNING,
                    "lease_owner": cleanup_lease_owner,
                    "lease_expires_at": {"$gt": datetime.now(timezone.utc)},
                    "published_at": None,
                },
                session=session,
            )
            if not task:
                return False
            owner_expires_at = (
                task.get("lease_expires_at")
                if isinstance(task, dict)
                else getattr(task, "lease_expires_at", None)
            )
            ownership_query = {
                "runtime_cleanup_task_id": None,
                "runtime_cleanup_lease_owner": None,
            }
        else:
            ownership_query = _available_generic_runtime_owner_query(now)
            owner_expires_at = _runtime_owner_deadline()
        result = await application_collection.update_one(
            {
                "app_id": app.app_id,
                "runtime_generation": app.runtime_generation,
                "runtime_token_hash": app.runtime_token_hash,
                "status": lifecycle_status,
                "lifecycle_revision": lifecycle_revision,
                "pending_traefik_cleanup_generation": None,
                **ownership_query,
            },
            {
                "$set": {
                    "runtime_cleanup_task_id": owner_task_id,
                    "runtime_cleanup_lease_owner": owner,
                    "runtime_cleanup_lease_expires_at": owner_expires_at,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            session=session,
        )
        return result.matched_count > 0

    async with mongodb_manager.client.start_session() as session:
        async with await session.start_transaction():
            acquired = await acquire(session)
    if not acquired:
        return None
    return owner_task_id, owner


async def _release_runtime_adoption(
    app_id: str,
    runtime_generation: int,
    owner_task_id: Optional[str],
    owner: str,
) -> bool:
    result = await mongodb_manager.get_collection(Application).update_one(
        {
            "app_id": app_id,
            "runtime_generation": runtime_generation,
            "runtime_cleanup_task_id": owner_task_id,
            "runtime_cleanup_lease_owner": owner,
        },
        {
            "$set": {
                "runtime_cleanup_task_id": None,
                "runtime_cleanup_lease_owner": None,
                "runtime_cleanup_lease_expires_at": None,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.matched_count > 0


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
      entryPoints: ["{settings.RUNTIME_INGRESS_ENTRYPOINT}"]
      service: "console-service"
{_router_tls_yaml_block(indent="      ")}
      middlewares:
        - "console-chain"

  services:
    console-service:
      loadBalancer:
        servers:
          - url: "{settings.object_storage_internal_url}"

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
          Host: "{settings.object_storage_internal_host_header}"
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


def create_traefik_web_config(
    app_id: str,
    domain_name: str,
    runtime_generation: Optional[int] = None,
):
    config_dir = TRAEFIK_DYNAMIC_CONFIG_DIR
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

    generation_header = (
        f"{_TRAEFIK_GENERATION_PREFIX}{runtime_generation}\n"
        if runtime_generation is not None
        else ""
    )
    config_content = f"""{generation_header}
http:
  routers:
    {router_name}:
      rule: "Host(`{bucket_name}.{domain_name}`)"
      entryPoints: ["{settings.RUNTIME_INGRESS_ENTRYPOINT}"]
      service: "{service_name}"
{_router_tls_yaml_block(indent="      ")}
      middlewares:
        - "{chain_name}"

  services:
    {service_name}:
      loadBalancer:
        servers:
          - url: "{settings.object_storage_internal_url}"

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
          Host: "{settings.object_storage_internal_host_header}"
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
    config_path = os.path.join(
        TRAEFIK_DYNAMIC_CONFIG_DIR, f"web-{app_id}.yml"
    )
    if os.path.exists(config_path):
        os.remove(config_path)
        logger.info(f"Removed Traefik web config: {config_path}")


def remove_traefik_web_config_for_generation(
    app_id: str, expected_generation: int
) -> bool:
    """Remove an absent, legacy, or matching config without touching a newer one."""
    config_path = os.path.join(
        TRAEFIK_DYNAMIC_CONFIG_DIR, f"web-{app_id}.yml"
    )
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as config_file:
            first_line = config_file.readline().strip()
        if first_line.startswith(_TRAEFIK_GENERATION_PREFIX):
            try:
                config_generation = int(
                    first_line.removeprefix(_TRAEFIK_GENERATION_PREFIX)
                )
            except ValueError:
                raise RuntimeError(
                    f"Invalid Traefik generation marker in {config_path}"
                )
            if config_generation != expected_generation:
                logger.info(
                    "Preserved Traefik config for app {} generation {}; "
                    "cleanup owns generation {}",
                    app_id,
                    config_generation,
                    expected_generation,
                )
                return False
    remove_traefik_web_config(app_id)
    return True


async def build_app_image_if_not_exists():
    """
    Checks if the 'hyac_app' Docker image exists, as it should be pre-built
    by docker-compose in the development environment.
    """
    if not docker_manager.client:
        logger.error("Docker client not initialized.")
        return
    app_image_name = get_app_image_name()
    try:
        docker_manager.client.images.get(app_image_name)
        logger.info(f"Docker image '{app_image_name}' found and ready to use.")
    except errors.ImageNotFound:
        logger.error(
            f"Docker image '{app_image_name}' not found. "
            f"Please ensure it was built correctly, e.g., by running 'docker-compose build app'."
        )


async def start_app_container(
    app: Application,
    runtime_state: Optional[Dict[str, Any]] = None,
    expected_status: Optional[ApplicationStatus] = None,
    expected_lifecycle_revision: Optional[int] = None,
    cleanup_task_id: Optional[str] = None,
    cleanup_lease_owner: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Starts a dedicated container for a specific application, with a lock to prevent race conditions.
    """
    app_id = app.app_id
    # Get or create a lock for the specific app_id
    lock = _app_start_locks.setdefault(app_id, asyncio.Lock())

    async with lock:
        if not docker_manager.client:
            return None

        lifecycle_status = expected_status
        lifecycle_revision = expected_lifecycle_revision
        while True:
            authoritative_app = await Application.find_one({"app_id": app_id})
            if not authoritative_app:
                return None
            app = authoritative_app
            authoritative_status = getattr(
                app, "status", ApplicationStatus.STARTING
            )
            authoritative_revision = getattr(app, "lifecycle_revision", 0)
            if lifecycle_status is None:
                lifecycle_status = authoritative_status
            if lifecycle_revision is None:
                lifecycle_revision = authoritative_revision
            pending_cleanup_generation = getattr(
                app, "pending_traefik_cleanup_generation", None
            )
            cleanup_owner_task_id = getattr(
                app, "runtime_cleanup_task_id", None
            )
            cleanup_owner = getattr(app, "runtime_cleanup_lease_owner", None)
            generic_owner_expired = generic_runtime_owner_is_expired(app)
            recoverable_task_cleanup = bool(
                cleanup_task_id
                and cleanup_lease_owner
                and (
                    cleanup_owner_task_id == cleanup_task_id
                    or pending_cleanup_generation == app.runtime_generation
                )
            )
            recoverable_generic_cleanup = bool(
                cleanup_task_id is None
                and pending_cleanup_generation == app.runtime_generation
                and cleanup_owner_task_id is None
                and (cleanup_owner is None or generic_owner_expired)
            )
            if recoverable_task_cleanup or recoverable_generic_cleanup:
                container_name = f"hyac-app-runtime-{app_id.lower()}"
                cleanup_containers = await _run_blocking_call(
                    docker_manager.list_containers, all=True
                )
                cleanup_container = next(
                    (
                        container
                        for container in cleanup_containers
                        if container.get("name") == container_name
                    ),
                    None,
                )
                cleaned = await _cleanup_runtime_generation(
                    app_id,
                    container_name,
                    app.runtime_generation,
                    cleanup_container.get("id") if cleanup_container else None,
                    getattr(app, "runtime_token_hash", None),
                    cleanup_task_id=(
                        cleanup_task_id if recoverable_task_cleanup else None
                    ),
                    cleanup_lease_owner=(
                        cleanup_lease_owner if recoverable_task_cleanup else None
                    ),
                )
                if not cleaned:
                    return None
                continue
            if generic_owner_expired:
                if not await clear_expired_generic_runtime_owner(app):
                    continue
                cleanup_owner = None
            if (
                authoritative_status not in _STARTABLE_APPLICATION_STATUSES
                or authoritative_status != lifecycle_status
                or authoritative_revision != lifecycle_revision
                or cleanup_owner_task_id is not None
                or cleanup_owner is not None
                or pending_cleanup_generation is not None
            ):
                logger.info(
                    "Refused runtime start for app {} at status {} revision {}; "
                    "expected status {} revision {}",
                    app_id,
                    authoritative_status,
                    authoritative_revision,
                    lifecycle_status,
                    lifecycle_revision,
                )
                return None
            container_name = f"hyac-app-runtime-{app_id.lower()}"
            containers = await _run_blocking_call(
                docker_manager.list_containers, all=True
            )
            containers_by_name = {
                container["name"]: container for container in containers
            }
            domain_name = settings.DOMAIN_NAME or "localhost"

            # Recheck authoritative generation and credentials after acquiring
            # the per-app lock; callers may hold stale Application snapshots.
            registry_entry = running_apps.get(app_id)
            existing_container = containers_by_name.get(container_name)
            existing_environment = {}
            credentials_match = False
            if existing_container:
                existing_environment = (
                    await _run_blocking_call(
                        docker_manager.get_container_environment,
                        existing_container["id"],
                    )
                    or {}
                )
                runtime_token = existing_environment.get("RUNTIME_TOKEN", "")
                runtime_token_hash = hashlib.sha256(
                    runtime_token.encode("utf-8")
                ).hexdigest()
                credentials_match = bool(
                    runtime_token
                    and app.runtime_token_hash
                    and hmac.compare_digest(
                        runtime_token_hash, app.runtime_token_hash
                    )
                    and existing_environment.get("RUNTIME_GENERATION")
                    == str(app.runtime_generation)
                )
            if (
                existing_container
                and existing_container.get("status") == "running"
                and existing_container.get("health_status") == "healthy"
                and credentials_match
                and runtime_container_matches_ingress(existing_container, app_id)
                and not LEGACY_PLATFORM_ENV_KEYS.intersection(
                    existing_environment
                )
            ):
                adoption_owner = await _acquire_runtime_adoption(
                    app,
                    lifecycle_status=lifecycle_status,
                    lifecycle_revision=lifecycle_revision,
                    cleanup_task_id=cleanup_task_id,
                    cleanup_lease_owner=cleanup_lease_owner,
                )
                if adoption_owner is None:
                    logger.info(
                        "Refused runtime adoption for app {}; cleanup or "
                        "lifecycle authority advanced",
                        app_id,
                    )
                    return None
                adoption_task_id, adoption_lease_owner = adoption_owner
                if (
                    not registry_entry
                    or registry_entry.get("id") != existing_container.get("id")
                    or registry_entry.get("generation")
                    != app.runtime_generation
                ):
                    registry_entry = {
                        "id": existing_container["id"],
                        "name": container_name,
                        "generation": app.runtime_generation,
                    }
                    running_apps[app_id] = registry_entry
                if runtime_state is not None:
                    runtime_state["runtime_generation"] = app.runtime_generation
                    runtime_state["runtime_token_hash"] = app.runtime_token_hash
                    runtime_state["lifecycle_revision"] = lifecycle_revision
                    runtime_state["source_status"] = lifecycle_status
                if cleanup_task_id is None:
                    if not await _release_runtime_adoption(
                        app_id,
                        app.runtime_generation,
                        adoption_task_id,
                        adoption_lease_owner,
                    ):
                        if running_apps.get(app_id) is registry_entry:
                            running_apps.pop(app_id, None)
                        return None
                else:
                    registry_entry["runtime_owner_task_id"] = adoption_task_id
                    registry_entry["runtime_owner"] = adoption_lease_owner
                logger.info(
                    "Container for app '{}' is already running "
                    "(checked after acquiring lock).",
                    app_id,
                )
                return registry_entry

            if existing_container:
                container_id = existing_container["id"]
                cleaned = await _cleanup_runtime_generation(
                    app_id,
                    container_name,
                    app.runtime_generation,
                    container_id,
                    getattr(app, "runtime_token_hash", None),
                    cleanup_task_id=cleanup_task_id,
                    cleanup_lease_owner=cleanup_lease_owner,
                )
                if not cleaned:
                    return None
                logger.info(
                    "Stopped and deleted stale container '{}' before starting "
                    "a new one.",
                    container_name,
                )
                # Revalidate database authority after releasing the cleanup
                # fence before allocating the successor generation. The
                # exact stale container id has already been removed.
                app = await Application.find_one(
                    {
                        "app_id": app_id,
                        "runtime_generation": app.runtime_generation,
                        "status": lifecycle_status,
                        "lifecycle_revision": lifecycle_revision,
                        "runtime_cleanup_task_id": None,
                        "runtime_cleanup_lease_owner": None,
                        "runtime_cleanup_lease_expires_at": None,
                        "pending_traefik_cleanup_generation": None,
                    }
                )
                if not app:
                    return None
            else:
                registry_entry = running_apps.get(app_id)
                if (
                    registry_entry
                    and registry_entry.get("generation")
                    == app.runtime_generation
                ):
                    running_apps.pop(app_id, None)

            storage = await app_storage_service.get_storage(app_id)
            if not storage or storage.status != StorageStatus.READY:
                storage = await app_storage_service.ensure_ready(app_id)

            expected_generation = app.runtime_generation
            startup_generation = expected_generation + 1
            runtime_token = secrets.token_urlsafe(32)
            runtime_token_hash = hashlib.sha256(
                runtime_token.encode("utf-8")
            ).hexdigest()
            allocation_time = datetime.now()
            app.updated_at = allocation_time
            allocation = await mongodb_manager.get_collection(
                Application
            ).update_one(
                {
                    "app_id": app_id,
                    "runtime_generation": expected_generation,
                    "status": lifecycle_status,
                    "lifecycle_revision": lifecycle_revision,
                    "runtime_cleanup_task_id": None,
                    "runtime_cleanup_lease_owner": None,
                    "runtime_cleanup_lease_expires_at": None,
                    "pending_traefik_cleanup_generation": None,
                },
                {
                    "$set": {
                        "runtime_generation": startup_generation,
                        "runtime_token_hash": runtime_token_hash,
                        "updated_at": allocation_time,
                    }
                },
            )
            if allocation.matched_count == 0:
                logger.info(
                    "Runtime generation changed while starting app {}; retrying",
                    app_id,
                )
                await asyncio.sleep(0)
                continue
            app.runtime_generation = startup_generation
            app.runtime_token_hash = runtime_token_hash
            if runtime_state is not None:
                runtime_state["runtime_generation"] = startup_generation
                runtime_state["runtime_token_hash"] = runtime_token_hash
                runtime_state["lifecycle_revision"] = lifecycle_revision
                runtime_state["source_status"] = lifecycle_status
            break

        created_container = None

        async def abort_startup() -> None:
            revoked = await _run_cleanup_non_cancellable(
                _cleanup_runtime_generation(
                    app.app_id,
                    container_name,
                    startup_generation,
                    getattr(created_container, "id", None),
                    runtime_token_hash,
                    cleanup_task_id=cleanup_task_id,
                    cleanup_lease_owner=cleanup_lease_owner,
                )
            )
            if (
                revoked
                and app.runtime_generation == startup_generation
                and app.runtime_token_hash == runtime_token_hash
            ):
                app.runtime_token_hash = None

        async def await_startup_step(awaitable, *, cleanup_on_error=True):
            try:
                return await awaitable
            except asyncio.CancelledError:
                if cleanup_task_id is None:
                    try:
                        await abort_startup()
                    except Exception:
                        logger.exception(
                            "Runtime cleanup failed while cancelling app {} generation {}",
                            app.app_id,
                            startup_generation,
                        )
                raise
            except Exception:
                if cleanup_on_error:
                    await abort_startup()
                raise

        environment = {
            "APP_ID": app.app_id,  # Pass the app_id to the container
            "APP_DB_USERNAME": app.app_id,
            "APP_DB_PASSWORD": app.db_password,
            "RUNTIME_TOKEN": runtime_token,
            "RUNTIME_GENERATION": str(app.runtime_generation),
            "CONTROL_PLANE_URL": "http://hyac_server:8000/internal/runtime",
            "S3_ACCESS_KEY": storage.access_key,
            "S3_SECRET_KEY": storage.secret_key,
            "S3_INTERNAL_ENDPOINT": settings.object_storage_internal_endpoint,
            "S3_SECURE_INTERNAL": settings.S3_SECURE_INTERNAL,
            "DEV_MODE": settings.DEV_MODE,
            "DEBUG": True,  # Only for logger level
            "LSP_MODE": settings.LSP_MODE,
            "LSP_SIDECAR_URL": settings.LSP_SIDECAR_URL,
            "LSP_SIDECAR_TIMEOUT_SECONDS": settings.LSP_SIDECAR_TIMEOUT_SECONDS,
            "LSP_SIDECAR_FALLBACK_LEGACY": settings.LSP_SIDECAR_FALLBACK_LEGACY,
        }

        # Add user-defined environment variables
        reserved_env_keys = RESERVED_ENV_KEYS | set(environment)
        for env_var in app.environment_variables:
            if env_var.key in reserved_env_keys:
                logger.warning(
                    "Ignoring reserved environment variable '%s' for app '%s'",
                    env_var.key,
                    app.app_id,
                )
                continue
            environment[env_var.key] = env_var.value

        # Define the healthcheck for the app container
        healthcheck = {
            "test": [
                "CMD",
                "python",
                "-c",
                "import httpx; httpx.get('http://localhost:8001/__runtime_health__').raise_for_status()",
            ],
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

        # --- Dynamic Network Attachment & Label Inheritance ---
        network_name = "hyac_network"  # Default fallback
        compose_labels = {}
        try:
            server_container = await await_startup_step(
                _run_blocking_call(
                    docker_manager.client.containers.get, "hyac_server"
                ),
                cleanup_on_error=False,
            )
            # Get the first network name from the list of networks
            network_name = list(
                server_container.attrs["NetworkSettings"]["Networks"].keys()
            )[0]
            logger.info(
                f"Server container is on network '{network_name}'. Attaching app container to the same network."
            )
            # Inherit all docker-compose labels from the server container
            server_labels = server_container.attrs["Config"]["Labels"]
            compose_labels = {
                k: v
                for k, v in server_labels.items()
                if k.startswith("com.docker.compose")
            }
            # Set a specific, dynamic service name for the app container to distinguish it
            if compose_labels:
                compose_labels["com.docker.compose.service"] = (
                    f"app-runtime-{app.app_id.lower()}"
                )
                compose_labels["com.docker.compose.oneoff"] = "False"
                logger.info(
                    f"Inheriting and customizing docker-compose labels: {compose_labels}"
                )
            else:
                logger.warning(
                    "No docker-compose labels found on server container to inherit."
                )

        except (errors.NotFound, KeyError, IndexError) as e:
            logger.warning(
                f"Could not dynamically determine server network or labels (error: {e}). "
                f"Falling back to default network 'hyac_network'. "
                "This might fail if the project name in docker-compose is not 'hyac'."
            )
        except Exception:
            await abort_startup()
            raise

        # --- Traefik Labels for the runtime container ---
        traefik_labels = {
            "traefik.enable": "true",
            f"traefik.http.routers.{container_name}.rule": f"Host(`{app.app_id.lower()}.{domain_name}`)",
            f"traefik.http.routers.{container_name}.entrypoints": settings.RUNTIME_INGRESS_ENTRYPOINT,
            f"traefik.http.services.{container_name}.loadbalancer.server.port": "8001",
        }

        if settings.RUNTIME_INGRESS_TLS:
            traefik_labels[
                f"traefik.http.routers.{container_name}.tls"
            ] = "true"

        if _use_acme_certresolver():
            traefik_labels[
                f"traefik.http.routers.{container_name}.tls.certresolver"
            ] = "myresolver"

        # Merge compose labels with traefik labels
        all_labels = {**compose_labels, **traefik_labels}

        app_image_name = get_app_image_name()

        def create_runtime_container():
            nonlocal created_container
            created_container = docker_manager.create_container(
                image=app_image_name,
                name=container_name,
                environment=environment,
                network=network_name,
                volumes=volumes,
                restart=False,
                healthcheck=healthcheck,
                labels=all_labels,
                mem_limit=f"{app.runtime_memory_mb}m",
                nano_cpus=int(app.runtime_cpus * 1_000_000_000),
                pids_limit=app.runtime_pids_limit,
                read_only=not settings.DEV_MODE,
                tmpfs={
                    "/tmp": "rw,noexec,nosuid,nodev,size=128m",
                    "/dependencies": "rw,nosuid,nodev,size=256m",
                },
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                user="hyac",
            )
            return created_container

        container = await await_startup_step(
            _run_blocking_call(create_runtime_container)
        )
        if not container:
            await abort_startup()
            await _revoke_runtime_token(app)
            return None
        if not await await_startup_step(
            _run_blocking_call(docker_manager.start_container, container_name)
        ):
            await abort_startup()
            await _revoke_runtime_token(app)
            return None

        # New health check logic based on Docker's health status
        is_ready = False
        logger.info(f"Waiting for container '{container_name}' to become healthy...")
        for i in range(30):  # Wait for up to 60 seconds
            try:
                await await_startup_step(
                    _run_blocking_call(container.reload),
                    cleanup_on_error=False,
                )
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
                await await_startup_step(asyncio.sleep(2))
            except KeyError:
                # This can happen if the health status is not yet available
                logger.info(
                    f"Health status for '{container_name}' not available yet. Waiting... (Attempt {i+1}/30)"
                )
                await await_startup_step(asyncio.sleep(2))
            except errors.NotFound:
                logger.error(
                    f"Container '{container_name}' not found during health check."
                )
                await abort_startup()
                await _revoke_runtime_token(app)
                return None
            except Exception:
                await abort_startup()
                raise

        if not is_ready:
            logger.error(f"Container '{container_name}' did not become healthy in time.")
            await abort_startup()
            await _revoke_runtime_token(app)
            return None

        # --- New: Network Readiness Check ---
        # Even if healthy, wait for Docker's internal DNS to resolve the container name.
        logger.info(f"Verifying network readiness for container '{container_name}'...")
        network_ready = False
        for i in range(15):  # Wait for up to 15 seconds for DNS to propagate
            try:
                # This runs in a thread to avoid blocking the async event loop.
                await await_startup_step(
                    _run_blocking_call(socket.gethostbyname, container_name),
                    cleanup_on_error=False,
                )
                logger.info(
                    f"Successfully resolved hostname for '{container_name}'. Network is ready."
                )
                network_ready = True
                break
            except socket.gaierror:
                logger.warning(
                    f"DNS resolution for '{container_name}' failed. Retrying... (Attempt {i+1}/15)"
                )
                await await_startup_step(asyncio.sleep(1))
            except Exception:
                await abort_startup()
                raise

        if not network_ready:
            logger.error(
                f"Could not resolve hostname for '{container_name}' after multiple attempts. Aborting."
            )
            await abort_startup()
            await _revoke_runtime_token(app)
            return None

        # Initialize function templates for the newly created app
        from core.initialization import create_function_templates_for_app

        await await_startup_step(create_function_templates_for_app(app.app_id))

        # Create Traefik config for web hosting
        try:
            create_traefik_web_config(
                app.app_id, domain_name, startup_generation
            )
        except Exception:
            await abort_startup()
            raise

        final_authority = await Application.find_one(
            {
                "app_id": app.app_id,
                "runtime_generation": startup_generation,
                "runtime_token_hash": runtime_token_hash,
                "status": lifecycle_status,
                "lifecycle_revision": lifecycle_revision,
                "runtime_cleanup_task_id": None,
                "runtime_cleanup_lease_owner": None,
                "runtime_cleanup_lease_expires_at": None,
                "pending_traefik_cleanup_generation": None,
            }
        )
        if not final_authority:
            logger.info(
                "Runtime authority changed before registering app {} generation {}",
                app.app_id,
                startup_generation,
            )
            await abort_startup()
            return None

        container_info = {
            "name": container_name,
            "id": container.id,
            "generation": startup_generation,
            "lifecycle_revision": lifecycle_revision,
            "source_status": lifecycle_status,
        }
        running_apps[app.app_id] = container_info
        logger.info(
            f"Started container for app '{app.app_id}'. Traefik proxy configured."
        )

        return container_info


async def stop_app_container(
    app_id: str,
    expected_runtime_generation: Optional[int] = None,
    expected_status: Optional[ApplicationStatus] = None,
    expected_lifecycle_revision: Optional[int] = None,
) -> bool:
    """
    Stops and removes the container for a specific application.
    """
    lock = _app_start_locks.setdefault(app_id, asyncio.Lock())
    async with lock:
        return await _stop_app_container_locked(
            app_id,
            expected_runtime_generation,
            expected_status,
            expected_lifecycle_revision,
        )


async def _stop_app_container_locked(
    app_id: str,
    expected_runtime_generation: Optional[int],
    expected_status: Optional[ApplicationStatus],
    expected_lifecycle_revision: Optional[int],
) -> bool:
    """Stop one runtime while the caller owns its lifecycle lock."""
    application = await Application.find_one({"app_id": app_id})
    if application:
        current_generation = getattr(application, "runtime_generation", None)
        current_status = getattr(application, "status", None)
        current_revision = getattr(application, "lifecycle_revision", None)
        if (
            expected_runtime_generation is not None
            and current_generation != expected_runtime_generation
        ) or (
            expected_status is not None and current_status != expected_status
        ) or (
            expected_lifecycle_revision is not None
            and current_revision != expected_lifecycle_revision
        ):
            logger.info(
                "Refused stale stop for app {} generation {} status {} revision {}",
                app_id,
                current_generation,
                current_status,
                current_revision,
            )
            return False
        revoked = await _revoke_runtime_token(
            application,
            expected_status=(
                expected_status if expected_status is not None else current_status
            ),
            expected_lifecycle_revision=(
                expected_lifecycle_revision
                if expected_lifecycle_revision is not None
                else current_revision
            ),
        )
        if not revoked:
            logger.info(
                "Refused stale stop for app {}; runtime authority advanced",
                app_id,
            )
            return False

    container_name = f"hyac-app-runtime-{app_id.lower()}"
    logger.info(f"Stopping container for app '{app_id}'...")
    if not await docker_manager.stop_container(container_name):
        raise RuntimeError(f"Failed to stop container '{container_name}'")
    if not await docker_manager.remove_container(container_name):
        raise RuntimeError(f"Failed to remove container '{container_name}'")

    remove_traefik_web_config(app_id)
    running_apps.pop(app_id, None)
    logger.info(
        f"Container for app '{app_id}' stopped and removed. Traefik proxy updated."
    )
    return True


async def _revoke_runtime_token(
    application: Application,
    expected_status: Optional[ApplicationStatus] = None,
    expected_lifecycle_revision: Optional[int] = None,
) -> bool:
    """Invalidate a credential only while its runtime generation is current."""
    query = {
        "app_id": application.app_id,
        "runtime_generation": application.runtime_generation,
        "runtime_token_hash": application.runtime_token_hash,
    }
    if expected_status is not None:
        query["status"] = expected_status
    if expected_lifecycle_revision is not None:
        query["lifecycle_revision"] = expected_lifecycle_revision
    result = await mongodb_manager.get_collection(Application).update_one(
        query,
        {
            "$set": {
                "runtime_token_hash": None,
                "updated_at": datetime.now(),
            }
        },
    )
    if result.matched_count:
        application.runtime_token_hash = None
        return True
    return False


async def delete_application_background(
    app: Application,
    expected_runtime_generation: Optional[int] = None,
    expected_status: Optional[ApplicationStatus] = None,
    expected_lifecycle_revision: Optional[int] = None,
):
    """Serialize the complete deletion with every startup for this app."""
    lock = _app_start_locks.setdefault(app.app_id, asyncio.Lock())
    async with lock:
        return await _delete_application_background_locked(
            app,
            expected_runtime_generation,
            expected_status,
            expected_lifecycle_revision,
        )


async def _delete_application_background_locked(
    app: Application,
    expected_runtime_generation: Optional[int],
    expected_status: Optional[ApplicationStatus],
    expected_lifecycle_revision: Optional[int],
):
    """
    Performs all deletion operations in the background.
    """
    logger.info(f"Starting background deletion for app '{app.app_name}' ({app.app_id})")

    # Active START/RESTART tasks are rejected transactionally by the route.
    # Never delete a durable RUNNING task here: another worker may own it.
    # 1. Stop and remove the application container
    stopped = await _stop_app_container_locked(
        app.app_id,
        expected_runtime_generation,
        expected_status,
        expected_lifecycle_revision,
    )
    if not stopped:
        raise RuntimeError(
            f"Runtime authority changed before deleting app '{app.app_id}'"
        )
    logger.info(f"Container for app '{app.app_id}' stopped and removed.")

    # 2. Delete all functions associated with the application
    functions_to_delete = await Function.find(Function.app_id == app.app_id).to_list()
    for func in functions_to_delete:
        await func.delete()
    logger.info(
        f"Deleted {len(functions_to_delete)} functions for app '{app.app_id}'."
    )

    # 3. Delete all function templates associated with the application
    templates_to_delete = await FunctionTemplate.find(
        FunctionTemplate.app_id == app.app_id
    ).to_list()
    for template in templates_to_delete:
        await template.delete()
    logger.info(
        f"Deleted {len(templates_to_delete)} function templates for app '{app.app_id}'."
    )

    # 4. Delete S3 buckets and app-scoped storage user
    await app_storage_service.delete_resources(app.app_id)
    logger.info(f"Deleted storage resources for app '{app.app_id}'.")

    # Also remove the web hosting Traefik config
    remove_traefik_web_config(app.app_id)

    # 5. Drop the application's dedicated database
    await dynamic_db.db_client.drop_database(app.app_id)
    logger.info(f"Dropped database '{app.app_id}'.")

    # 6. Delete the application document itself
    await app.delete()
    logger.info(f"Deleted application document for '{app.app_name}'.")

    logger.info(f"Background deletion for app '{app.app_name}' completed.")
