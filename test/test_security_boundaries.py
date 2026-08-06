import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = REPO_ROOT / "server"
sys.path.insert(0, str(SERVER_ROOT))


def parse_server_file(relative_path: str) -> ast.Module:
    source = (SERVER_ROOT / relative_path).read_text(encoding="utf-8")
    return ast.parse(source)


def function_node(module: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in module.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"async function {name!r} not found")


class TokenClaimsTests(unittest.TestCase):
    def test_refresh_token_cannot_be_used_as_access_token(self):
        from core.token_claims import TokenClaimsError, validate_token_claims

        payload = {"sub": "admin", "type": "refresh", "token_version": 0}

        with self.assertRaises(TokenClaimsError):
            validate_token_claims(payload, expected_type="access", token_version=0)

    def test_token_version_must_match_current_user(self):
        from core.token_claims import TokenClaimsError, validate_token_claims

        payload = {"sub": "admin", "type": "access", "token_version": 2}

        with self.assertRaises(TokenClaimsError):
            validate_token_claims(payload, expected_type="access", token_version=3)

    def test_valid_access_claims_return_subject(self):
        from core.token_claims import validate_token_claims

        payload = {"sub": "admin", "type": "access", "token_version": 3}

        self.assertEqual(
            validate_token_claims(payload, expected_type="access", token_version=3),
            "admin",
        )


class UserSurfaceTests(unittest.TestCase):
    def test_public_router_does_not_register_user_management_endpoints(self):
        module = parse_server_file("routers/users.py")
        registered_paths = set()
        for node in module.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                if (
                    isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "router"
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    registered_paths.add(decorator.args[0].value)

        self.assertTrue(
            {"/login", "/captcha", "/info", "/me", "/refreshToken"}
            <= registered_paths
        )
        self.assertTrue(
            {"/add", "/delete/{username}", "/get/{username}", "/list"}.isdisjoint(
                registered_paths
            )
        )

    def test_public_user_model_excludes_credentials(self):
        module = parse_server_file("models/users_model.py")
        user_public = next(
            (
                node
                for node in module.body
                if isinstance(node, ast.ClassDef) and node.name == "UserPublic"
            ),
            None,
        )
        self.assertIsNotNone(user_public, "UserPublic response model is required")
        fields = {
            node.target.id
            for node in user_public.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
        }
        self.assertTrue({"username", "roles", "disabled"} <= fields)
        self.assertTrue(
            {"password", "refresh_token", "refresh_token_hash"}.isdisjoint(fields)
        )


class AccessControlTests(unittest.TestCase):
    def test_every_template_operation_enforces_application_membership(self):
        module = parse_server_file("routers/function_templates.py")
        handler_names = {
            "get_function_templates",
            "create_function_template",
            "delete_function_template",
            "update_function_template",
            "get_function_template",
        }

        for handler_name in handler_names:
            node = function_node(module, handler_name)
            calls = {
                call.func.id
                for call in ast.walk(node)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            }
            self.assertIn(
                "require_app_member",
                calls,
                f"{handler_name} must enforce application membership",
            )

    def test_package_add_checks_membership_before_container_lookup(self):
        module = parse_server_file("routers/settings.py")
        node = function_node(module, "package_add")
        membership_guard_line = None
        dependency_lookup_line = None

        for child in ast.walk(node):
            if isinstance(child, ast.If) and isinstance(child.test, ast.UnaryOp):
                if isinstance(child.test.op, ast.Not) and isinstance(
                    child.test.operand, ast.Name
                ):
                    if child.test.operand.id == "app":
                        membership_guard_line = child.lineno
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                if child.func.id == "get_app_system_dependencies":
                    dependency_lookup_line = child.lineno

        self.assertIsNotNone(membership_guard_line)
        self.assertIsNotNone(dependency_lookup_line)
        self.assertLess(membership_guard_line, dependency_lookup_line)


class CredentialRedactionBehaviorTests(unittest.IsolatedAsyncioTestCase):
    def test_application_responses_strip_internal_credentials(self):
        from routers import applications as applications_router

        credential_sentinel = object()

        class SerializableApplication:
            def model_dump(self, **_kwargs):
                return {
                    "app_id": "safe-app-id",
                    "app_name": "safe-app-name",
                    "db_password": credential_sentinel,
                    "runtime_token_hash": credential_sentinel,
                    "ai_config": {
                        "provider": "safe-provider",
                        "api_key": credential_sentinel,
                    },
                    "notification": {
                        "email": {
                            "sender": "safe@example.invalid",
                            "password": credential_sentinel,
                        }
                    },
                }

        serialized = applications_router.serialize_application(
            SerializableApplication()
        )

        self.assertNotIn("db_password", serialized)
        self.assertNotIn("runtime_token_hash", serialized)
        self.assertNotIn("api_key", serialized["ai_config"])
        self.assertNotIn("password", serialized["notification"]["email"])
        self.assertEqual(serialized["app_id"], "safe-app-id")
        self.assertEqual(serialized["ai_config"]["provider"], "safe-provider")
        self.assertEqual(
            serialized["notification"]["email"]["sender"],
            "safe@example.invalid",
        )

    async def test_environment_response_redacts_runtime_credentials(self):
        from routers import settings as settings_router

        credential_sentinel = "credential-sentinel-must-not-leak"
        sensitive_values = {
            "APP_DB_PASSWORD": f"{credential_sentinel}-db",
            "RUNTIME_TOKEN": f"{credential_sentinel}-runtime",
            "MONGODB_PASSWORD": f"{credential_sentinel}-mongo",
            "S3_ACCESS_KEY": f"{credential_sentinel}-access",
            "S3_SECRET_KEY": f"{credential_sentinel}-secret",
            "SECRET_KEY": f"{credential_sentinel}-jwt",
        }
        startup_envs = [
            *(f"{key}={value}" for key, value in sensitive_values.items()),
            "APP_DB_USERNAME=safe-runtime-user",
            "RUNTIME_GENERATION=17",
            "CONTROL_PLANE_URL=http://control-plane.invalid",
        ]
        app = SimpleNamespace(app_id="APP-REDaction", environment_variables=[])

        class QueryField:
            def __eq__(self, other):
                return other

        class FakeApplication:
            app_id = QueryField()
            users = QueryField()

            @staticmethod
            async def find_one(*_conditions):
                return app

        container = SimpleNamespace(attrs={"Config": {"Env": startup_envs}})
        fake_docker_manager = SimpleNamespace(
            client=SimpleNamespace(
                containers=SimpleNamespace(get=lambda _name: container)
            )
        )

        with (
            patch.object(settings_router, "Application", FakeApplication),
            patch.object(
                settings_router, "docker_manager", fake_docker_manager
            ),
        ):
            response = await settings_router.envs_data(
                settings_router.AppDependenciesRequest(appId=app.app_id),
                SimpleNamespace(username="admin"),
            )

        system_envs = {
            item["key"]: item["value"] for item in response.data["system"]
        }
        for key in sensitive_values:
            self.assertEqual(system_envs[key], "<redacted>")
            self.assertNotIn(credential_sentinel, system_envs[key])
        self.assertEqual(system_envs["APP_DB_USERNAME"], "safe-runtime-user")
        self.assertEqual(system_envs["RUNTIME_GENERATION"], "17")
        self.assertEqual(
            system_envs["CONTROL_PLANE_URL"],
            "http://control-plane.invalid",
        )


if __name__ == "__main__":
    unittest.main()
