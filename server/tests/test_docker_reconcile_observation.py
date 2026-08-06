import hashlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from docker import errors


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault(
    "SECRET_KEY", "test-secret-key-with-at-least-32-characters"
)

from core import docker_manager as docker_manager_module
from core import task_worker
from models.applications_model import ApplicationStatus


class _Cursor:
    def __init__(self, values):
        self.values = values

    async def to_list(self):
        return list(self.values)


class _ApplicationQuery:
    values = []

    @classmethod
    def find(cls, *_args, **_kwargs):
        return _Cursor(cls.values)


def _running_application():
    return SimpleNamespace(
        app_id="APP12345",
        status=ApplicationStatus.RUNNING,
        runtime_generation=7,
        runtime_token_hash="stored-digest",
        lifecycle_revision=4,
        pending_traefik_cleanup_generation=None,
        runtime_cleanup_task_id=None,
        runtime_cleanup_lease_owner=None,
        runtime_cleanup_lease_expires_at=None,
    )


async def _inline_to_thread(function, *args, **kwargs):
    return function(*args, **kwargs)


class DockerReconcileObservationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        task_worker.running_apps.clear()
        self.addCleanup(task_worker.running_apps.clear)

    async def test_unavailable_inventory_aborts_without_missing_runtime_write(self):
        app = _running_application()
        _ApplicationQuery.values = [app]
        with (
            patch.object(task_worker, "Application", _ApplicationQuery),
            patch.object(task_worker.asyncio, "to_thread", _inline_to_thread),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                side_effect=errors.DockerException("client unavailable"),
            ),
            patch.object(
                task_worker,
                "_replace_missing_runtime",
                new=AsyncMock(),
            ) as replace_missing,
        ):
            with self.assertRaises(errors.DockerException):
                await task_worker.reconcile_running_apps()

        replace_missing.assert_not_awaited()
        self.assertEqual(app.status, ApplicationStatus.RUNNING)
        self.assertEqual(app.runtime_token_hash, "stored-digest")

    async def test_inspect_api_failure_aborts_without_replacing_runtime(self):
        app = _running_application()
        _ApplicationQuery.values = [app]
        container = {
            "id": "container-7",
            "name": "hyac-app-runtime-app12345",
            "status": "running",
            "health_status": "healthy",
        }
        with (
            patch.object(task_worker, "Application", _ApplicationQuery),
            patch.object(task_worker.asyncio, "to_thread", _inline_to_thread),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                return_value=[container],
            ),
            patch.object(
                task_worker.docker_manager,
                "get_container_environment",
                side_effect=errors.APIError("inspect unavailable"),
            ),
            patch.object(
                task_worker,
                "_replace_missing_runtime",
                new=AsyncMock(),
            ) as replace_missing,
            patch.object(
                task_worker,
                "_replace_reconciled_runtime",
                new=AsyncMock(),
            ) as replace_stale,
        ):
            with self.assertRaises(errors.APIError):
                await task_worker.reconcile_running_apps()

        replace_missing.assert_not_awaited()
        replace_stale.assert_not_awaited()
        self.assertEqual(app.status, ApplicationStatus.RUNNING)

    async def test_inspect_not_found_uses_missing_runtime_recovery(self):
        app = _running_application()
        _ApplicationQuery.values = [app]
        container = {
            "id": "container-7",
            "name": "hyac-app-runtime-app12345",
            "status": "running",
            "health_status": "healthy",
        }
        with (
            patch.object(task_worker, "Application", _ApplicationQuery),
            patch.object(task_worker.asyncio, "to_thread", _inline_to_thread),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                return_value=[container],
            ),
            patch.object(
                task_worker.docker_manager,
                "get_container_environment",
                side_effect=errors.NotFound("runtime disappeared"),
            ),
            patch.object(
                task_worker,
                "_replace_missing_runtime",
                new=AsyncMock(),
            ) as replace_missing,
            patch.object(
                task_worker,
                "_replace_reconciled_runtime",
                new=AsyncMock(),
            ) as replace_stale,
        ):
            await task_worker.reconcile_running_apps()

        replace_missing.assert_awaited_once_with(app)
        replace_stale.assert_not_awaited()

    async def test_stale_ingress_domain_replaces_healthy_runtime(self):
        app = _running_application()
        runtime_token = "runtime-token"
        app.runtime_token_hash = hashlib.sha256(runtime_token.encode()).hexdigest()
        _ApplicationQuery.values = [app]
        container = {
            "id": "container-7",
            "name": "hyac-app-runtime-app12345",
            "status": "running",
            "health_status": "healthy",
            "labels": {
                "traefik.http.routers.hyac-app-runtime-app12345.rule": (
                    "Host(`app12345.localhost`)"
                )
            },
        }
        replace_stale = AsyncMock()

        with (
            patch.object(task_worker, "Application", _ApplicationQuery),
            patch.object(task_worker.asyncio, "to_thread", _inline_to_thread),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                return_value=[container],
            ),
            patch.object(
                task_worker.docker_manager,
                "get_container_environment",
                return_value={
                    "RUNTIME_TOKEN": runtime_token,
                    "RUNTIME_GENERATION": str(app.runtime_generation),
                },
            ),
            patch.object(
                task_worker,
                "_replace_reconciled_runtime",
                new=replace_stale,
            ),
            patch.object(
                task_worker,
                "_replace_missing_runtime",
                new=AsyncMock(),
            ),
            patch.object(
                docker_manager_module.settings,
                "DOMAIN_NAME",
                "hyac.localhost",
            ),
        ):
            await task_worker.reconcile_running_apps()

        replace_stale.assert_awaited_once_with(app, container)

    async def test_reconcile_finishes_expired_pending_cleanup_then_recovers(self):
        app = _running_application()
        app.pending_traefik_cleanup_generation = app.runtime_generation
        app.runtime_cleanup_lease_owner = "cleanup:crashed-proxy"
        app.runtime_cleanup_lease_expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        _ApplicationQuery.values = [app]
        cleanup = AsyncMock(return_value=True)
        replace_missing = AsyncMock()

        with (
            patch.object(task_worker, "Application", _ApplicationQuery),
            patch.object(task_worker.asyncio, "to_thread", _inline_to_thread),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                return_value=[],
            ),
            patch.object(task_worker, "_cleanup_runtime_generation", new=cleanup),
            patch.object(
                task_worker,
                "_replace_missing_runtime",
                new=replace_missing,
            ),
        ):
            await task_worker.reconcile_running_apps()

        cleanup.assert_awaited_once_with(
            app.app_id,
            "hyac-app-runtime-app12345",
            app.runtime_generation,
            None,
            "stored-digest",
        )
        replace_missing.assert_awaited_once_with(app)
        self.assertIsNone(app.pending_traefik_cleanup_generation)
        self.assertIsNone(app.runtime_cleanup_lease_owner)

    async def test_reconcile_clears_expired_adoption_before_registering_runtime(self):
        token = "runtime-secret"
        app = _running_application()
        app.runtime_token_hash = hashlib.sha256(token.encode()).hexdigest()
        app.runtime_cleanup_lease_owner = "adopt:crashed-proxy"
        app.runtime_cleanup_lease_expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        _ApplicationQuery.values = [app]
        container = {
            "id": "container-7",
            "name": "hyac-app-runtime-app12345",
            "status": "running",
            "health_status": "healthy",
        }

        async def clear_owner(application):
            application.runtime_cleanup_lease_owner = None
            application.runtime_cleanup_lease_expires_at = None
            return True

        clear = AsyncMock(side_effect=clear_owner)
        with (
            patch.object(task_worker, "Application", _ApplicationQuery),
            patch.object(task_worker.asyncio, "to_thread", _inline_to_thread),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                return_value=[container],
            ),
            patch.object(
                task_worker.docker_manager,
                "get_container_environment",
                return_value={
                    "RUNTIME_TOKEN": token,
                    "RUNTIME_GENERATION": str(app.runtime_generation),
                },
            ),
            patch.object(
                task_worker,
                "clear_expired_generic_runtime_owner",
                new=clear,
            ),
        ):
            await task_worker.reconcile_running_apps()

        clear.assert_awaited_once_with(app)
        self.assertEqual(
            task_worker.running_apps[app.app_id],
            {
                "id": container["id"],
                "name": container["name"],
                "generation": app.runtime_generation,
            },
        )
