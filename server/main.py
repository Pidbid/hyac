# main.py
from contextlib import asynccontextmanager
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.runtime_status_manager import sync_runtime_status

from core.database import mongodb_manager
from core.logger import configure_logging
from core.config import settings
from routers import (
    applications_router,
    database_router,
    functions_router,
    logs_router,
    statistics_router,
    storage_router,
    users_router,
    function_templates_router,
    settings_router,
    health_router,
    runtime_router,
    proxy_router,
)
from core.initialization import InitializationService
import asyncio
from core.docker_manager import (
    build_app_image_if_not_exists,
    stop_app_container,
    running_apps,
)
from core.task_worker import watch_for_tasks


# Filter for health check endpoint to prevent logging
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # The message format for uvicorn access logs is a tuple.
        # e.g. ('127.0.0.1:52995', 'GET', '/__server_health__', 'HTTP/1.1', 200)
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            # Check if the path is the health check endpoint
            if record.args[2] == "/__server_health__":
                return False
        return True


# Add the filter to the uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous context manager to handle application startup and shutdown events.
    """
    # Initialize the database connection.
    await mongodb_manager.init_beanie()
    logger.info("Database initialized.")

    # Configure the logging system.
    configure_logging()
    logger.info("Application starting up...")

    # Perform initialization checks.
    try:
        await InitializationService.check_and_initialize()
    except Exception as e:
        logger.error(f"Initialization failed: {e}")

    # Build the app executor image on startup
    await build_app_image_if_not_exists()

    # Start the task worker to watch for new tasks
    asyncio.create_task(watch_for_tasks())
    logger.info("Task worker started.")

    # Initialize existing applications by creating tasks for the running worker
    await InitializationService.initialize_existing_apps()

    # Start the scheduler for background tasks
    scheduler.add_job(
        sync_runtime_status, "interval", seconds=30, id="sync_runtime_status_job"
    )
    scheduler.start()
    logger.info("Scheduler started for runtime status synchronization.")

    yield

    # Shutdown the scheduler
    scheduler.shutdown()
    logger.info("Scheduler shut down.")

    # Clean up all running app containers on shutdown
    logger.info("Shutting down all running app containers...")
    app_ids_to_stop = list(running_apps.keys())
    for app_id in app_ids_to_stop:
        await stop_app_container(app_id)
    logger.info("Application shutting down.")


app = FastAPI(lifespan=lifespan)

# Add CORS middleware to allow cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include application routers.
app.include_router(functions_router)
app.include_router(applications_router)
app.include_router(users_router)
app.include_router(database_router)
app.include_router(storage_router)
app.include_router(logs_router)
app.include_router(statistics_router)
app.include_router(function_templates_router)
app.include_router(settings_router)
app.include_router(runtime_router)
app.include_router(health_router)

# The proxy router must be included last, as it's a catch-all.
app.include_router(proxy_router)

# if __name__ == "__main__":
#     # Run the application using uvicorn server.
#     uvicorn.run(
#         "main:app",
#         host="0.0.0.0",
#         port=settings.get("SERVICE_PORT"),
#         reload=True,
#         workers=1,
#     )
