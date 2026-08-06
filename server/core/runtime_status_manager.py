from loguru import logger

from core.task_worker import reconcile_running_apps


async def sync_runtime_status():
    """Run the CAS-based reconciler as the sole runtime status authority."""
    try:
        await reconcile_running_apps()
    except Exception as e:
        logger.error(f"An error occurred during runtime status synchronization: {e}")
