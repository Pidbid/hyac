"""Application-scoped dynamic environment management."""

import asyncio
import os

from loguru import logger

from core.runtime_client import get_runtime_client
from models.applications_model import Application, EnvironmentVariable


RESERVED_ENV_KEYS = {
    "APP_ID",
    "APP_DB_USERNAME",
    "APP_DB_PASSWORD",
    "RUNTIME_TOKEN",
    "RUNTIME_GENERATION",
    "CONTROL_PLANE_URL",
    "MONGODB_USERNAME",
    "MONGODB_PASSWORD",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_INTERNAL_ENDPOINT",
    "S3_SECURE_INTERNAL",
    "SECRET_KEY",
    "DEV_MODE",
    "DEBUG",
    "LSP_MODE",
    "LSP_SIDECAR_URL",
    "LSP_SIDECAR_TIMEOUT_SECONDS",
    "LSP_SIDECAR_FALLBACK_LEGACY",
}

_managed_keys: set[str] = set()


def _filter_user_envs(
    environment_variables: list[EnvironmentVariable],
) -> dict[str, str]:
    envs = {}
    for item in environment_variables:
        if item.key in RESERVED_ENV_KEYS:
            logger.warning("Ignoring reserved environment variable: {}", item.key)
            continue
        envs[item.key] = str(item.value)
    return envs


async def get_dynamic_envs(application: Application | None = None) -> dict[str, str]:
    if application is None:
        bootstrap = await get_runtime_client().bootstrap()
        application = Application.model_validate(bootstrap["application"])
    return _filter_user_envs(application.environment_variables or [])


def _apply_environment_snapshot(latest: dict[str, str]) -> None:
    global _managed_keys
    for key in _managed_keys - latest.keys():
        os.environ.pop(key, None)
    for key, value in latest.items():
        os.environ[key] = value
    _managed_keys = set(latest)


async def set_dynamic_env(key: str, value: str) -> None:
    if key in RESERVED_ENV_KEYS:
        raise ValueError(f"Reserved environment key: {key}")
    str_value = str(value)
    await get_runtime_client().set_environment(key, str_value)
    os.environ[key] = str_value
    _managed_keys.add(key)


async def watch_for_env_changes() -> None:
    """Poll the scoped bootstrap snapshot and apply environment changes."""
    while True:
        try:
            latest = await get_dynamic_envs()
            _apply_environment_snapshot(latest)
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to refresh runtime environment; retrying")
            await asyncio.sleep(5)
