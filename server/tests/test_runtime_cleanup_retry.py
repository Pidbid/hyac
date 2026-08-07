import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, call, patch


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from core import docker_manager
from models.applications_model import Application
from routers import applications as applications_router


class _ApplicationCollection:
    def __init__(self, state):
        self.state = state
        self.update_calls = []

    async def update_one(self, query, update, session=None):
        self.update_calls.append((query, update))
        if not self._matches(query):
            return SimpleNamespace(matched_count=0)
        self.state.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1)

    def _matches(self, query):
        for key, expected in query.items():
            if key == "$or":
                if not any(self._matches(branch) for branch in expected):
                    return False
                continue
            actual = self.state.get(key)
            if isinstance(expected, dict):
                if "$lte" in expected and not (
                    actual is not None and actual <= expected["$lte"]
                ):
                    return False
                if "$gt" in expected and not (
                    actual is not None and actual > expected["$gt"]
                ):
                    return False
                if "$ne" in expected and actual == expected["$ne"]:
                    return False
                continue
            if actual != expected:
                return False
        return True


class _NoOpTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _NoOpSession(_NoOpTransaction):
    async def start_transaction(self):
        return _NoOpTransaction()


class _NoOpTransactionClient:
    def start_session(self):
        return _NoOpSession()


class _CleanupTaskCollection:
    def __init__(self, task):
        self.task = task

    async def find_one(self, query, session=None):
        for key, expected in query.items():
            actual = self.task.get(key)
            if isinstance(expected, dict) and "$gt" in expected:
                if actual is None or actual <= expected["$gt"]:
                    return None
            elif actual != expected:
                return None
        return dict(self.task)


class RuntimeCleanupRetryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        docker_manager.running_apps.clear()
        self.addCleanup(docker_manager.running_apps.clear)

    async def test_traefik_cleanup_retries_after_ownership_is_consumed(self):
        token_hash = hashlib.sha256(b"generation-7-token").hexdigest()
        state = {
            "app_id": "APP12345",
            "runtime_generation": 7,
            "runtime_token_hash": token_hash,
            "pending_traefik_cleanup_generation": None,
        }
        collection = _ApplicationCollection(state)
        docker_manager.running_apps[state["app_id"]] = {
            "id": "container-7",
            "name": "hyac-app-runtime-app12345",
            "generation": 7,
        }
        remove_config = MagicMock(
            side_effect=[RuntimeError("temporary Traefik filesystem failure"), True]
        )

        with (
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(
                docker_manager.docker_manager,
                "stop_container",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                docker_manager.docker_manager,
                "remove_container",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                docker_manager,
                "remove_traefik_web_config_for_generation",
                remove_config,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "temporary Traefik filesystem failure"
            ):
                await docker_manager._cleanup_runtime_generation(
                    state["app_id"],
                    "hyac-app-runtime-app12345",
                    7,
                    "container-7",
                    token_hash,
                )

            self.assertIsNone(state["runtime_token_hash"])
            self.assertNotIn(state["app_id"], docker_manager.running_apps)
            self.assertEqual(state["pending_traefik_cleanup_generation"], 7)

            retried = await docker_manager._cleanup_runtime_generation(
                state["app_id"],
                "hyac-app-runtime-app12345",
                7,
                "container-7",
                token_hash,
            )

        self.assertTrue(retried)
        self.assertIsNone(state["pending_traefik_cleanup_generation"])
        self.assertEqual(
            remove_config.call_args_list,
            [
                call(state["app_id"], 7),
                call(state["app_id"], 7),
            ],
        )

    async def test_stale_cleanup_marker_cannot_remove_new_generation_config(self):
        old_token_hash = hashlib.sha256(b"generation-7-token").hexdigest()
        new_token_hash = hashlib.sha256(b"generation-8-token").hexdigest()
        state = {
            "app_id": "APP12345",
            "runtime_generation": 7,
            "runtime_token_hash": old_token_hash,
            "pending_traefik_cleanup_generation": None,
        }
        collection = _ApplicationCollection(state)
        docker_manager.running_apps[state["app_id"]] = {
            "id": "container-7",
            "name": "hyac-app-runtime-app12345",
            "generation": 7,
        }
        remove_config = MagicMock(
            side_effect=RuntimeError("temporary Traefik filesystem failure")
        )

        with (
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(
                docker_manager.docker_manager,
                "stop_container",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                docker_manager.docker_manager,
                "remove_container",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                docker_manager,
                "remove_traefik_web_config_for_generation",
                remove_config,
            ),
        ):
            with self.assertRaises(RuntimeError):
                await docker_manager._cleanup_runtime_generation(
                    state["app_id"],
                    "hyac-app-runtime-app12345",
                    7,
                    "container-7",
                    old_token_hash,
                )

            state.update(
                runtime_generation=8,
                runtime_token_hash=new_token_hash,
            )
            docker_manager.running_apps[state["app_id"]] = {
                "id": "container-8",
                "name": "hyac-app-runtime-app12345",
                "generation": 8,
            }
            remove_config.side_effect = None
            remove_config.reset_mock()

            retried = await docker_manager._cleanup_runtime_generation(
                state["app_id"],
                "hyac-app-runtime-app12345",
                7,
                "container-7",
                old_token_hash,
            )

        self.assertFalse(retried)
        remove_config.assert_not_called()
        self.assertEqual(state["runtime_generation"], 8)
        self.assertEqual(state["runtime_token_hash"], new_token_hash)
        self.assertEqual(
            docker_manager.running_apps[state["app_id"]],
            {
                "id": "container-8",
                "name": "hyac-app-runtime-app12345",
                "generation": 8,
            },
        )

    async def test_expired_generic_cleanup_owner_is_reclaimed_after_crash(self):
        expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        state = {
            "app_id": "APP12345",
            "runtime_generation": 7,
            "runtime_token_hash": None,
            "pending_traefik_cleanup_generation": 7,
            "runtime_cleanup_task_id": None,
            "runtime_cleanup_lease_owner": "cleanup:crashed-worker",
            "runtime_cleanup_lease_expires_at": expired_at,
        }
        collection = _ApplicationCollection(state)

        with (
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(
                docker_manager,
                "remove_traefik_web_config_for_generation",
                return_value=True,
            ),
        ):
            reclaimed = await docker_manager._cleanup_runtime_generation(
                state["app_id"],
                "hyac-app-runtime-app12345",
                7,
                None,
            )

        self.assertTrue(reclaimed)
        self.assertIsNone(state["runtime_cleanup_task_id"])
        self.assertIsNone(state["runtime_cleanup_lease_owner"])
        self.assertIsNone(state["runtime_cleanup_lease_expires_at"])
        self.assertIsNone(state["pending_traefik_cleanup_generation"])

    async def test_unexpired_generic_cleanup_owner_cannot_be_stolen(self):
        state = {
            "app_id": "APP12345",
            "runtime_generation": 7,
            "runtime_token_hash": None,
            "pending_traefik_cleanup_generation": 7,
            "runtime_cleanup_task_id": None,
            "runtime_cleanup_lease_owner": "cleanup:active-worker",
            "runtime_cleanup_lease_expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=5)
            ),
        }
        collection = _ApplicationCollection(state)

        with patch.object(
            docker_manager.mongodb_manager,
            "get_collection",
            return_value=collection,
        ):
            reclaimed = await docker_manager._cleanup_runtime_generation(
                state["app_id"],
                "hyac-app-runtime-app12345",
                7,
                None,
            )

        self.assertFalse(reclaimed)
        self.assertEqual(
            state["runtime_cleanup_lease_owner"], "cleanup:active-worker"
        )

    async def test_lifecycle_task_reclaims_an_expired_generic_owner(self):
        state = {
            "app_id": "APP12345",
            "runtime_generation": 7,
            "runtime_token_hash": "generation-token",
            "pending_traefik_cleanup_generation": 7,
            "runtime_cleanup_task_id": None,
            "runtime_cleanup_lease_owner": "cleanup:crashed-proxy",
            "runtime_cleanup_lease_expires_at": (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ),
        }
        task = {
            "task_id": "task-start",
            "status": docker_manager.TaskStatus.RUNNING,
            "lease_owner": "worker-a",
            "lease_expires_at": datetime.now(timezone.utc) + timedelta(minutes=1),
            "published_at": None,
        }
        application_collection = _ApplicationCollection(state)
        task_collection = _CleanupTaskCollection(task)

        def get_collection(model):
            if model is docker_manager.Task:
                return task_collection
            return application_collection

        with (
            patch.object(
                docker_manager.mongodb_manager,
                "client",
                _NoOpTransactionClient(),
            ),
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                side_effect=get_collection,
            ),
            patch.object(
                docker_manager,
                "remove_traefik_web_config_for_generation",
                return_value=True,
            ),
        ):
            reclaimed = await docker_manager._cleanup_runtime_generation(
                state["app_id"],
                "hyac-app-runtime-app12345",
                7,
                None,
                state["runtime_token_hash"],
                cleanup_task_id=task["task_id"],
                cleanup_lease_owner=task["lease_owner"],
            )

        self.assertTrue(reclaimed)
        self.assertIsNone(state["runtime_cleanup_task_id"])
        self.assertIsNone(state["runtime_cleanup_lease_owner"])
        self.assertIsNone(state["runtime_cleanup_lease_expires_at"])
        self.assertIsNone(state["pending_traefik_cleanup_generation"])
        self.assertIsNone(state["runtime_token_hash"])

    async def test_lifecycle_task_cannot_steal_an_unexpired_generic_owner(self):
        state = {
            "app_id": "APP12345",
            "runtime_generation": 7,
            "runtime_token_hash": "generation-token",
            "pending_traefik_cleanup_generation": 7,
            "runtime_cleanup_task_id": None,
            "runtime_cleanup_lease_owner": "cleanup:active-proxy",
            "runtime_cleanup_lease_expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=1)
            ),
        }
        task = {
            "task_id": "task-start",
            "status": docker_manager.TaskStatus.RUNNING,
            "lease_owner": "worker-a",
            "lease_expires_at": datetime.now(timezone.utc) + timedelta(minutes=1),
            "published_at": None,
        }
        application_collection = _ApplicationCollection(state)
        task_collection = _CleanupTaskCollection(task)

        def get_collection(model):
            if model is docker_manager.Task:
                return task_collection
            return application_collection

        with (
            patch.object(
                docker_manager.mongodb_manager,
                "client",
                _NoOpTransactionClient(),
            ),
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                side_effect=get_collection,
            ),
        ):
            reclaimed = await docker_manager._cleanup_runtime_generation(
                state["app_id"],
                "hyac-app-runtime-app12345",
                7,
                None,
                state["runtime_token_hash"],
                cleanup_task_id=task["task_id"],
                cleanup_lease_owner=task["lease_owner"],
            )

        self.assertFalse(reclaimed)
        self.assertEqual(
            "cleanup:active-proxy", state["runtime_cleanup_lease_owner"]
        )

    async def test_clear_expired_generic_owner_uses_exact_generation_owner_cas(self):
        expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_cleanup_task_id=None,
            runtime_cleanup_lease_owner="adopt:crashed-proxy",
            runtime_cleanup_lease_expires_at=expired_at,
        )
        state = vars(application).copy()
        collection = _ApplicationCollection(state)

        with patch.object(
            docker_manager.mongodb_manager,
            "get_collection",
            return_value=collection,
        ):
            cleared = await docker_manager.clear_expired_generic_runtime_owner(
                application
            )

        self.assertTrue(cleared)
        self.assertIsNone(state["runtime_cleanup_lease_owner"])
        self.assertIsNone(state["runtime_cleanup_lease_expires_at"])
        self.assertIsNone(application.runtime_cleanup_lease_owner)
        self.assertIsNone(application.runtime_cleanup_lease_expires_at)

    async def test_clear_expired_generic_owner_preserves_a_successor_claim(self):
        expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_cleanup_task_id=None,
            runtime_cleanup_lease_owner="adopt:crashed-proxy",
            runtime_cleanup_lease_expires_at=expired_at,
        )
        successor_expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        state = {
            **vars(application),
            "runtime_cleanup_lease_owner": "adopt:successor",
            "runtime_cleanup_lease_expires_at": successor_expiry,
        }
        collection = _ApplicationCollection(state)

        with patch.object(
            docker_manager.mongodb_manager,
            "get_collection",
            return_value=collection,
        ):
            cleared = await docker_manager.clear_expired_generic_runtime_owner(
                application
            )

        self.assertFalse(cleared)
        self.assertEqual("adopt:successor", state["runtime_cleanup_lease_owner"])
        self.assertEqual(successor_expiry, state["runtime_cleanup_lease_expires_at"])


