import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from core import migrations
from models.applications_model import (
    AIConfig,
    ApplicationStatus,
    NotificationConfig,
)
from routers import settings as settings_router
from core.environment_contract import RESERVED_ENV_KEYS


class _Field:
    def __eq__(self, other):
        return other


class _Application:
    app_id = _Field()
    users = _Field()
    find_one = None


class _SettingsApplicationCollection:
    def __init__(self, application):
        self.application = application
        self.update_calls = []

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(matched_count=1)


class SettingsSecretHandlingTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = SimpleNamespace(
            app_id="app-1",
            status=ApplicationStatus.RUNNING,
            runtime_generation=4,
            runtime_token_hash="runtime-token-hash",
            lifecycle_revision=6,
            environment_revision=0,
            cors_revision=0,
            notification_revision=0,
            ai_config_revision=0,
            notification=NotificationConfig.model_validate(
                {
                    "email": {
                        "enabled": True,
                        "smtpServer": "smtp.old.invalid",
                        "username": "mailer",
                        "password": "stored-smtp-secret",
                    }
                }
            ),
            ai_config=AIConfig(
                provider="openai",
                model="old-model",
                api_key="stored-ai-secret",
                base_url="https://old.invalid/v1",
            ),
            save=AsyncMock(),
        )

        async def find_application(*_conditions):
            return self.app

        _Application.find_one = find_application
        self.application_patch = patch.object(
            settings_router, "Application", _Application
        )
        self.application_patch.start()
        self.addCleanup(self.application_patch.stop)
        self.collection = _SettingsApplicationCollection(self.app)
        self.mongodb_patch = patch.object(
            settings_router,
            "mongodb_manager",
            SimpleNamespace(
                get_collection=MagicMock(return_value=self.collection)
            ),
            create=True,
        )
        self.mongodb_patch.start()
        self.addCleanup(self.mongodb_patch.stop)
        self.user = SimpleNamespace(username="admin")

    async def test_settings_reads_redact_stored_secrets_without_mutating_app(self):
        notification_response = await settings_router.notification_data(
            settings_router.NotificationDataRequest(appId="app-1"), self.user
        )
        ai_response = await settings_router.ai_config_data(
            settings_router.AIConfigDataRequest(appId="app-1"), self.user
        )

        self.assertEqual(notification_response.data.email.password, "")
        self.assertEqual(ai_response.data.api_key, "")
        self.assertEqual(
            self.app.notification.email.password, "stored-smtp-secret"
        )
        self.assertEqual(self.app.ai_config.api_key, "stored-ai-secret")

    async def test_empty_secret_updates_preserve_existing_values(self):
        notification = NotificationConfig.model_validate(
            {
                "email": {
                    "enabled": True,
                    "smtpServer": "smtp.new.invalid",
                    "username": "mailer",
                    "password": "",
                }
            }
        )
        ai_config = AIConfig(
            provider="openai",
            model="new-model",
            api_key="",
            base_url="https://new.invalid/v1",
        )

        await settings_router.notification_update(
            settings_router.NotificationUpdateRequest(
                appId="app-1", config=notification
            ),
            self.user,
        )
        await settings_router.ai_config_update(
            settings_router.AIConfigUpdateRequest(appId="app-1", config=ai_config),
            self.user,
        )

        self.assertEqual(self.app.notification.email.password, "stored-smtp-secret")
        self.assertEqual(
            self.app.notification.email.smtpServer, "smtp.new.invalid"
        )
        self.assertEqual(self.app.ai_config.api_key, "stored-ai-secret")
        self.assertEqual(self.app.ai_config.model, "new-model")
        self.app.save.assert_not_awaited()
        self.assertEqual(len(self.collection.update_calls), 2)

    async def test_console_setting_update_cannot_restore_lifecycle_snapshot(self):
        write_started = asyncio.Event()
        resume_write = asyncio.Event()
        captured_write = {}
        authoritative = SimpleNamespace(
            app_id="app-1",
            status=ApplicationStatus.RUNNING,
            runtime_generation=4,
            runtime_token_hash="runtime-token-hash",
            lifecycle_revision=6,
            notification_revision=0,
            notification=self.app.notification.model_copy(deep=True),
        )
        snapshot = SimpleNamespace(
            app_id=authoritative.app_id,
            status=authoritative.status,
            runtime_generation=authoritative.runtime_generation,
            runtime_token_hash=authoritative.runtime_token_hash,
            lifecycle_revision=authoritative.lifecycle_revision,
            notification_revision=authoritative.notification_revision,
            notification=authoritative.notification.model_copy(deep=True),
        )

        async def stale_full_save():
            write_started.set()
            await resume_write.wait()
            authoritative.status = snapshot.status
            authoritative.runtime_generation = snapshot.runtime_generation
            authoritative.runtime_token_hash = snapshot.runtime_token_hash
            authoritative.lifecycle_revision = snapshot.lifecycle_revision
            authoritative.notification_revision = snapshot.notification_revision
            authoritative.notification = snapshot.notification

        snapshot.save = AsyncMock(side_effect=stale_full_save)

        class NarrowCollection:
            async def update_one(self, query, update):
                captured_write["query"] = query
                captured_write["update"] = update
                write_started.set()
                await resume_write.wait()
                for field, value in update["$set"].items():
                    if field == "notification":
                        authoritative.notification = NotificationConfig.model_validate(
                            value
                        )
                return SimpleNamespace(matched_count=1)

        async def find_application(*_conditions):
            return snapshot

        _Application.find_one = find_application
        with patch.object(
            settings_router,
            "mongodb_manager",
            SimpleNamespace(
                get_collection=MagicMock(return_value=NarrowCollection())
            ),
            create=True,
        ):
            update = asyncio.create_task(
                settings_router.notification_update(
                    settings_router.NotificationUpdateRequest(
                        appId="app-1",
                        config=NotificationConfig.model_validate(
                            {
                                "email": {
                                    "enabled": True,
                                    "smtpServer": "smtp.new.invalid",
                                    "username": "mailer",
                                    "password": "new-secret",
                                }
                            }
                        ),
                    ),
                    self.user,
                )
            )
            await asyncio.wait_for(write_started.wait(), timeout=1)
            authoritative.status = ApplicationStatus.STOPPING
            authoritative.runtime_generation = 5
            authoritative.runtime_token_hash = None
            authoritative.lifecycle_revision = 7
            resume_write.set()
            await update

        self.assertEqual(authoritative.status, ApplicationStatus.STOPPING)
        self.assertEqual(authoritative.runtime_generation, 5)
        self.assertIsNone(authoritative.runtime_token_hash)
        self.assertEqual(authoritative.lifecycle_revision, 7)
        self.assertEqual(
            authoritative.notification.email.smtpServer,
            "smtp.new.invalid",
        )
        self.assertEqual(
            captured_write["query"],
            {
                "app_id": "app-1",
                "users": "admin",
                "notification_revision": 0,
            },
        )
        self.assertEqual(
            set(captured_write["update"]["$set"]),
            {"notification", "updated_at"},
        )
        self.assertEqual(
            captured_write["update"]["$inc"],
            {"notification_revision": 1},
        )


