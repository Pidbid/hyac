import json
import os
import re
import runpy
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


class DeploymentReviewContractTests(unittest.TestCase):
    def test_app_uses_one_authoritative_dependency_source_for_lsp_commands(self):
        runtime_requirements_path = (
            REPO_ROOT / "app/lsp_sidecar/runtime_requirements.py"
        )
        self.assertTrue(runtime_requirements_path.is_file())
        runtime_requirements = runpy.run_path(str(runtime_requirements_path))
        command_packages = runtime_requirements["PYTHON_COMMAND_PACKAGES"]

        project = tomllib.loads(read("app/pyproject.toml"))
        declared_packages = {
            re.split(r"[<>=!~ ]", dependency, maxsplit=1)[0]
            for dependency in project["project"]["dependencies"]
        }

        self.assertEqual(
            {"pyright-langserver": "pyright", "autopep8": "autopep8"},
            command_packages,
        )
        self.assertLessEqual(set(command_packages.values()), declared_packages)
        self.assertFalse((REPO_ROOT / "app/requirements.txt").exists())
        self.assertNotIn("app/requirements.txt", read("app/lsp_sidecar/lsp_process.py"))

    def test_dev_compose_exposes_dashboard_without_a_dedicated_host_port(self):
        compose = yaml.safe_load(read("docker-compose.dev.yml"))
        services = compose["services"]
        traefik = services["traefik"]

        self.assertEqual("traefik:v3.7", traefik["image"])
        self.assertEqual("mongo:8.2", services["mongodb"]["image"])
        self.assertEqual(
            {"127.0.0.1:80:80", "127.0.0.1:443:443"},
            set(traefik["ports"]),
        )
        self.assertNotIn("--api.insecure=true", traefik["command"])
        self.assertIn("--ping=true", traefik["command"])
        self.assertIn("healthcheck", traefik)
        self.assertIn(
            "traefik.http.routers.hyac-dashboard.service=api@internal",
            traefik["labels"],
        )

        lsp_sidecar = services["lsp-sidecar"]
        self.assertIn("healthcheck", lsp_sidecar)
        self.assertEqual(
            "service_healthy",
            services["web"]["depends_on"]["lsp-sidecar"]["condition"],
        )

    def test_dev_start_script_preflights_and_waits_for_healthy_services(self):
        script_path = REPO_ROOT / "scripts/dev-up.sh"
        self.assertTrue(script_path.is_file())
        self.assertTrue(os.access(script_path, os.X_OK))
        script = script_path.read_text(encoding="utf-8")

        for required_contract in (
            "--check",
            "mkcert -CAROOT",
            "openssl verify",
            "*.hyac.localhost",
            "config --environment",
            "APP_CODE_PATH_ON_HOST",
            "--wait",
            "--wait-timeout",
            "Development endpoint did not become ready",
            "https://console.hyac.localhost/",
            "https://server.hyac.localhost/docs",
            "https://traefik.localhost/api/overview",
            "http://127.0.0.1:9002/health",
            "--noproxy",
        ):
            with self.subTest(contract=required_contract):
                self.assertIn(required_contract, script)
        self.assertNotIn("curl -k", script)
        self.assertNotIn("down -v", script)

    def test_web_preserves_multilabel_localhost_base_domain(self):
        common = read("web/src/utils/common.ts")
        self.assertIn("host === 'server.localhost'", common)
        self.assertNotIn("host.endsWith('.localhost')", common)

    def test_developer_guides_use_the_preflighted_start_command(self):
        for relative_path in (
            "README.md",
            "README.en.md",
            "docs/docs/en/development/developer-deployment.md",
            "docs/docs/zh/development/developer-deployment.md",
        ):
            with self.subTest(path=relative_path):
                guide = read(relative_path)
                self.assertIn("./scripts/dev-up.sh", guide)
                self.assertIn("https://traefik.localhost", guide)

    def test_github_actions_only_runs_basic_fast_jobs(self):
        workflow_source = read(".github/workflows/ci.yml")
        workflow = yaml.safe_load(workflow_source)

        self.assertEqual(set(workflow["jobs"]), {"python", "frontend", "compose"})
        allowed_docker_commands = {
            "docker compose config --quiet",
            "docker compose -f docker-compose.dev.yml --env-file .env.example config --quiet",
        }
        browser_markers = (
            "playwright",
            "chromium",
            "chrome",
            "production-smoke-function-lifecycle.mjs",
        )
        container_tool_markers = ("buildah", "nerdctl", "podman")
        container_action_markers = ("docker", *container_tool_markers)

        for job_name, job in workflow["jobs"].items():
            with self.subTest(job=job_name, boundary="job-container"):
                self.assertNotIn("container", job)
                self.assertNotIn("services", job)

            for step_index, step in enumerate(job.get("steps", [])):
                run_command = step.get("run", "")
                uses_action = step.get("uses", "")
                step_source = f"{run_command}\n{uses_action}".lower()
                for marker in browser_markers:
                    with self.subTest(
                        job=job_name,
                        step=step_index,
                        boundary="browser",
                        marker=marker,
                    ):
                        self.assertNotIn(marker, step_source)

                normalized_run = " ".join(run_command.split())
                if re.search(r"\bdocker\b", normalized_run, re.IGNORECASE):
                    with self.subTest(
                        job=job_name,
                        step=step_index,
                        boundary="docker-command",
                    ):
                        self.assertIn(normalized_run, allowed_docker_commands)
                for marker in container_tool_markers:
                    with self.subTest(
                        job=job_name,
                        step=step_index,
                        boundary="container-command",
                        marker=marker,
                    ):
                        self.assertNotIn(marker, normalized_run.lower())

                normalized_action = uses_action.lower()
                for marker in container_action_markers:
                    with self.subTest(
                        job=job_name,
                        step=step_index,
                        boundary="container-action",
                        marker=marker,
                    ):
                        self.assertNotIn(marker, normalized_action)

    def test_production_compose_resolves_one_non_latest_runtime_image_tag(self):
        release_tag = "release-2026-08-05"
        environment = {
            **os.environ,
            "DOMAIN_NAME": "example.com",
            "EMAIL_ADDRESS": "ops@example.com",
            "MONGODB_USERNAME": "root",
            "MONGODB_PASSWORD": "mongo-production-password",
            "S3_ACCESS_KEY": "production-access-key",
            "S3_SECRET_KEY": "production-secret-key",
            "SECRET_KEY": "production-secret-key-with-at-least-32-characters",
            "DEFAULT_ADMIN_USER": "admin",
            "DEFAULT_ADMIN_PASSWORD": "production-admin-password",
            "APP_IMAGE_TAG": release_tag,
            "DEMO_MODE": "false",
        }
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(REPO_ROOT / "docker-compose.yml"),
                "config",
                "--format",
                "json",
            ],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        compose = json.loads(result.stdout)
        server_tag = compose["services"]["server"]["environment"]["APP_IMAGE_TAG"]
        app_image = compose["services"]["app"]["image"]
        self.assertEqual(server_tag, release_tag)
        self.assertEqual(app_image, f"wicos/hyac_app:{server_tag}")
        self.assertNotEqual(server_tag, "latest")

    def test_mongo_keyfile_generator_refuses_symlinks_without_touching_target(self):
        script = REPO_ROOT / "scripts/01-create-mongo-keyfile.sh"

        for force_regen in ("0", "1"):
            with self.subTest(force_regen=force_regen), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                target = directory / "sentinel"
                target.write_text("do-not-touch", encoding="utf-8")
                target.chmod(0o640)
                keyfile = directory / "mongo-keyfile"
                keyfile.symlink_to(target)

                result = subprocess.run(
                    [str(script)],
                    cwd=directory,
                    env={
                        **os.environ,
                        "KEYFILE": str(keyfile),
                        "FORCE_REGEN": force_regen,
                        "MONGO_UID": str(os.getuid()),
                        "MONGO_GID": str(os.getgid()),
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(keyfile.is_symlink())
                self.assertEqual(target.read_text(encoding="utf-8"), "do-not-touch")
                self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_example_secrets_are_empty_and_compose_ci_injects_test_values(self):
        example = read(".env.example")
        values = {}
        for line in example.splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"').strip("'")

        for key in (
            "DOMAIN_NAME",
            "EMAIL_ADDRESS",
            "MONGODB_PASSWORD",
            "S3_ACCESS_KEY",
            "S3_SECRET_KEY",
            "SECRET_KEY",
            "DEFAULT_ADMIN_PASSWORD",
        ):
            with self.subTest(key=key):
                self.assertEqual(values[key], "")

        workflow = read(".github/workflows/ci.yml")
        compose_job = workflow.split("  compose:\n", 1)[1]
        for key in (
            "DOMAIN_NAME",
            "EMAIL_ADDRESS",
            "MONGODB_PASSWORD",
            "S3_ACCESS_KEY",
            "S3_SECRET_KEY",
            "SECRET_KEY",
            "DEFAULT_ADMIN_PASSWORD",
        ):
            with self.subTest(ci_key=key):
                self.assertRegex(compose_job, rf"(?m)^      {key}: .+")

    def test_production_images_install_from_the_same_frozen_locks_as_ci(self):
        for service in ("server", "app"):
            with self.subTest(service=service):
                dockerfile = read(f"{service}/Dockerfile")
                self.assertIn("COPY pyproject.toml uv.lock ./", dockerfile)
                self.assertIn("uv export --frozen --no-dev", dockerfile)
                self.assertNotIn("COPY requirements.txt", dockerfile)
                self.assertNotIn("-r requirements.txt", dockerfile)

        server_entrypoint = read("server/start.sh")
        self.assertNotIn("uv pip install", server_entrypoint)
        self.assertNotIn("--reload", server_entrypoint)
        self.assertIn("exec uvicorn", server_entrypoint)

    def test_frontend_ci_runs_the_password_contract(self):
        workflow = read(".github/workflows/ci.yml")
        frontend_job = workflow.split("  frontend:\n", 1)[1].split(
            "\n  compose:\n", 1
        )[0]

        self.assertIn("pnpm test:password-contract", frontend_job)

    def test_local_production_smoke_assets_use_real_tls_with_the_test_certificate(self):
        smoke_source = read(".github/compose-smoke.yml")
        browser_smoke = read("web/tests/production-smoke-function-lifecycle.mjs")
        self.assertIn('RUNTIME_INGRESS_TLS: "true"', smoke_source)
        self.assertIn("traefik.http.routers.hyac-ci-server.tls=true", smoke_source)
        self.assertIn("traefik.http.routers.hyac-ci-web.tls=true", smoke_source)
        self.assertIn("CI_SMOKE_DYNAMIC_DIR", smoke_source)
        self.assertIn("https://server.ci.example.com:18443", smoke_source)
        self.assertIn("ignoreHTTPSErrors: true", browser_smoke)

    def test_local_production_smoke_uses_disposable_dependencies(self):
        smoke_compose = REPO_ROOT / ".github/compose-smoke.yml"

        self.assertTrue(smoke_compose.is_file())
        smoke_source = smoke_compose.read_text(encoding="utf-8") if smoke_compose.exists() else ""
        self.assertIn("image: hyac-server-ci", smoke_source)
        self.assertIn("image: hyac-web-ci", smoke_source)
        self.assertIn("/var/run/docker.sock:/var/run/docker.sock", smoke_source)

    def test_local_smoke_uses_production_config_and_authenticated_replica_set(self):
        smoke_source = read(".github/compose-smoke.yml")

        self.assertIn('DEV_MODE: "false"', smoke_source)
        self.assertIn("APP_IMAGE_TAG: ${CI_SMOKE_APP_IMAGE_TAG", smoke_source)
        self.assertIn("image: wicos/hyac_app:${CI_SMOKE_APP_IMAGE_TAG", smoke_source)
        self.assertNotIn("APP_IMAGE_TAG: ci-smoke", smoke_source)
        self.assertIn("MONGO_INITDB_ROOT_USERNAME", smoke_source)
        self.assertIn("MONGO_INITDB_ROOT_PASSWORD", smoke_source)
        self.assertIn("--keyFile", smoke_source)
        self.assertIn("--auth", smoke_source)
        self.assertIn('-u "$$MONGO_INITDB_ROOT_USERNAME"', smoke_source)
        self.assertIn('-p "$$MONGO_INITDB_ROOT_PASSWORD"', smoke_source)
        self.assertNotIn("-u '$${MONGO_INITDB_ROOT_USERNAME}'", smoke_source)
        self.assertIn("--authenticationDatabase admin", smoke_source)
        self.assertIn("rs.initiate", smoke_source)
        self.assertIn("service_completed_successfully", smoke_source)
        self.assertNotIn('MONGODB_USERNAME: ""', smoke_source)
        self.assertNotIn('MONGODB_PASSWORD: ""', smoke_source)

    def test_local_smoke_routes_public_surfaces_through_real_traefik_labels(self):
        smoke_source = read(".github/compose-smoke.yml")
        docker_manager = read("server/core/docker_manager.py")

        self.assertIn("image: traefik:v3.6.1", smoke_source)
        self.assertIn('image: "traefik:v3.6.1"', read("docker-compose.yml"))
        self.assertNotIn("traefik:v3.5.0", smoke_source)
        self.assertIn('"--entrypoints.ci.address=:8443"', smoke_source)
        self.assertIn('"--entrypoints.traefik.address=:8080"', smoke_source)
        self.assertIn('"--ping.entrypoint=traefik"', smoke_source)
        self.assertIn('"127.0.0.1:18443:8443"', smoke_source)
        self.assertIn(
            'command: ["python", "-c", "import time; time.sleep(3600)"]',
            smoke_source,
        )
        self.assertIn("CI_SMOKE_MODE: \"true\"", smoke_source)
        self.assertIn("RUNTIME_INGRESS_ENTRYPOINT: ci", smoke_source)
        self.assertIn('RUNTIME_INGRESS_TLS: "true"', smoke_source)
        self.assertIn(
            'traefik.http.routers.hyac-ci-server.rule=Host(`server.ci.example.com`)',
            smoke_source,
        )
        self.assertIn(
            'traefik.http.routers.hyac-ci-web.rule=Host(`console.ci.example.com`)',
            smoke_source,
        )
        self.assertNotIn('"127.0.0.1:18000:8000"', smoke_source)
        self.assertNotIn('"127.0.0.1:18080:80"', smoke_source)

        self.assertIn("settings.RUNTIME_INGRESS_ENTRYPOINT", docker_manager)
        self.assertIn("settings.RUNTIME_INGRESS_TLS", docker_manager)

    def test_local_browser_smoke_logs_in_through_the_real_chrome_form(self):
        browser_smoke = read("web/tests/production-smoke-function-lifecycle.mjs")
        self.assertIn("channel: 'chrome'", browser_smoke)
        self.assertIn("--no-proxy-server", browser_smoke)
        self.assertIn("waitUntil: 'domcontentloaded'", browser_smoke)
        self.assertNotIn("waitUntil: 'networkidle'", browser_smoke)
        self.assertIn("page.waitForResponse", browser_smoke)
        self.assertIn("page.locator", browser_smoke)

    def test_local_browser_smoke_exercises_full_function_lifecycle(self):
        browser_smoke = read("web/tests/production-smoke-function-lifecycle.mjs")

        self.assertIn("channel: 'chrome'", browser_smoke)
        self.assertIn("--ignore-certificate-errors", browser_smoke)
        self.assertIn("/function/create", browser_smoke)
        self.assertIn("/function/update_code", browser_smoke)
        self.assertIn("/function/proxy_test", browser_smoke)
        self.assertIn("/function/delete", browser_smoke)
        self.assertIn(".add-btn", browser_smoke)
        self.assertIn(".monaco-editor textarea", browser_smoke)
        self.assertIn(".send-btn", browser_smoke)
        self.assertIn(".delete-btn", browser_smoke)
        self.assertIn("Authorization", browser_smoke)
        self.assertIn("Bearer ${accessToken}", browser_smoke)
        self.assertIn("finally", browser_smoke)

    def test_local_browser_smoke_exercises_storage_and_database_lifecycles(self):
        smoke_source = read(".github/compose-smoke.yml")
        browser_smoke = read(
            "web/tests/production-smoke-function-lifecycle.mjs"
        )
        json_editor = read("web/src/components/custom/jsonEditor.vue")

        self.assertIn(
            "S3_EXTERNAL_ENDPOINT: oss.ci.example.com:18443", smoke_source
        )
        self.assertIn('S3_SECURE_EXTERNAL: "true"', smoke_source)
        self.assertIn(
            "traefik.http.routers.hyac-ci-rustfs.tls=true", smoke_source
        )
        self.assertIn("MAP oss.ci.example.com 127.0.0.1", browser_smoke)
        for endpoint in (
            "/storage/upload_file",
            "/storage/get_download_url",
            "/storage/delete_file",
            "/database/create_collection",
            "/database/insert_document",
            "/database/update_document",
            "/database/delete_document",
            "/database/delete_collection",
        ):
            self.assertIn(endpoint, browser_smoke)
        for interaction in (
            "waitForEvent('filechooser')",
            ".storage-actions",
            ".collection-panel",
            ".document-table",
            ".operation-panel",
        ):
            self.assertIn(interaction, browser_smoke)
        self.assertIn("experimentalEditContextEnabled: false", json_editor)

    def test_deployment_guides_explain_generated_admin_password_length(self):
        for relative_path in (
            "README.md",
            "README.en.md",
            "docs/docs/en/getting-started/deployment.md",
            "docs/docs/zh/getting-started/deployment.md",
        ):
            with self.subTest(path=relative_path):
                guide = read(relative_path)
                command_position = guide.index("openssl rand -hex 32")
                explanation = guide[command_position : command_position + 320]
                self.assertIn("64", explanation)
                self.assertIn("APP_IMAGE_TAG", guide[: guide.index("docker compose up -d")])

    def test_user_settings_do_not_publish_a_default_password(self):
        for relative_path, first_start_phrase in (
            ("docs/docs/en/user-guide/user-settings.md", "before the first startup"),
            ("docs/docs/zh/user-guide/user-settings.md", "首次启动前"),
        ):
            with self.subTest(path=relative_path):
                guide = read(relative_path)
                self.assertIn("DEFAULT_ADMIN_USER=admin", guide)
                self.assertIn("DEFAULT_ADMIN_PASSWORD=", guide)
                self.assertNotIn("admin123", guide)
                self.assertIn(first_start_phrase, guide)

    def test_developer_guides_create_the_tls_files_used_by_compose(self):
        for relative_path in (
            "docs/docs/en/development/developer-deployment.md",
            "docs/docs/zh/development/developer-deployment.md",
        ):
            with self.subTest(path=relative_path):
                guide = read(relative_path)
                compose_position = guide.index("./scripts/dev-up.sh")
                certificate_position = guide.index("mkcert -cert-file")
                self.assertLess(certificate_position, compose_position)
                self.assertIn("traefik/certs/dev-cert.pem", guide)
                self.assertIn("traefik/certs/dev-key.pem", guide)

    def test_basic_compose_ci_only_runs_config_gates(self):
        workflow = read(".github/workflows/ci.yml")
        compose_job = workflow.split("  compose:\n", 1)[1]

        self.assertIn("MONGODB_USERNAME: hyac-root", compose_job)
        self.assertIn("DEFAULT_ADMIN_USER: admin", compose_job)
        self.assertNotIn("cp .env.example .env", compose_job)
        self.assertNotIn("01-create-mongo-keyfile.sh", compose_job)
        self.assertNotIn("docker run", compose_job)
        self.assertIn("docker compose config --quiet", compose_job)
        self.assertIn(
            "docker compose -f docker-compose.dev.yml --env-file .env.example config --quiet",
            compose_job,
        )
        self.assertEqual(compose_job.count("docker compose"), 2)
        self.assertNotIn("docker compose up", compose_job)

    def test_production_readme_access_points_match_compose_routes(self):
        headings = {
            "README.md": "访问地址",
            "README.en.md": "Access Points",
        }
        for relative_path, heading in headings.items():
            with self.subTest(path=relative_path):
                source = read(relative_path)
                match = re.search(
                    rf"### 🌐 {re.escape(heading)}\n(?P<section>.*?)(?=\n### |\n## )",
                    source,
                    re.DOTALL,
                )
                self.assertIsNotNone(match)
                section = match.group("section")
                self.assertIn("https://console.<DOMAIN_NAME>", section)
                self.assertNotIn("RustFS Console", section)
                self.assertNotIn("9001", section)


if __name__ == "__main__":
    unittest.main()
