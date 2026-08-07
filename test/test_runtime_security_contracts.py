import ast
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def parse(relative_path: str) -> ast.Module:
    return ast.parse(read(relative_path))


def async_function(module: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(module):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"async function {name!r} not found")


class RuntimeCredentialContractTests(unittest.TestCase):
    def test_runtime_environment_contains_no_platform_credentials(self):
        module = parse("server/core/docker_manager.py")
        start = async_function(module, "start_app_container")
        environment_keys = set()
        for node in ast.walk(start):
            if not isinstance(node, ast.Assign):
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == "environment"
                for target in node.targets
            ):
                continue
            if isinstance(node.value, ast.Dict):
                environment_keys = {
                    key.value
                    for key in node.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
                break

        self.assertTrue({"APP_ID", "RUNTIME_TOKEN", "CONTROL_PLANE_URL"} <= environment_keys)
        self.assertTrue(
            {"MONGODB_USERNAME", "MONGODB_PASSWORD", "SECRET_KEY"}.isdisjoint(
                environment_keys
            )
        )

    def test_runtime_control_router_exists_and_is_not_publicly_routed(self):
        self.assertTrue((REPO_ROOT / "server/routers/runtime_control.py").is_file())
        compose = read("docker-compose.yml")
        self.assertIn("!PathPrefix(`/internal`)", compose)


class FunctionAuthorizationContractTests(unittest.TestCase):
    def test_function_limits_are_validated_on_control_and_runtime_models(self):
        for relative_path in (
            "server/models/functions_model.py",
            "app/models/functions_model.py",
        ):
            source = read(relative_path)
            self.assertIn("memory_limit: int = Field(default=128, ge=128, le=4096)", source)
            self.assertIn("timeout: int = Field(default=5, ge=1, le=300)", source)

    def test_new_functions_are_public_by_default_on_control_and_runtime_models(self):
        for relative_path in (
            "server/models/functions_model.py",
            "app/models/functions_model.py",
        ):
            source = read(relative_path)
            self.assertIn("requires_auth: bool = False", source)

    def test_dynamic_handler_authorizes_before_execution(self):
        module = parse("app/router.py")
        handler = async_function(module, "dynamic_handler")
        authorize_line = None
        execute_line = None
        for node in ast.walk(handler):
            if not isinstance(node, ast.Call):
                continue
            name = None
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            elif isinstance(node.func, ast.Name):
                name = node.func.id
            if name == "authorize_function":
                authorize_line = node.lineno
            elif name == "_execute_and_log":
                execute_line = node.lineno

        self.assertIsNotNone(authorize_line)
        self.assertIsNotNone(execute_line)
        self.assertLess(authorize_line, execute_line)

    def test_function_url_uses_stable_function_id(self):
        module = parse("server/routers/functions.py")
        node = async_function(module, "function_url")
        source = ast.unparse(node)
        self.assertIn("Function.function_id == data.id", source)
        self.assertIn("func_result.function_id", source)
        self.assertNotIn("ObjectId(data.id)", source)


class DockerHardeningContractTests(unittest.TestCase):
    def test_database_clients_are_created_after_invocation_fork(self):
        router_source = read("app/router.py")
        executor_source = read("app/core/function_executor.py")
        self.assertNotIn("Depends(get_dynamic_clients)", router_source)
        self.assertIn("_refresh_child_context", executor_source)
        self.assertIn("AsyncMongoClient", executor_source)

    def test_runtime_create_call_sets_all_mandatory_limits(self):
        module = parse("server/core/docker_manager.py")
        start = async_function(module, "start_app_container")
        call_keywords = set()
        for node in ast.walk(start):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == "create_container":
                call_keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
                break

        self.assertTrue(
            {
                "mem_limit",
                "nano_cpus",
                "pids_limit",
                "read_only",
                "tmpfs",
                "cap_drop",
                "security_opt",
                "user",
            }
            <= call_keywords
        )

    def test_runtime_image_declares_non_root_user(self):
        dockerfile = read("app/Dockerfile")
        self.assertIn("USER hyac", dockerfile)


class RuntimePackagingContractTests(unittest.TestCase):
    def test_dynamic_dependencies_use_the_runtime_dependency_mount(self):
        loader = read("app/core/dependency_loader.py")
        dockerfile = read("app/Dockerfile")

        self.assertIn('DEPENDENCY_PATH = "/dependencies/python"', loader)
        self.assertNotIn("/tmp/hyac-dependencies", loader)
        self.assertIn("PYTHONPATH=/dependencies/python", dockerfile)
        self.assertIn("UV_CACHE_DIR=/tmp/uv-cache", dockerfile)

    def test_dependency_install_failures_escape_the_startup_helper(self):
        module = parse("app/core/dependency_loader.py")
        helper = async_function(module, "install_app_dependencies")

        swallowing_handlers = [
            handler
            for handler in ast.walk(helper)
            if isinstance(handler, ast.ExceptHandler)
            and not any(isinstance(node, ast.Raise) for node in ast.walk(handler))
        ]
        self.assertEqual([], swallowing_handlers)


class DeploymentAssetContractTests(unittest.TestCase):
    def test_dev_traefik_entrypoints_are_loopback_only(self):
        compose = read("docker-compose.dev.yml")
        self.assertIn('"127.0.0.1:80:80"', compose)
        self.assertIn('"127.0.0.1:443:443"', compose)
        self.assertNotIn('- "80:80"', compose)
        self.assertNotIn('- "443:443"', compose)

    def test_keyfile_script_rejects_an_unusable_owner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            keyfile = directory / "mongo-keyfile"
            keyfile.write_text("test-key", encoding="utf-8")
            fake_bin = directory / "bin"
            fake_bin.mkdir()
            fake_id = fake_bin / "id"
            fake_id.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"-u\" ]; then echo 12345; else exec /usr/bin/id \"$@\"; fi\n",
                encoding="utf-8",
            )
            fake_id.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "KEYFILE": str(keyfile),
                "MONGO_UID": "999",
                "MONGO_GID": "999",
            }

            result = subprocess.run(
                [str(REPO_ROOT / "scripts/01-create-mongo-keyfile.sh")],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("keyfile owner", result.stderr)

    def test_production_images_are_kept_out_of_basic_ci(self):
        workflow = read(".github/workflows/ci.yml")
        basic_ci = workflow.split("\n  release-gate:", 1)[0]
        self.assertNotIn("docker build", basic_ci)
        self.assertNotIn("docker run", basic_ci)
        self.assertNotIn("hyac-server-ci", basic_ci)
        self.assertNotIn("hyac-app-ci", basic_ci)
        self.assertIn("compileall", basic_ci)
        self.assertIn("if: startsWith(github.ref, 'refs/tags/')", workflow)

        for service in ("server", "app"):
            with self.subTest(service=service):
                self.assertIn("AS production", read(f"{service}/Dockerfile"))
        self.assertIn("FROM nginx:alpine", read("web/Dockerfile"))

    def test_production_guides_require_keyfile_and_all_mandatory_secrets(self):
        mandatory = {
            "DOMAIN_NAME",
            "EMAIL_ADDRESS",
            "MONGODB_USERNAME",
            "MONGODB_PASSWORD",
            "S3_ACCESS_KEY",
            "S3_SECRET_KEY",
            "SECRET_KEY",
            "DEFAULT_ADMIN_USER",
            "DEFAULT_ADMIN_PASSWORD",
        }
        for relative_path in (
            "README.md",
            "README.en.md",
            "docs/docs/en/getting-started/deployment.md",
            "docs/docs/zh/getting-started/deployment.md",
        ):
            with self.subTest(path=relative_path):
                guide = read(relative_path)
                start_position = guide.find("docker compose up -d")
                if start_position < 0:
                    start_position = guide.find("docker-compose up -d")
                self.assertGreaterEqual(start_position, 0)
                prerequisites = guide[:start_position]
                self.assertIn("./scripts/01-create-mongo-keyfile.sh", prerequisites)
                for variable in mandatory:
                    self.assertIn(variable, prerequisites)


if __name__ == "__main__":
    unittest.main()
