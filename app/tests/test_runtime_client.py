import sys
from pathlib import Path

import pytest


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))


def test_runtime_control_client_ignores_application_proxy_environment(monkeypatch):
    from core import runtime_client

    captured = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(runtime_client.settings, "APP_ID", "test-app")
    monkeypatch.setattr(runtime_client.settings, "RUNTIME_TOKEN", "test-token")
    monkeypatch.setattr(runtime_client.httpx, "AsyncClient", FakeAsyncClient)

    runtime_client.RuntimeControlClient()

    assert captured["trust_env"] is False


@pytest.mark.asyncio
async def test_get_runtime_client_rebuilds_singleton_after_close(monkeypatch):
    from core import runtime_client

    monkeypatch.setattr(runtime_client.settings, "APP_ID", "test-app")
    monkeypatch.setattr(runtime_client.settings, "RUNTIME_TOKEN", "test-token")
    monkeypatch.setattr(runtime_client, "_runtime_client", None)

    first = runtime_client.get_runtime_client()
    await first.close()
    second = runtime_client.get_runtime_client()

    try:
        assert second is not first
        assert not second._client.is_closed
    finally:
        await second.close()
        monkeypatch.setattr(runtime_client, "_runtime_client", None)
