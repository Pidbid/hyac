"""Authenticated client for the Server runtime control plane."""

from typing import Any, Optional

import httpx

from core.config import settings


class RuntimeControlClient:
    def __init__(self) -> None:
        if not settings.APP_ID or not settings.RUNTIME_TOKEN:
            raise RuntimeError("Runtime identity is not configured")
        self.app_id = settings.APP_ID
        self._client = httpx.AsyncClient(
            base_url=settings.CONTROL_PLANE_URL.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.RUNTIME_TOKEN}",
                "X-App-Id": self.app_id,
                "X-Runtime-Generation": str(settings.RUNTIME_GENERATION),
            },
            timeout=10.0,
            trust_env=False,
        )

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()

    async def bootstrap(self) -> dict:
        return await self._request("GET", "/bootstrap")

    async def get_function(self, function_id: str) -> dict:
        return await self._request("GET", f"/functions/{function_id}")

    async def get_functions(self, function_type: Optional[str] = None) -> list[dict]:
        params = {"function_type": function_type} if function_type else None
        return await self._request("GET", "/functions", params=params)

    async def authorize_function(
        self, function_id: str, authorization: Optional[str]
    ) -> dict:
        headers = {}
        if authorization:
            headers["X-Function-Authorization"] = authorization
        return await self._request(
            "POST",
            f"/authorize/{function_id}",
            headers=headers,
        )

    async def write_metric(self, data: dict) -> None:
        await self._request("POST", "/metrics", json=data)

    async def set_environment(self, key: str, value: str) -> None:
        await self._request("PUT", f"/environment/{key}", json={"value": value})

    async def close(self) -> None:
        global _runtime_client
        try:
            await self._client.aclose()
        finally:
            if _runtime_client is self:
                _runtime_client = None


_runtime_client: RuntimeControlClient | None = None


def get_runtime_client() -> RuntimeControlClient:
    global _runtime_client
    if _runtime_client is None:
        _runtime_client = RuntimeControlClient()
    return _runtime_client


def reset_runtime_client_after_fork() -> None:
    """Discard inherited async connection state inside an invocation worker."""
    global _runtime_client
    _runtime_client = None
