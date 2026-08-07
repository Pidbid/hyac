import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from routers import functions as functions_router


class _Field:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return (self.name, other)


class _Application:
    app_id = _Field("app_id")
    users = _Field("users")
    result = SimpleNamespace(app_id="app-a")

    @classmethod
    async def find_one(cls, *_conditions):
        return cls.result


class _Function:
    app_id = _Field("app_id")
    function_id = _Field("function_id")
    users = _Field("users")
    result = None

    @classmethod
    async def find_one(cls, *_conditions):
        return cls.result


class FunctionAuthPolicyTests(IsolatedAsyncioTestCase):
    def setUp(self):
        _Application.result = SimpleNamespace(app_id="app-a")
        _Function.result = None
        self.user = SimpleNamespace(username="alice")

    async def _proxy(self, *, requires_auth, headers=None):
        _Function.result = SimpleNamespace(requires_auth=requires_auth)
        response = SimpleNamespace(status_code=200, text='{"ok": true}', headers={})
        request = AsyncMock(return_value=response)
        proxy_request = functions_router.ProxyRequest(
            target_url="https://app-a.example.com/function-id",
            method="GET",
            headers=headers or {},
        )

        with (
            patch.object(functions_router.settings, "DOMAIN_NAME", "example.com"),
            patch.object(functions_router, "Application", _Application),
            patch.object(functions_router, "Function", _Function),
            patch.object(functions_router.http_client, "request", request),
        ):
            result = await functions_router.test_function(
                proxy_request,
                self.user,
                authorization="Bearer console-token",
            )

        self.assertEqual(result.code, 0)
        return httpx.Headers(request.await_args.kwargs["headers"])

    async def test_public_function_proxy_does_not_forward_console_token(self):
        headers = await self._proxy(requires_auth=False)

        self.assertNotIn("authorization", headers)

    async def test_protected_function_proxy_forwards_console_token_by_default(self):
        headers = await self._proxy(requires_auth=True)

        self.assertEqual(headers["authorization"], "Bearer console-token")

    async def test_explicit_proxy_authorization_takes_precedence_case_insensitively(self):
        headers = await self._proxy(
            requires_auth=True,
            headers={"authorization": "Bearer explicit-token"},
        )

        self.assertEqual(headers["authorization"], "Bearer explicit-token")
        self.assertEqual(headers.get_list("authorization"), ["Bearer explicit-token"])

    async def test_function_metadata_update_persists_auth_policy(self):
        function = SimpleNamespace(
            requires_auth=True,
            function_type=functions_router.FunctionType.ENDPOINT,
            function_name="hello",
            description="old",
            tags=[],
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )
        _Function.result = function
        request = functions_router.UpdateFunctionMetaRequest(
            appId="app-a",
            id="function-id",
            name="hello",
            description="updated",
            tags=["api"],
            requires_auth=False,
        )

        with (
            patch.object(functions_router, "Application", _Application),
            patch.object(functions_router, "Function", _Function),
        ):
            response = await functions_router.update_function_meta(request, self.user)

        self.assertEqual(response.code, 0)
        self.assertFalse(function.requires_auth)
        function.update_timestamp.assert_called_once_with()
        function.save.assert_awaited_once_with()


if __name__ == "__main__":
    import unittest

    unittest.main()
