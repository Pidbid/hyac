# app/core/cache_watcher.py
import asyncio
from core.config import settings
from loguru import logger
from models.functions_model import Function
from core.cache import code_cache


async def watch_function_changes():
    """
    Watches for changes in the 'functions' collection and invalidates the cache
    for updated functions.
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
                # The correct ID to use is the short, human-readable 'function_id',
                # not the MongoDB '_id', to match the key used in CodeLoader.
                function_id = full_document.get("function_id")

                if not (app_id and function_id):
                    logger.warning(
                        f"Could not process cache invalidation due to missing app_id or function_id: {full_document}"
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
                        f"Invalidating cache for function {function_id} in app {app_id} due to {operation_type} operation."
                    )
                    code_cache.invalidate(app_id, function_id)

    except asyncio.CancelledError:
        logger.info("Function change watcher task cancelled.")
    except Exception as e:
        logger.error(f"Error in function change watcher: {e}", exc_info=True)
        # Optional: Add a delay and retry mechanism
        await asyncio.sleep(5)
        asyncio.create_task(watch_function_changes())
