import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("DEV_MODE", "true")

from core import initialization
import main as server_main


REPO_ROOT = Path(__file__).resolve().parents[2]


class _Field:
    def __eq__(self, other):
        return ("eq", other)

    def __ne__(self, other):
        return ("ne", other)


class _MemoryDocument:
    record = None
    created = []
    bulk_update_calls = []
    bulk_update_error = None

    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)
        self.app_id = getattr(self, "app_id", "DEMO1234")
        self.function_id = getattr(self, "function_id", "FUNCTION1234")
        self.users = list(getattr(self, "users", []))
        self.update_calls = []
        type(self).created.append(self)

    @classmethod
    async def find_one(cls, *_args, **_kwargs):
        return cls.record

    @classmethod
    def find_all(cls):
        return _MemoryQuery(cls)

    async def insert(self):
        type(self).record = self

    async def update(self, operation):
        self.update_calls.append(operation)
        for field, value in operation.get("$addToSet", {}).items():
            collection = getattr(self, field)
            if value not in collection:
                collection.append(value)


class _MemoryQuery:
    def __init__(self, document_type):
        self.document_type = document_type

    async def update(self, operation):
        if self.document_type.bulk_update_error is not None:
            raise self.document_type.bulk_update_error
        self.document_type.bulk_update_calls.append(operation)
        record = self.document_type.record
        if record is not None:
            await record.update(operation)


class _MemoryApplication(_MemoryDocument):
    app_name = _Field()


class _MemoryFunction(_MemoryDocument):
    function_name = _Field()
    app_id = _Field()


class _MemoryUser:
    username = _Field()
    disabled = _Field()
    records = []

    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)
        self.roles = list(getattr(self, "roles", []))
        self.disabled = getattr(self, "disabled", False)
        self.refresh_token_hash = getattr(self, "refresh_token_hash", None)

    @classmethod
    async def find_one(cls, condition):
        operation, username = condition
        if operation != "eq":
            raise AssertionError(f"unexpected user condition: {condition}")
        return next(
            (record for record in cls.records if record.username == username), None
        )

    @classmethod
    def find(cls, *conditions):
        return _MemoryUserQuery(cls, conditions)

    async def insert(self):
        type(self).records.append(self)

    async def update(self, operation):
        for field, value in operation.get("$set", {}).items():
            setattr(self, field, value)
        for field, amount in operation.get("$inc", {}).items():
            setattr(self, field, getattr(self, field, 0) + amount)


class _MemoryUserQuery:
    def __init__(self, document_type, conditions):
        self.document_type = document_type
        self.conditions = conditions

    async def update(self, operation):
        operation_name, username = self.conditions[0]
        if operation_name != "ne":
            raise AssertionError(f"unexpected user condition: {self.conditions}")
        for record in self.document_type.records:
            if record.username == username:
                continue
            if len(self.conditions) > 1:
                disabled_operation, disabled_value = self.conditions[1]
                if disabled_operation != "eq" or record.disabled != disabled_value:
                    continue
            if record.username != username:
                await record.update(operation)


