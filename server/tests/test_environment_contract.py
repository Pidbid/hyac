import asyncio
import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from routers import runtime_control
from routers import settings as settings_router
from routers import applications as applications_router
from core import docker_manager
from core.environment_contract import RESERVED_ENV_KEYS
from models.applications_model import ApplicationStatus, EnvironmentVariable


class _Field:
    def __eq__(self, other):
        return other


class _Application:
    app_id = _Field()
    find_one = None


class RuntimeEnvironmentContractTests(IsolatedAsyncioTestCase):
    async def test_stopped_application_rejects_an_old_runtime_credential(self):
        token = "old-runtime-token"
        application = SimpleNamespace(
            app_id="APP12345",
            status=ApplicationStatus.STOPPED,
            runtime_generation=7,
            runtime_token_hash=runtime_control._runtime_digest(token),
            lifecycle_revision=11,
        )

        async def find_application(*_conditions):
            return application

        _Application.find_one = find_application
        with (
            patch.object(runtime_control, "Application", _Application),
            self.assertRaises(HTTPException) as raised,
        ):
            await runtime_control.require_runtime_identity(
                HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials=token,
                ),
                application.app_id,
                application.runtime_generation,
            )

        self.assertEqual(raised.exception.status_code, 401)

    def test_application_metadata_filters_reserved_environment_variables(self):
        application = SimpleNamespace(
            model_dump=MagicMock(
                return_value={
                    "app_id": "APP12345",
                    "db_password": "database-secret",
                    "runtime_token_hash": "digest",
                    "environment_variables": [
                        {"key": "SECRET_KEY", "value": "legacy-secret"},
                        {"key": "MONGODB_PASSWORD", "value": "legacy-mongo"},
                        {"key": "USER_ALLOWED", "value": "visible"},
                    ],
                    "ai_config": {"api_key": "ai-secret"},
                    "notification": {"email": {"password": "smtp-secret"}},
                }
            )
        )

        serialized = applications_router.serialize_application(application)

        self.assertEqual(
            serialized["environment_variables"],
            [{"key": "USER_ALLOWED", "value": "visible"}],
        )
        self.assertNotIn("db_password", serialized)
        self.assertNotIn("runtime_token_hash", serialized)

    def test_bootstrap_filters_persisted_reserved_keys_from_shared_contract(self):
        application = SimpleNamespace(
            model_dump=MagicMock(
                return_value={
                    "app_id": "APP12345",
                    "runtime_token_hash": "digest",
                    "environment_variables": [
                        {"key": "SECRET_KEY", "value": "legacy-secret"},
                        {"key": "MONGODB_PASSWORD", "value": "legacy-mongo"},
                        {"key": "USER_ALLOWED", "value": "visible"},
                    ],
                }
            )
        )

        public = runtime_control._public_application(application)

        self.assertEqual(
            public["environment_variables"],
            [{"key": "USER_ALLOWED", "value": "visible"}],
        )
        self.assertNotIn("runtime_token_hash", public)
        self.assertIs(runtime_control.RESERVED_ENV_KEYS, RESERVED_ENV_KEYS)
        self.assertIs(settings_router.RESERVED_ENV_KEYS, RESERVED_ENV_KEYS)
        self.assertIs(docker_manager.RESERVED_ENV_KEYS, RESERVED_ENV_KEYS)

    async def test_runtime_control_rejects_legacy_platform_secret_persistence(self):
        application = SimpleNamespace(
            app_id="APP12345",
            environment_variables=[],
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )

        async def find_application(*_conditions):
            return application

        _Application.find_one = find_application
        identity = runtime_control.RuntimeIdentity(
            app_id=application.app_id,
            generation=1,
        )
        with patch.object(runtime_control, "Application", _Application):
            for key in ("SECRET_KEY", "MONGODB_PASSWORD", "MONGODB_USERNAME"):
                with self.subTest(key=key):
                    with self.assertRaises(HTTPException) as raised:
                        await runtime_control.update_environment(
                            key,
                            runtime_control.RuntimeEnvironmentRequest(value="attack"),
                            identity,
                        )
                    self.assertEqual(raised.exception.status_code, 400)

        self.assertEqual(application.environment_variables, [])
        application.save.assert_not_awaited()

    async def test_runtime_environment_update_cannot_restore_revoked_authority(self):
        write_started = asyncio.Event()
        resume_write = asyncio.Event()
        captured_write = {}
        authoritative = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash="runtime-token-hash",
            lifecycle_revision=11,
            environment_revision=0,
            status=ApplicationStatus.RUNNING,
            environment_variables=[EnvironmentVariable(key="OLD", value="before")],
        )
        snapshot = SimpleNamespace(
            app_id=authoritative.app_id,
            runtime_generation=authoritative.runtime_generation,
            runtime_token_hash=authoritative.runtime_token_hash,
            lifecycle_revision=authoritative.lifecycle_revision,
            environment_revision=authoritative.environment_revision,
            status=authoritative.status,
            environment_variables=list(authoritative.environment_variables),
            update_timestamp=MagicMock(),
        )

        async def stale_full_save():
            write_started.set()
            await resume_write.wait()
            authoritative.runtime_generation = snapshot.runtime_generation
            authoritative.runtime_token_hash = snapshot.runtime_token_hash
            authoritative.lifecycle_revision = snapshot.lifecycle_revision
            authoritative.environment_revision = snapshot.environment_revision
            authoritative.status = snapshot.status
            authoritative.environment_variables = list(
                snapshot.environment_variables
            )

        snapshot.save = AsyncMock(side_effect=stale_full_save)

        class RuntimeCollection:
            async def update_one(self, query, update):
                captured_write["query"] = query
                captured_write["update"] = update
                write_started.set()
                await resume_write.wait()
                authority_matches = all(
                    query.get(field) == getattr(authoritative, field)
                    for field in (
                        "app_id",
                        "runtime_generation",
                        "runtime_token_hash",
                        "lifecycle_revision",
                        "environment_revision",
                    )
                )
                if authority_matches:
                    for field, value in update["$set"].items():
                        setattr(authoritative, field, value)
                return SimpleNamespace(matched_count=int(authority_matches))

        async def find_application(*_conditions):
            return snapshot

        _Application.find_one = find_application
        identity = runtime_control.RuntimeIdentity(
            app_id=authoritative.app_id,
            generation=authoritative.runtime_generation,
            runtime_token_hash=authoritative.runtime_token_hash,
            lifecycle_revision=authoritative.lifecycle_revision,
        )
        with (
            patch.object(runtime_control, "Application", _Application),
            patch.object(
                runtime_control,
                "mongodb_manager",
                SimpleNamespace(get_collection=MagicMock(return_value=RuntimeCollection())),
                create=True,
            ),
        ):
            update = asyncio.create_task(
                runtime_control.update_environment(
                    "NEW",
                    runtime_control.RuntimeEnvironmentRequest(value="after"),
                    identity,
                )
            )
            await asyncio.wait_for(write_started.wait(), timeout=1)
            authoritative.status = ApplicationStatus.STOPPING
            authoritative.lifecycle_revision = 12
            authoritative.runtime_token_hash = None
            resume_write.set()
            with self.assertRaises(HTTPException) as raised:
                await update

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(authoritative.status, ApplicationStatus.STOPPING)
        self.assertEqual(authoritative.lifecycle_revision, 12)
        self.assertIsNone(authoritative.runtime_token_hash)
        self.assertEqual(
            [(item.key, item.value) for item in authoritative.environment_variables],
            [("OLD", "before")],
        )
        self.assertEqual(
            captured_write["query"],
            {
                "app_id": "APP12345",
                "runtime_generation": 7,
                "runtime_token_hash": "runtime-token-hash",
                "lifecycle_revision": 11,
                "environment_revision": 0,
            },
        )
        self.assertEqual(
            set(captured_write["update"]["$set"]),
            {"environment_variables", "updated_at"},
        )
        self.assertEqual(
            captured_write["update"]["$inc"],
            {"environment_revision": 1},
        )

    async def test_same_generation_runtime_environment_writes_have_one_winner(self):
        authoritative = {
            "app_id": "APP12345",
            "runtime_generation": 7,
            "runtime_token_hash": "runtime-token-hash",
            "lifecycle_revision": 11,
            "environment_revision": 0,
            "environment_variables": [],
        }
        arrived = 0
        both_arrived = asyncio.Event()

        async def find_application(*_conditions):
            return SimpleNamespace(
                app_id=authoritative["app_id"],
                runtime_generation=authoritative["runtime_generation"],
                runtime_token_hash=authoritative["runtime_token_hash"],
                lifecycle_revision=authoritative["lifecycle_revision"],
                environment_revision=authoritative["environment_revision"],
                environment_variables=[
                    EnvironmentVariable.model_validate(item)
                    for item in authoritative["environment_variables"]
                ],
            )

        class RuntimeCollection:
            async def update_one(self, query, update):
                nonlocal arrived
                arrived += 1
                if arrived == 2:
                    both_arrived.set()
                await both_arrived.wait()
                if not self._matches(query):
                    return SimpleNamespace(matched_count=0)
                authoritative.update(update["$set"])
                for field, increment in update.get("$inc", {}).items():
                    authoritative[field] = authoritative.get(field, 0) + increment
                return SimpleNamespace(matched_count=1)

            @staticmethod
            def _matches(query):
                return all(authoritative.get(field) == expected for field, expected in query.items())

        _Application.find_one = find_application
        identity = runtime_control.RuntimeIdentity(
            app_id=authoritative["app_id"],
            generation=authoritative["runtime_generation"],
            runtime_token_hash=authoritative["runtime_token_hash"],
            lifecycle_revision=authoritative["lifecycle_revision"],
        )
        with (
            patch.object(runtime_control, "Application", _Application),
            patch.object(
                runtime_control,
                "mongodb_manager",
                SimpleNamespace(
                    get_collection=MagicMock(return_value=RuntimeCollection())
                ),
            ),
        ):
            results = await asyncio.gather(
                runtime_control.update_environment(
                    "FIRST",
                    runtime_control.RuntimeEnvironmentRequest(value="one"),
                    identity,
                ),
                runtime_control.update_environment(
                    "SECOND",
                    runtime_control.RuntimeEnvironmentRequest(value="two"),
                    identity,
                ),
                return_exceptions=True,
            )

        successes = [result for result in results if result is None]
        conflicts = [result for result in results if isinstance(result, HTTPException)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].status_code, 409)
        self.assertEqual(authoritative["environment_revision"], 1)
        self.assertEqual(len(authoritative["environment_variables"]), 1)

    async def test_runtime_environment_write_conflicts_after_console_revision_advance(self):
        write_started = asyncio.Event()
        resume_write = asyncio.Event()
        authoritative = {
            "app_id": "APP12345",
            "runtime_generation": 7,
            "runtime_token_hash": "runtime-token-hash",
            "lifecycle_revision": 11,
            "environment_revision": 0,
            "environment_variables": [
                {"key": "OLD", "value": "before"},
            ],
        }
        snapshot = SimpleNamespace(
            app_id=authoritative["app_id"],
            environment_revision=authoritative["environment_revision"],
            environment_variables=[EnvironmentVariable(key="OLD", value="before")],
        )

        async def find_application(*_conditions):
            return snapshot

        class RuntimeCollection:
            async def update_one(self, query, update):
                write_started.set()
                await resume_write.wait()
                if not all(
                    authoritative.get(field) == expected
                    for field, expected in query.items()
                ):
                    return SimpleNamespace(matched_count=0)
                authoritative.update(update["$set"])
                for field, increment in update.get("$inc", {}).items():
                    authoritative[field] = authoritative.get(field, 0) + increment
                return SimpleNamespace(matched_count=1)

        _Application.find_one = find_application
        identity = runtime_control.RuntimeIdentity(
            app_id=authoritative["app_id"],
            generation=authoritative["runtime_generation"],
            runtime_token_hash=authoritative["runtime_token_hash"],
            lifecycle_revision=authoritative["lifecycle_revision"],
        )
        with (
            patch.object(runtime_control, "Application", _Application),
            patch.object(
                runtime_control,
                "mongodb_manager",
                SimpleNamespace(
                    get_collection=MagicMock(return_value=RuntimeCollection())
                ),
            ),
        ):
            runtime_write = asyncio.create_task(
                runtime_control.update_environment(
                    "RUNTIME",
                    runtime_control.RuntimeEnvironmentRequest(value="stale"),
                    identity,
                )
            )
            await asyncio.wait_for(write_started.wait(), timeout=1)
            authoritative["environment_variables"].append(
                {"key": "CONSOLE", "value": "kept"}
            )
            authoritative["environment_revision"] = 1
            resume_write.set()
            result = await asyncio.gather(runtime_write, return_exceptions=True)

        self.assertIsInstance(result[0], HTTPException)
        self.assertEqual(result[0].status_code, 409)
        self.assertEqual(authoritative["environment_revision"], 1)
        self.assertEqual(
            authoritative["environment_variables"],
            [
                {"key": "OLD", "value": "before"},
                {"key": "CONSOLE", "value": "kept"},
            ],
        )