class SettingsConcurrentUpdateTests(IsolatedAsyncioTestCase):
    async def test_concurrent_environment_adds_preserve_both_variables(self):
        authoritative = {
            "app_id": "app-1",
            "users": ["admin"],
            "environment_variables": [],
            "environment_revision": 0,
        }
        collection = _ConcurrentSettingsCollection(
            authoritative, required_arrivals=2, auto_release=True
        )

        async def find_application(*_conditions):
            return SimpleNamespace(
                app_id="app-1",
                environment_revision=authoritative["environment_revision"],
                environment_variables=[
                    settings_router.EnvironmentVariable.model_validate(item)
                    for item in authoritative["environment_variables"]
                ],
            )

        _Application.find_one = find_application
        user = SimpleNamespace(username="admin")
        with (
            patch.object(settings_router, "Application", _Application),
            patch.object(
                settings_router,
                "mongodb_manager",
                SimpleNamespace(
                    get_collection=MagicMock(return_value=collection)
                ),
            ),
        ):
            await asyncio.gather(
                settings_router.env_add(
                    settings_router.EnvAddRequest(
                        appId="app-1", key="FIRST", value="one"
                    ),
                    user,
                ),
                settings_router.env_add(
                    settings_router.EnvAddRequest(
                        appId="app-1", key="SECOND", value="two"
                    ),
                    user,
                ),
            )

        self.assertEqual(
            {
                item["key"]: item["value"]
                for item in authoritative["environment_variables"]
            },
            {"FIRST": "one", "SECOND": "two"},
        )
        self.assertEqual(authoritative["environment_revision"], 2)

    async def test_blank_notification_secret_cannot_undo_concurrent_rotation(self):
        authoritative = {
            "app_id": "app-1",
            "users": ["admin"],
            "notification_revision": 0,
            "notification": NotificationConfig.model_validate(
                {"email": {"password": "old-secret"}}
            ).model_dump(mode="python"),
        }
        started = asyncio.Event()
        resume = asyncio.Event()
        collection = _ConcurrentSettingsCollection(
            authoritative, started=started, resume=resume
        )
        snapshot = SimpleNamespace(
            app_id="app-1",
            notification_revision=0,
            notification=NotificationConfig.model_validate(
                authoritative["notification"]
            ),
        )

        async def find_application(*_conditions):
            return snapshot

        _Application.find_one = find_application
        with (
            patch.object(settings_router, "Application", _Application),
            patch.object(
                settings_router,
                "mongodb_manager",
                SimpleNamespace(
                    get_collection=MagicMock(return_value=collection)
                ),
            ),
        ):
            update = asyncio.create_task(
                settings_router.notification_update(
                    settings_router.NotificationUpdateRequest(
                        appId="app-1",
                        config=NotificationConfig.model_validate(
                            {
                                "email": {
                                    "smtpServer": "smtp.new.invalid",
                                    "password": "",
                                }
                            }
                        ),
                    ),
                    SimpleNamespace(username="admin"),
                )
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            authoritative["notification"]["email"]["password"] = "rotated-secret"
            authoritative["notification_revision"] = 1
            resume.set()
            result = await asyncio.gather(update, return_exceptions=True)

        self.assertIsInstance(result[0], HTTPException)
        self.assertEqual(result[0].status_code, 409)
        self.assertEqual(
            authoritative["notification"]["email"]["password"],
            "rotated-secret",
        )

    async def test_blank_ai_secret_cannot_undo_concurrent_rotation(self):
        authoritative = {
            "app_id": "app-1",
            "users": ["admin"],
            "ai_config_revision": 0,
            "ai_config": AIConfig(
                provider="openai", model="old", api_key="old-secret"
            ).model_dump(mode="python"),
        }
        started = asyncio.Event()
        resume = asyncio.Event()
        collection = _ConcurrentSettingsCollection(
            authoritative, started=started, resume=resume
        )
        snapshot = SimpleNamespace(
            app_id="app-1",
            ai_config_revision=0,
            ai_config=AIConfig.model_validate(authoritative["ai_config"]),
        )

        async def find_application(*_conditions):
            return snapshot

        _Application.find_one = find_application
        with (
            patch.object(settings_router, "Application", _Application),
            patch.object(
                settings_router,
                "mongodb_manager",
                SimpleNamespace(
                    get_collection=MagicMock(return_value=collection)
                ),
            ),
        ):
            update = asyncio.create_task(
                settings_router.ai_config_update(
                    settings_router.AIConfigUpdateRequest(
                        appId="app-1",
                        config=AIConfig(
                            provider="openai", model="new", api_key=""
                        ),
                    ),
                    SimpleNamespace(username="admin"),
                )
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            authoritative["ai_config"]["api_key"] = "rotated-secret"
            authoritative["ai_config_revision"] = 1
            resume.set()
            result = await asyncio.gather(update, return_exceptions=True)

        self.assertIsInstance(result[0], HTTPException)
        self.assertEqual(result[0].status_code, 409)
        self.assertEqual(authoritative["ai_config"]["api_key"], "rotated-secret")


class _ConcurrentSettingsCollection:
    def __init__(
        self,
        authoritative,
        *,
        required_arrivals=1,
        auto_release=False,
        started=None,
        resume=None,
    ):
        self.authoritative = authoritative
        self.required_arrivals = required_arrivals
        self.auto_release = auto_release
        self.started = started or asyncio.Event()
        self.resume = resume or asyncio.Event()
        self.arrivals = 0

    async def update_one(self, query, update):
        self.arrivals += 1
        if self.arrivals >= self.required_arrivals:
            self.started.set()
            if self.auto_release:
                self.resume.set()
        await self.resume.wait()
        if not self._matches(query):
            return SimpleNamespace(matched_count=0)

        if isinstance(update, list):
            for stage in update:
                for field, expression in stage.get("$set", {}).items():
                    self.authoritative[field] = self._evaluate(expression)
        else:
            self.authoritative.update(update.get("$set", {}))
            for field, increment in update.get("$inc", {}).items():
                self.authoritative[field] = (
                    self.authoritative.get(field, 0) + increment
                )
        return SimpleNamespace(matched_count=1)

    def _matches(self, query):
        for field, expected in query.items():
            actual = self.authoritative.get(field)
            if field == "users" and not isinstance(expected, list):
                if expected not in (actual or []):
                    return False
            elif actual != expected:
                return False
        return True

    def _evaluate(self, expression, variables=None):
        variables = variables or {}
        if isinstance(expression, str):
            if expression.startswith("$$"):
                variable_path = expression[2:].split(".")
                value = variables[variable_path[0]]
                for part in variable_path[1:]:
                    value = value.get(part)
                return value
            if expression.startswith("$"):
                return self.authoritative.get(expression[1:])
            return expression
        if isinstance(expression, list):
            return [self._evaluate(item, variables) for item in expression]
        if not isinstance(expression, dict):
            return expression
        if "$ifNull" in expression:
            value, fallback = expression["$ifNull"]
            evaluated = self._evaluate(value, variables)
            return self._evaluate(fallback, variables) if evaluated is None else evaluated
        if "$literal" in expression:
            return expression["$literal"]
        if "$concatArrays" in expression:
            result = []
            for items in expression["$concatArrays"]:
                result.extend(self._evaluate(items, variables))
            return result
        if "$filter" in expression:
            spec = expression["$filter"]
            result = []
            for item in self._evaluate(spec["input"], variables):
                scoped = {**variables, spec.get("as", "this"): item}
                if self._evaluate(spec["cond"], scoped):
                    result.append(item)
            return result
        if "$not" in expression:
            values = self._evaluate(expression["$not"], variables)
            return not values[0]
        if "$in" in expression:
            value, choices = self._evaluate(expression["$in"], variables)
            return value in choices
        if "$add" in expression:
            return sum(self._evaluate(expression["$add"], variables))
        return {
            key: self._evaluate(value, variables)
            for key, value in expression.items()
        }


class _Collection:
    def __init__(self, *, marker=None):
        self.find_one = AsyncMock(return_value=marker)
        self.update_many = AsyncMock()
        self.insert_one = AsyncMock()


class SecurityMigrationTests(IsolatedAsyncioTestCase):
    async def test_migration_backfills_per_domain_settings_revisions(self):
        settings_collection = _Collection()
        applications_collection = _Collection()
        collections = {
            "settings": settings_collection,
            "users": _Collection(marker={"name": "unused"}),
            "applications": applications_collection,
            "functions": _Collection(),
            "tasks": _Collection(),
        }

        with patch.object(migrations.mongodb_manager, "db", collections):
            await migrations.run_security_migrations()

        revision_defaults = {
            tuple(call.args[1].get("$set", {}).items())
            for call in applications_collection.update_many.await_args_list
            if "$set" in call.args[1]
        }
        for field in (
            "environment_revision",
            "cors_revision",
            "notification_revision",
            "ai_config_revision",
        ):
            self.assertIn(((field, 0),), revision_defaults)

    async def test_application_migrations_are_idempotent_and_backfill_authority_fields(
        self,
    ):
        class StatefulSettingsCollection:
            def __init__(self):
                self.markers = set()

            async def find_one(self, query):
                return (
                    {"name": query["name"]}
                    if query["name"] in self.markers
                    else None
                )

            async def insert_one(self, document):
                self.markers.add(document["name"])

        class StatefulApplicationCollection:
            def __init__(self):
                self.documents = [
                    {
                        "environment_variables": [
                            {"key": "SECRET_KEY", "value": "legacy"},
                            {"key": "MONGODB_PASSWORD", "value": "legacy"},
                            {"key": "USER_ALLOWED", "value": "visible"},
                        ]
                    }
                ]
                self.reserved_cleanup_calls = 0
                self.lifecycle_backfill_calls = 0
                self.runtime_authority_backfill_calls = 0
                self.runtime_cleanup_backfill_calls = 0

            async def update_many(self, query, update):
                if update == {"$set": {"lifecycle_revision": 0}}:
                    self.lifecycle_backfill_calls += 1
                    for document in self.documents:
                        document.setdefault("lifecycle_revision", 0)
                    return
                authority_defaults = {
                    "runtime_generation": 0,
                    "runtime_token_hash": None,
                    "lifecycle_completed_task_id": None,
                }
                if "$set" in update and update["$set"] in (
                    {field: value}
                    for field, value in authority_defaults.items()
                ):
                    self.runtime_authority_backfill_calls += 1
                    for field, value in update["$set"].items():
                        self.assert_missing_filter(query, field)
                        for document in self.documents:
                            document.setdefault(field, value)
                    return
                cleanup_fields = {
                    "runtime_cleanup_task_id",
                    "runtime_cleanup_lease_owner",
                    "runtime_cleanup_lease_expires_at",
                }
                set_fields = update.get("$set", {})
                if len(set_fields) == 1:
                    field, value = next(iter(set_fields.items()))
                    if field in cleanup_fields and value is None:
                        self.assert_missing_filter(query, field)
                        self.runtime_cleanup_backfill_calls += 1
                        for document in self.documents:
                            document.setdefault(field, None)
                        return
                if "$pull" not in update:
                    return
                self.reserved_cleanup_calls += 1
                reserved = set(
                    update["$pull"]["environment_variables"]["key"]["$in"]
                )
                for document in self.documents:
                    document["environment_variables"] = [
                        item
                        for item in document["environment_variables"]
                        if item["key"] not in reserved
                    ]

            @staticmethod
            def assert_missing_filter(query, field):
                if query != {field: {"$exists": False}}:
                    raise AssertionError(
                        f"expected a missing-field filter for {field}: {query!r}"
                    )

        settings_collection = StatefulSettingsCollection()
        applications_collection = StatefulApplicationCollection()

        class StatefulTaskCollection:
            def __init__(self):
                self.documents = [{}]
                self.publication_backfill_calls = 0

            async def update_many(self, query, update):
                publication_fields = {
                    "published_at",
                    "published_status",
                    "published_lifecycle_revision",
                    "published_runtime_generation",
                }
                set_fields = update.get("$set", {}) if isinstance(update, dict) else {}
                if len(set_fields) == 1:
                    field, value = next(iter(set_fields.items()))
                    if field in publication_fields and value is None:
                        if query != {field: {"$exists": False}}:
                            raise AssertionError(
                                f"expected missing publication filter for {field}"
                            )
                        self.publication_backfill_calls += 1
                        for document in self.documents:
                            document.setdefault(field, None)

        tasks_collection = StatefulTaskCollection()
        collections = {
            "settings": settings_collection,
            "users": _Collection(),
            "applications": applications_collection,
            "functions": _Collection(),
            "tasks": tasks_collection,
        }

        with patch.object(migrations.mongodb_manager, "db", collections):
            await migrations.run_security_migrations()
            await migrations.run_security_migrations()

        self.assertEqual(
            applications_collection.documents[0]["environment_variables"],
            [{"key": "USER_ALLOWED", "value": "visible"}],
        )
        self.assertEqual(applications_collection.reserved_cleanup_calls, 1)
        self.assertEqual(applications_collection.lifecycle_backfill_calls, 1)
        self.assertEqual(
            applications_collection.runtime_authority_backfill_calls, 3
        )
        self.assertEqual(
            applications_collection.runtime_cleanup_backfill_calls, 3
        )
        self.assertEqual(
            applications_collection.documents[0]["lifecycle_revision"], 0
        )
        self.assertEqual(
            applications_collection.documents[0]["runtime_generation"], 0
        )
        self.assertIsNone(
            applications_collection.documents[0]["runtime_token_hash"]
        )
        self.assertIsNone(
            applications_collection.documents[0]["lifecycle_completed_task_id"]
        )
        self.assertIsNone(
            applications_collection.documents[0]["runtime_cleanup_task_id"]
        )
        self.assertIsNone(
            applications_collection.documents[0]["runtime_cleanup_lease_owner"]
        )
        self.assertIsNone(
            applications_collection.documents[0][
                "runtime_cleanup_lease_expires_at"
            ]
        )
        self.assertEqual(tasks_collection.publication_backfill_calls, 4)
        self.assertEqual(
            tasks_collection.documents[0],
            {
                "published_at": None,
                "published_status": None,
                "published_lifecycle_revision": None,
                "published_runtime_generation": None,
            },
        )
        self.assertTrue(RESERVED_ENV_KEYS)

    async def test_migration_normalizes_function_limits_and_releases_legacy_running_tasks(
        self,
    ):
        collections = {
            "settings": _Collection(),
            "users": _Collection(),
            "applications": _Collection(),
            "functions": _Collection(),
            "tasks": _Collection(),
        }

        with patch.object(migrations.mongodb_manager, "db", collections):
            await migrations.run_security_migrations()

        function_calls = collections["functions"].update_many.await_args_list
        self.assertEqual(len(function_calls), 2)
        function_filter, function_update = function_calls[0].args
        self.assertEqual(function_filter, {})
        limit_set = function_update[0]["$set"]

        auth_filter, auth_update = function_calls[1].args
        self.assertEqual(auth_filter, {"requires_auth": {"$exists": False}})
        self.assertEqual(auth_update, {"$set": {"requires_auth": True}})

        samples = [
            ({"memory_limit": 64, "timeout": 0}, (128, 1)),
            ({"memory_limit": 8192, "timeout": 900}, (4096, 300)),
            ({}, (128, 5)),
        ]
        for document, expected in samples:
            normalized = {
                name: self._evaluate(expression, document)
                for name, expression in limit_set.items()
            }
            self.assertEqual(
                (normalized["memory_limit"], normalized["timeout"]), expected
            )

        task_calls = collections["tasks"].update_many.await_args_list
        self.assertEqual(len(task_calls), 6)
        release_filter, release_update = task_calls[1].args
        self.assertEqual(
            release_filter, {"status": "running", "lease_expires_at": None}
        )
        released_at = release_update["$set"]["lease_expires_at"]
        self.assertIsInstance(released_at, datetime)
        self.assertLessEqual(released_at, datetime.now(timezone.utc))
        publication_fields = {
            next(iter(call.args[0]))
            for call in task_calls[2:]
        }
        self.assertEqual(
            publication_fields,
            {
                "published_at",
                "published_status",
                "published_lifecycle_revision",
                "published_runtime_generation",
            },
        )

    @classmethod
    def _evaluate(cls, expression, document):
        if isinstance(expression, str) and expression.startswith("$"):
            return document.get(expression[1:])
        if not isinstance(expression, dict):
            return expression
        if "$ifNull" in expression:
            value, fallback = expression["$ifNull"]
            evaluated = cls._evaluate(value, document)
            return fallback if evaluated is None else evaluated
        if "$max" in expression:
            return max(cls._evaluate(value, document) for value in expression["$max"])
        if "$min" in expression:
            return min(cls._evaluate(value, document) for value in expression["$min"])
        raise AssertionError(f"Unsupported aggregation expression: {expression}")