class DemoMembershipInitializationTests(IsolatedAsyncioTestCase):
    def setUp(self):
        for document in (_MemoryApplication, _MemoryFunction):
            document.record = None
            document.created = []
            document.bulk_update_calls = []
            document.bulk_update_error = None
        _MemoryUser.records = []

    async def test_fresh_demo_records_use_the_configured_admin(self):
        with (
            patch.object(initialization, "Application", _MemoryApplication),
            patch.object(initialization, "Function", _MemoryFunction),
            patch.object(initialization.settings, "DEFAULT_ADMIN_USER", "operator"),
            patch.object(
                initialization,
                "create_mongodb_user",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                initialization.app_storage_service,
                "ensure_ready",
                new=AsyncMock(),
            ),
            patch.object(
                initialization.InitializationService,
                "_is_database_empty",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                initialization.InitializationService,
                "initialize_default_user",
                new=AsyncMock(),
            ),
            patch.object(
                initialization.InitializationService,
                "initialize_functions_templates",
                new=AsyncMock(),
            ),
            patch.object(
                initialization.InitializationService,
                "initialize_system_tasks",
                new=AsyncMock(),
            ),
        ):
            await initialization.InitializationService.check_and_initialize()

        self.assertEqual(["operator"], _MemoryApplication.record.users)
        self.assertEqual(["operator"], _MemoryFunction.record.users)

    async def test_existing_demo_records_add_admin_once_without_dropping_users(self):
        application = _MemoryApplication(
            app_name="demo",
            app_id="DEMO1234",
            db_password="existing-password",
            users=["existing-user"],
        )
        function = _MemoryFunction(
            function_name="Hello",
            app_id="DEMO1234",
            users=["existing-user"],
        )
        _MemoryApplication.record = application
        _MemoryFunction.record = function

        with (
            patch.object(initialization, "Application", _MemoryApplication),
            patch.object(initialization, "Function", _MemoryFunction),
            patch.object(initialization.settings, "DEFAULT_ADMIN_USER", "operator"),
            patch.object(
                initialization.InitializationService,
                "_is_database_empty",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                initialization.InitializationService,
                "initialize_default_user",
                new=AsyncMock(),
            ),
            patch.object(
                initialization.InitializationService,
                "initialize_system_tasks",
                new=AsyncMock(),
            ),
        ):
            for _ in range(2):
                await initialization.InitializationService.check_and_initialize()

        self.assertEqual(["existing-user", "operator"], application.users)
        self.assertEqual(["existing-user", "operator"], function.users)
        self.assertEqual(
            [
                {"$addToSet": {"users": "operator"}},
                {"$addToSet": {"users": "operator"}},
            ],
            _MemoryApplication.bulk_update_calls,
        )
        self.assertEqual(
            [
                {"$addToSet": {"users": "operator"}},
                {"$addToSet": {"users": "operator"}},
            ],
            _MemoryFunction.bulk_update_calls,
        )

    async def test_nonempty_database_establishes_one_authoritative_admin(self):
        application = _MemoryApplication(
            app_name="legacy",
            app_id="LEGACY01",
            db_password="existing-password",
            users=["legacy-a"],
        )
        function = _MemoryFunction(
            function_name="Legacy",
            app_id="LEGACY01",
            users=["legacy-b"],
        )
        _MemoryApplication.record = application
        _MemoryFunction.record = function
        _MemoryUser.records = [
            _MemoryUser(
                username="legacy-a",
                password="hash-a",
                roles=["admin"],
                disabled=False,
                refresh_token_hash="refresh-a",
            ),
            _MemoryUser(
                username="legacy-b",
                password="hash-b",
                roles=["admin"],
                disabled=False,
                refresh_token_hash="refresh-b",
            ),
        ]

        with (
            patch.object(initialization, "Application", _MemoryApplication),
            patch.object(initialization, "Function", _MemoryFunction),
            patch.object(initialization, "User", _MemoryUser),
            patch.object(initialization, "hash_password", return_value="operator-hash"),
            patch.object(initialization.settings, "DEFAULT_ADMIN_USER", "operator"),
            patch.object(
                initialization.settings,
                "DEFAULT_ADMIN_PASSWORD",
                "operator-password",
            ),
            patch.object(
                initialization.InitializationService,
                "_is_database_empty",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                initialization.InitializationService,
                "initialize_demo_application",
                new=AsyncMock(),
            ) as demo_application,
            patch.object(
                initialization.InitializationService,
                "initialize_demo_functions",
                new=AsyncMock(),
            ) as demo_functions,
            patch.object(
                initialization.InitializationService,
                "initialize_functions_templates",
                new=AsyncMock(),
            ) as demo_templates,
            patch.object(
                initialization.InitializationService,
                "initialize_system_tasks",
                new=AsyncMock(),
            ),
        ):
            await initialization.InitializationService.check_and_initialize()

        operator = next(
            user for user in _MemoryUser.records if user.username == "operator"
        )
        self.assertFalse(operator.disabled)
        self.assertIn("admin", operator.roles)
        for legacy in (
            user for user in _MemoryUser.records if user.username != "operator"
        ):
            self.assertTrue(legacy.disabled)
            self.assertIsNone(legacy.refresh_token_hash)
        self.assertIn("operator", application.users)
        self.assertIn("operator", function.users)
        demo_application.assert_not_awaited()
        demo_functions.assert_not_awaited()
        demo_templates.assert_not_awaited()

    async def test_lifespan_runs_raw_identity_migration_before_beanie(self):
        order = []

        async def record(name):
            order.append(name)

        async def stop_after_initialization():
            await record("initialize")
            raise RuntimeError("stop after initialization")

        async def record_raw_migration():
            await record("raw-migration")

        async def record_beanie():
            await record("beanie")

        async def record_security_migration():
            await record("security-migration")

        with (
            patch.object(
                server_main,
                "run_pre_beanie_migrations",
                new=AsyncMock(side_effect=record_raw_migration),
            ),
            patch.object(
                server_main.mongodb_manager,
                "init_beanie",
                new=AsyncMock(side_effect=record_beanie),
            ),
            patch.object(
                server_main,
                "run_security_migrations",
                new=AsyncMock(side_effect=record_security_migration),
            ),
            patch.object(
                initialization.InitializationService,
                "check_and_initialize",
                new=AsyncMock(side_effect=stop_after_initialization),
            ),
        ):
            context = server_main.lifespan(SimpleNamespace())
            with self.assertRaisesRegex(RuntimeError, "stop after initialization"):
                await context.__aenter__()

        self.assertEqual(
            ["raw-migration", "beanie", "security-migration", "initialize"],
            order,
        )

    async def test_default_user_database_failure_is_not_swallowed(self):
        class FailingUser:
            username = _Field()

            @classmethod
            async def find_one(cls, *_args, **_kwargs):
                raise RuntimeError("user database unavailable")

        with (
            patch.object(initialization.settings, "DEFAULT_ADMIN_USER", "operator"),
            patch.object(
                initialization.settings,
                "DEFAULT_ADMIN_PASSWORD",
                "operator-password",
            ),
            patch.object(initialization, "hash_password", return_value="hashed"),
            patch.object(initialization, "User", FailingUser),
        ):
            with self.assertRaisesRegex(RuntimeError, "user database unavailable"):
                await initialization.InitializationService.initialize_default_user()

    async def test_default_admin_rotation_revokes_old_access_token_versions(self):
        _MemoryUser.records = [
            _MemoryUser(
                username="admin-a",
                password="hash-a",
                roles=["admin"],
                disabled=False,
                token_version=7,
            ),
            _MemoryUser(
                username="admin-b",
                password="hash-b",
                roles=["admin"],
                disabled=True,
                token_version=4,
            ),
        ]

        with (
            patch.object(initialization, "User", _MemoryUser),
            patch.object(initialization, "hash_password", return_value="unused"),
            patch.object(
                initialization.settings,
                "DEFAULT_ADMIN_PASSWORD",
                "operator-password",
            ),
        ):
            with patch.object(
                initialization.settings, "DEFAULT_ADMIN_USER", "admin-b"
            ):
                await initialization.InitializationService.initialize_default_user()
            with patch.object(
                initialization.settings, "DEFAULT_ADMIN_USER", "admin-a"
            ):
                await initialization.InitializationService.initialize_default_user()

        admin_a = next(
            user for user in _MemoryUser.records if user.username == "admin-a"
        )
        admin_b = next(
            user for user in _MemoryUser.records if user.username == "admin-b"
        )
        self.assertFalse(admin_a.disabled)
        self.assertTrue(admin_b.disabled)
        self.assertGreaterEqual(admin_a.token_version, 9)
        self.assertGreaterEqual(admin_b.token_version, 6)

    async def test_lifespan_does_not_continue_after_initialization_failure(self):
        _MemoryApplication.bulk_update_error = RuntimeError(
            "ownership repair failed"
        )
        with (
            patch.object(
                server_main.mongodb_manager,
                "init_beanie",
                new=AsyncMock(),
            ),
            patch.object(
                server_main,
                "run_pre_beanie_migrations",
                new=AsyncMock(),
            ),
            patch.object(server_main, "run_security_migrations", new=AsyncMock()),
            patch.object(server_main, "configure_logging", new=MagicMock()),
            patch.object(initialization, "Application", _MemoryApplication),
            patch.object(initialization, "Function", _MemoryFunction),
            patch.object(initialization.settings, "DEFAULT_ADMIN_USER", "operator"),
            patch.object(
                initialization.InitializationService,
                "_is_database_empty",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                initialization.InitializationService,
                "initialize_default_user",
                new=AsyncMock(),
            ),
            patch.object(
                initialization.InitializationService,
                "initialize_system_tasks",
                new=AsyncMock(),
            ),
            patch.object(
                server_main,
                "build_app_image_if_not_exists",
                new=AsyncMock(side_effect=AssertionError("startup continued")),
            ) as build_image,
        ):
            context = server_main.lifespan(SimpleNamespace())
            with self.assertRaisesRegex(RuntimeError, "ownership repair failed"):
                await context.__aenter__()

        build_image.assert_not_awaited()

    def test_compose_smoke_uses_a_non_default_admin_identity(self):
        source = (REPO_ROOT / ".github/compose-smoke.yml").read_text(
            encoding="utf-8"
        )
        match = re.search(
            r"(?m)^\s+DEFAULT_ADMIN_USER:\s*([^\s#]+)\s*$",
            source,
        )

        self.assertIsNotNone(match)
        self.assertEqual("operator", match.group(1))


if __name__ == "__main__":
    import unittest

    unittest.main()
