# app/core/env_manager.py
import os
from loguru import logger

from core.config import settings
from models.applications_model import Application, EnvironmentVariable


async def get_dynamic_envs():
    """
    Asynchronously retrieves dynamic environment variables for the current application
    directly from MongoDB to ensure data is always up-to-date.
    """
    app_id = settings.APP_ID
    if not app_id:
        return {}

    # Directly query the database on every call
    application = await Application.find_one({"app_id": app_id})
    if not application or not application.environment_variables:
        return {}

    # Convert list of EnvironmentVariable objects to a single dict
    envs = {item.key: str(item.value) for item in application.environment_variables}

    return envs


async def set_dynamic_env(key: str, value: str):
    """
    Sets a dynamic environment variable and persists it to the database.
    """
    app_id = settings.APP_ID
    if not app_id:
        return

    application = await Application.find_one({"app_id": app_id})
    if not application:
        return

    # Ensure environment_variables is not None
    if application.environment_variables is None:
        application.environment_variables = []

    # Update existing env var or add a new one
    env_found = False
    for env in application.environment_variables:
        if env.key == key:
            env.value = value
            env_found = True
            break

    if not env_found:
        application.environment_variables.append(
            EnvironmentVariable(key=key, value=value)
        )

    # Update the timestamp and save the changes
    application.update_timestamp()
    await application.save()

    # Directly update the process environment to make the change immediately available.
    os.environ[key] = value
