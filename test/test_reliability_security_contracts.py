import ast
import tomllib
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def parse(relative_path: str) -> ast.Module:
    return ast.parse(read(relative_path))


class AIIsolationContractTests(unittest.TestCase):
    def test_ai_route_uses_request_local_litellm_arguments(self):
        source = read("server/routers/ai.py")
        module = ast.parse(source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("litellm.proxy", source)

        completion_calls = [
            node
            for node in ast.walk(module)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "acompletion"
        ]
        self.assertEqual(len(completion_calls), 1)
        keywords = {keyword.arg for keyword in completion_calls[0].keywords}
        self.assertTrue({"api_key", "api_base", "proxy"} <= keywords)


class DynamicCORSContractTests(unittest.TestCase):
    def test_control_plane_wildcard_cors_disables_credentials(self):
        source = read("server/main.py")
        self.assertIn('allow_origins=["*"]', source)
        self.assertIn("allow_credentials=False", source)
        self.assertNotIn("allow_credentials=True", source)

    def test_runtime_uses_dynamic_cors_middleware(self):
        self.assertTrue((REPO_ROOT / "app/core/dynamic_cors.py").is_file())
        main_source = read("app/main.py")
        self.assertIn("DynamicCORSMiddleware", main_source)
        self.assertNotIn("app.add_middleware(\n    CORSMiddleware", main_source)

    def test_cors_model_rejects_wildcard_credentials(self):
        source = read("server/models/applications_model.py")
        cors_class = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ClassDef) and node.name == "CORSConfig"
        )
        methods = {
            node.name
            for node in cors_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("validate_policy", methods)


class TaskRecoveryContractTests(unittest.TestCase):
    def test_dependency_restart_calls_are_awaited(self):
        module = parse("server/routers/settings.py")
        restart_calls = [
            node
            for node in ast.walk(module)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "restart_container"
        ]
        awaited_calls = {
            id(node.value)
            for node in ast.walk(module)
            if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
        }
        self.assertTrue(restart_calls)
        self.assertTrue(all(id(call) in awaited_calls for call in restart_calls))

    def test_task_model_contains_lease_and_retry_fields(self):
        source = read("server/models/tasks_model.py")
        task_class = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ClassDef) and node.name == "Task"
        )
        fields = {
            node.target.id
            for node in task_class.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        self.assertTrue(
            {
                "app_id",
                "attempts",
                "lease_owner",
                "lease_expires_at",
                "next_attempt_at",
                "last_error",
            }
            <= fields
        )

    def test_worker_atomically_claims_and_reconnects(self):
        source = read("server/core/task_worker.py")
        self.assertIn("find_one_and_update", source)
        self.assertIn("lease_expires_at", source)
        self.assertIn("while True", source)
        self.assertIn("MAX_TASK_ATTEMPTS", source)


class DeploymentAssetContractTests(unittest.TestCase):
    def test_container_builds_use_pinned_uv_installation(self):
        for relative_path in ("server/Dockerfile", "app/Dockerfile"):
            source = read(relative_path)
            self.assertIn("pip install --no-cache-dir uv==0.8.2", source)
            self.assertNotIn("astral.sh/uv", source)
            self.assertNotIn("pip install uv\n", source)

    def test_application_collection_defaults_use_callable_factories(self):
        for relative_path in (
            "server/models/applications_model.py",
            "app/models/applications_model.py",
        ):
            source = read(relative_path)
            self.assertNotIn("default_factory=[]", source, relative_path)
            self.assertGreaterEqual(source.count("default_factory=list"), 5)

    def test_dev_mount_path_rejects_root_and_relative_paths(self):
        config = read("server/core/config.py")
        self.assertIn("validate_dev_mount_path", config)
        self.assertIn("path.is_absolute()", config)
        self.assertIn("path == Path(path.anchor)", config)

    def test_failed_runtime_start_revokes_issued_token(self):
        source = read("server/core/docker_manager.py")
        self.assertIn("_revoke_runtime_token", source)
        self.assertGreaterEqual(source.count("await _revoke_runtime_token(app)"), 4)

    def test_example_environment_contains_no_deployable_secrets_or_root_mount(self):
        env_example = read(".env.example")
        for forbidden in (
            'MONGODB_PASSWORD="hyacpassword"',
            'S3_SECRET_KEY="rustfssecret"',
            'DEFAULT_ADMIN_PASSWORD="admin123"',
            'APP_CODE_PATH_ON_HOST="/"',
        ):
            self.assertNotIn(forbidden, env_example)

    def test_production_compose_only_publishes_web_ports(self):
        source = read("docker-compose.yml")
        compose = yaml.safe_load(source)
        published = {
            service_name: service.get("ports", [])
            for service_name, service in compose["services"].items()
            if service.get("ports")
        }

        self.assertEqual(published, {"traefik": ["80:80", "443:443"]})
        self.assertNotIn("--api.insecure=true", source)
        server_environment = compose["services"]["server"]["environment"]
        self.assertIn("DEFAULT_ADMIN_USER", server_environment)
        self.assertIn("DEFAULT_ADMIN_PASSWORD", server_environment)

    def test_mongo_keyfile_is_generated_and_existing_permissions_are_repaired(self):
        self.assertFalse((REPO_ROOT / "mongo-keyfile").exists())
        self.assertIn("/mongo-keyfile", read(".gitignore"))
        script = read("scripts/01-create-mongo-keyfile.sh")
        self.assertIn("repair_existing_keyfile", script)


class ToolchainContractTests(unittest.TestCase):
    def test_python_projects_declare_runtime_and_test_dependencies(self):
        for relative_path in ("server/pyproject.toml", "app/pyproject.toml"):
            data = tomllib.loads(read(relative_path))
            self.assertTrue(data["project"]["dependencies"], relative_path)
            self.assertTrue(data.get("dependency-groups", {}).get("dev"), relative_path)

    def test_ci_runs_python_frontend_and_compose_gates(self):
        workflow = read(".github/workflows/ci.yml")
        self.assertIn("unittest discover", workflow)
        self.assertIn("uv sync --project server --frozen", workflow)
        self.assertIn("uv sync --project app --frozen", workflow)
        self.assertIn("app/.venv/bin/pytest", workflow)
        self.assertIn("typecheck", workflow)
        self.assertIn("eslint", workflow)
        self.assertIn("docker compose", workflow)


if __name__ == "__main__":
    unittest.main()