class TraefikGenerationFenceTests(TestCase):
    def test_generation_mismatch_preserves_newer_config(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            docker_manager, "TRAEFIK_DYNAMIC_CONFIG_DIR", temp_dir
        ):
            docker_manager.create_traefik_web_config(
                "APP12345", "example.invalid", runtime_generation=8
            )
            config_path = os.path.join(temp_dir, "web-APP12345.yml")

            removed = docker_manager.remove_traefik_web_config_for_generation(
                "APP12345", 7
            )

            self.assertFalse(removed)
            self.assertTrue(os.path.exists(config_path))
            self.assertIn(
                "# hyac-runtime-generation: 8",
                Path(config_path).read_text(encoding="utf-8"),
            )

            self.assertTrue(
                docker_manager.remove_traefik_web_config_for_generation(
                    "APP12345", 8
                )
            )
            self.assertFalse(os.path.exists(config_path))

    def test_cleanup_marker_has_safe_default_and_is_not_public(self):
        marker_field = Application.model_fields[
            "pending_traefik_cleanup_generation"
        ]
        application = SimpleNamespace(
            model_dump=lambda **_kwargs: {
                "app_id": "APP12345",
                "pending_traefik_cleanup_generation": 7,
                "runtime_cleanup_lease_expires_at": "internal",
                "environment_variables": [],
                "ai_config": {},
                "notification": {},
            }
        )

        self.assertIsNone(marker_field.default)
        self.assertNotIn(
            "pending_traefik_cleanup_generation",
            applications_router.serialize_application(application),
        )
        self.assertIsNone(
            Application.model_fields["runtime_cleanup_lease_expires_at"].default
        )
        self.assertNotIn(
            "runtime_cleanup_lease_expires_at",
            applications_router.serialize_application(application),
        )
