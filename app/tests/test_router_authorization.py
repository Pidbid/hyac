import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

import router as router_module


class _StrictDenyingRuntimeClient:
    def __init__(self, denial: httpx.HTTPStatusError) -> None:
        self._denial = denial
        self.calls = 0

    async def authorize_function(self, function_id, authorization):
        assert function_id == "document-function-id"
        assert authorization == "Bearer denied"
        self.calls += 1
        raise self._denial


def _request(method: str) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/function-id",
            "raw_path": b"/function-id",
            "query_string": b"",
            "headers": [(b"authorization", b"Bearer denied")],
            "client": ("127.0.0.1", 1234),
            "server": ("runtime", 443),
            "app": SimpleNamespace(
                state=SimpleNamespace(common_modules={})
            ),
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE", "PATCH"])
async def test_authorization_failure_suppresses_function_execution(
    monkeypatch,
    method,
):
    def handler():
        return "must-not-run"

    function = SimpleNamespace(
        function_id="document-function-id",
        function_name="protected",
        timeout=5,
        memory_limit=128,
    )
    load = AsyncMock(return_value=(handler, function, inspect.signature(handler)))
    execute = AsyncMock(side_effect=AssertionError("function executed after denial"))
    denied_request = httpx.Request("POST", "http://control/internal/authorize")
    denied_response = httpx.Response(
        403,
        json={"detail": "denied"},
        request=denied_request,
    )
    runtime_client = _StrictDenyingRuntimeClient(
        httpx.HTTPStatusError(
            "denied",
            request=denied_request,
            response=denied_response,
        )
    )
    monkeypatch.setattr(router_module, "_load_function_details", load)
    monkeypatch.setattr(router_module, "_execute_and_log", execute)
    monkeypatch.setattr(router_module, "get_runtime_client", lambda: runtime_client)

    with pytest.raises(HTTPException) as raised:
        await router_module.dynamic_handler(
            _request(method),
            "route-function-id",
            BackgroundTasks(),
            SimpleNamespace(app_id="APP12345"),
        )

    assert raised.value.status_code == 403
    assert runtime_client.calls == 1
    execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function_id", "authorization"),
    [
        ("wrong-function-id", "Bearer denied"),
        ("document-function-id", "Bearer replaced"),
    ],
)
async def test_authorization_denial_fake_rejects_wrong_forwarded_parameters(
    function_id,
    authorization,
):
    request = httpx.Request("POST", "http://control/internal/authorize")
    response = httpx.Response(403, json={"detail": "denied"}, request=request)
    runtime_client = _StrictDenyingRuntimeClient(
        httpx.HTTPStatusError("denied", request=request, response=response)
    )

    with pytest.raises(AssertionError):
        await runtime_client.authorize_function(function_id, authorization)
