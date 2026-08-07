import os
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest


def test_app_config_imports_without_pydantic_v2_deprecation_warnings():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import warnings; "
                "from pydantic.warnings import PydanticDeprecatedSince20; "
                "warnings.simplefilter('error', PydanticDeprecatedSince20); "
                "import core.config"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    assert result.returncode == 0, result.stderr


def test_app_settings_ignore_dotenv_and_keep_case_sensitive_environment(
    monkeypatch, tmp_path
):
    from core.config import Settings

    (tmp_path / ".env").write_text(
        "DEV_MODE=false\nAPP_ID=dotenv-app\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_ID", raising=False)
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("app_id", "lowercase-app")

    settings = Settings()

    assert settings.DEV_MODE is True
    assert settings.APP_ID is None


@pytest.mark.asyncio
async def test_ctx_env_rejects_legacy_platform_secret_persistence(monkeypatch):
    from context import EnvContext
    from core import env_manager

    runtime_client = type(
        "RuntimeClient",
        (),
        {"set_environment": AsyncMock()},
    )()
    monkeypatch.setattr(env_manager, "get_runtime_client", lambda: runtime_client)

    context = EnvContext()
    for key in ("SECRET_KEY", "MONGODB_PASSWORD", "MONGODB_USERNAME"):
        with pytest.raises(ValueError, match="Reserved environment key"):
            await context.set(key, "attack")

    runtime_client.set_environment.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_snapshot_ignores_persisted_legacy_platform_secrets():
    from core import env_manager

    application = type(
        "Application",
        (),
        {
            "environment_variables": [
                type("Env", (), {"key": "SECRET_KEY", "value": "legacy"})(),
                type("Env", (), {"key": "MONGODB_PASSWORD", "value": "legacy"})(),
                type("Env", (), {"key": "USER_ALLOWED", "value": "visible"})(),
            ]
        },
    )()

    assert await env_manager.get_dynamic_envs(application) == {
        "USER_ALLOWED": "visible"
    }
