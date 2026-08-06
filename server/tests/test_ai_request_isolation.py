import asyncio
import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from routers import ai as ai_router


class _Stream:
    def __init__(self, content: str):
        self.content = content

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.content is None:
            raise StopAsyncIteration
        content, self.content = self.content, None
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
        )


class _Field:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return self.name, other


class _Application:
    app_id = _Field("app_id")
    users = _Field("users")
    find_one = None


class AIRequestIsolationTest(IsolatedAsyncioTestCase):
    async def test_concurrent_streams_keep_credentials_and_proxy_request_local(self):
        apps = {
            "app-a": SimpleNamespace(
                ai_config=SimpleNamespace(
                    api_key="key-a",
                    provider="openai",
                    model="model-a",
                    base_url="https://a.invalid/v1",
                    proxy="http://proxy-a.invalid",
                )
            ),
            "app-b": SimpleNamespace(
                ai_config=SimpleNamespace(
                    api_key="key-b",
                    provider="openai",
                    model="model-b",
                    base_url="https://b.invalid/v1",
                    proxy="http://proxy-b.invalid",
                )
            ),
        }
        calls = []
        queries = []

        async def find_application(*conditions):
            predicates = dict(conditions)
            self.assertEqual(set(predicates), {"app_id", "users"})
            self.assertEqual(predicates["users"], "admin")
            self.assertIn(predicates["app_id"], apps)
            queries.append(predicates)
            return apps[predicates["app_id"]]

        _Application.find_one = find_application

        async def completion(**kwargs):
            calls.append(kwargs)
            await asyncio.sleep(0)
            return _Stream(kwargs["api_key"])

        async def invoke(app_id: str):
            request = ai_router.ChatCompletionRequest(
                appid=app_id,
                model="ignored",
                messages=[ai_router.ChatMessage(role="user", content="hello")],
            )
            response = await ai_router.chat_completions(
                request,
                SimpleNamespace(username="admin"),
            )
            return [item async for item in response.body_iterator]

        with (
            patch.object(ai_router, "Application", _Application),
            patch.object(ai_router.litellm, "acompletion", completion),
        ):
            result_a, result_b = await asyncio.gather(
                asyncio.create_task(invoke("app-a"), name="app-a"),
                asyncio.create_task(invoke("app-b"), name="app-b"),
            )

        by_key = {call["api_key"]: call for call in calls}
        self.assertCountEqual(
            queries,
            [
                {"app_id": "app-a", "users": "admin"},
                {"app_id": "app-b", "users": "admin"},
            ],
        )
        self.assertEqual(by_key["key-a"]["api_base"], "https://a.invalid/v1")
        self.assertEqual(by_key["key-a"]["proxy"], "http://proxy-a.invalid")
        self.assertEqual(by_key["key-b"]["api_base"], "https://b.invalid/v1")
        self.assertEqual(by_key["key-b"]["proxy"], "http://proxy-b.invalid")
        self.assertIn("key-a", "".join(result_a))
        self.assertIn("key-b", "".join(result_b))
