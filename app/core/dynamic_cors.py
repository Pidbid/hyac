"""ASGI middleware that applies the latest application CORS policy."""

import asyncio

from loguru import logger
from starlette.middleware.cors import CORSMiddleware

from core.runtime_client import get_runtime_client
from models.applications_model import Application, CORSConfig


class DynamicCORSMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        fastapi_app = scope.get("app")
        config = getattr(
            getattr(fastapi_app, "state", None),
            "cors_config",
            CORSConfig(),
        )
        middleware = CORSMiddleware(
            self.app,
            allow_origins=config.allow_origins,
            allow_credentials=config.allow_credentials,
            allow_methods=config.allow_methods,
            allow_headers=config.allow_headers,
        )
        await middleware(scope, receive, send)


async def watch_runtime_config(app) -> None:
    """Refresh application and CORS state from the scoped control plane."""
    while True:
        try:
            bootstrap = await get_runtime_client().bootstrap()
            application = Application.model_validate(bootstrap["application"])
            app.state.application = application
            app.state.cors_config = application.cors
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to refresh runtime application config; retrying")
            await asyncio.sleep(5)
