"""Poll application-scoped function metadata and invalidate stale code caches."""

import asyncio

from fastapi import FastAPI
from loguru import logger

from code_loader import CodeLoader
from core.cache import code_cache
from core.config import settings
from core.runtime_client import get_runtime_client


def _fingerprint(functions: list[dict]) -> tuple:
    return tuple(
        sorted(
            (
                item.get("function_id"),
                item.get("function_name"),
                item.get("status"),
                item.get("updated_at"),
            )
            for item in functions
        )
    )


async def watch_function_changes(app: FastAPI) -> None:
    """Refresh function caches without granting the runtime platform DB access."""
    app_id = settings.APP_ID
    if not app_id:
        raise RuntimeError("APP_ID is required")
    previous = None
    while True:
        try:
            functions = await get_runtime_client().get_functions()
            current = _fingerprint(functions)
            if previous is not None and current != previous:
                code_cache.clear_app_cache(app_id)
                app.state.common_modules = await CodeLoader().load_all_common_functions(
                    app_id
                )
                logger.info("Function snapshot changed; runtime caches refreshed")
            previous = current
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to refresh function snapshot; retrying")
            await asyncio.sleep(5)
