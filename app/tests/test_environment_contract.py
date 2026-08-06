from unittest.mock import AsyncMock

import pytest


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
