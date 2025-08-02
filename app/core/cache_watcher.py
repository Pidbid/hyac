# app/core/cache_watcher.py
import asyncio
from fastapi import FastAPI
from core.config import settings
from loguru import logger
from models.functions_model import Function, FunctionType
from core.cache import code_cache
from code_loader import CodeLoader


async def watch_function_changes(app: FastAPI):
    """
    Watches for changes in the 'functions' collection, invalidates the cache,
    and reloads common functions into the app.state.
    """
    logger.info("Starting function change watcher...")
    try:
        # Get the 'functions' collection from the Function model
        collection = Function.get_motor_collection()

        # Use a pipeline to only watch for 'update' and 'replace' operations
        # for the current app_id
        pipeline = [
            {
                "$match": {
                    "operationType": {"$in": ["update", "replace"]},
                    "fullDocument.app_id": settings.APP_ID,
                }
            }
        ]

        async with collection.watch(pipeline, full_document="updateLookup") as stream:
            async for change in stream:
                logger.debug(f"Change detected: {change}")

                operation_type = change.get("operationType")
                full_document = change.get("fullDocument")

                if not full_document:
                    logger.warning(
                        f"Change event did not include full document: {change}"
                    )
                    continue

                app_id = full_document.get("app_id")
                function_type = full_document.get(
                    "function_type", FunctionType.ENDPOINT.value
                )

                identifier = None
                # Invalidate by function_name for COMMON functions, and function_id for others.
                if function_type == FunctionType.COMMON.value:
                    identifier = full_document.get("function_name")
                else:
                    identifier = full_document.get("function_id")

                if not (app_id and identifier):
                    logger.warning(
                        f"Could not process cache invalidation due to missing app_id or identifier: {full_document}"
                    )
                    continue

                should_invalidate = False
                if operation_type == "update":
                    # For 'update', check if 'code' was updated
                    if "code" in change.get("updateDescription", {}).get(
                        "updatedFields", {}
                    ):
                        should_invalidate = True
                elif operation_type == "replace":
                    # For 'replace', we assume the code might have changed and invalidate
                    should_invalidate = True

                if should_invalidate:
                    logger.info(
                        f"Invalidating cache for {function_type} function '{identifier}' in app '{app_id}' due to {operation_type}."
                    )
                    code_cache.invalidate(app_id, identifier)

                    # If a common function was updated, reload all common functions into app.state
                    if function_type == FunctionType.COMMON.value:
                        logger.info(
                            f"Common function '{identifier}' updated. Reloading all common functions for app '{app_id}'."
                        )
                        code_loader = CodeLoader()
                        reloaded_modules = await code_loader.load_all_common_functions(
                            app_id
                        )
                        app.state.common_modules = reloaded_modules
                        logger.info(
                            "Successfully reloaded common functions into app.state."
                        )

    except asyncio.CancelledError:
        logger.info("Function change watcher task cancelled.")
    except Exception as e:
        logger.error(f"Error in function change watcher: {e}", exc_info=True)
        # Optional: Add a delay and retry mechanism
        await asyncio.sleep(5)
        asyncio.create_task(watch_function_changes(app))
