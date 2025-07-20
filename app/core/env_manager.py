# app/core/env_manager.py
import os
import asyncio
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
    str_value = str(value)  # Ensure value is a string
    for env in application.environment_variables:
        if env.key == key:
            env.value = str_value
            env_found = True
            break

    if not env_found:
        application.environment_variables.append(
            EnvironmentVariable(key=key, value=str_value)
        )

    # Update the timestamp and save the changes
    application.update_timestamp()
    await application.save()

    # Directly update the process environment to make the change immediately available.
    os.environ[key] = str(value)


async def watch_for_env_changes():
    """
    Watches for changes in the application's environment variables using MongoDB Change Streams
    and updates the process's environment variables in real-time.
    """
    app_id = settings.APP_ID
    if not app_id:
        logger.warning("APP_ID not set, cannot watch for environment changes.")
        return

    try:
        collection = Application.get_motor_collection()
        pipeline = [
            {
                "$match": {
                    "operationType": "update",
                    "fullDocument.app_id": app_id,
                }
            }
        ]

        logger.info(f"Starting environment variable watcher for app: {app_id}")
        async with collection.watch(
            pipeline=pipeline, full_document="updateLookup"
        ) as stream:
            async for change in stream:
                logger.debug(f"Detected environment change for {app_id}: {change}")

                # Extract the full document, which contains the latest state
                full_document = change.get("fullDocument")
                if not full_document:
                    continue

                # Get the latest environment variables from the document
                latest_vars_list = full_document.get("environment_variables", [])
                latest_vars_dict = {
                    item["key"]: str(item["value"]) for item in latest_vars_list
                }

                # Identify keys that are currently in os.environ but managed by this app
                # This requires knowing which keys were set by this system initially.
                # A simpler approach is to compare with the latest snapshot.

                current_app_keys = {
                    k
                    for k, v in os.environ.items()
                    if k in latest_vars_dict
                    or any(
                        env.key == k
                        for env in getattr(
                            Application.find_one({"app_id": app_id}),
                            "environment_variables",
                            [],
                        )
                    )
                }

                # Find variables to remove
                keys_to_remove = current_app_keys - set(latest_vars_dict.keys())
                for key in keys_to_remove:
                    if key in os.environ:
                        del os.environ[key]
                        logger.info(f"Removed environment variable: {key}")

                # Find variables to add or update
                for key, value in latest_vars_dict.items():
                    if os.getenv(key) != value:
                        os.environ[key] = value
                        logger.info(f"Updated environment variable: {key}")

    except Exception as e:
        logger.error(
            f"Error in environment variable watcher for {app_id}: {e}", exc_info=True
        )
        # Wait a bit before trying to reconnect to avoid spamming logs on persistent errors
        await asyncio.sleep(10)
        # It might be useful to restart the watcher upon recoverable errors
        asyncio.create_task(watch_for_env_changes())
