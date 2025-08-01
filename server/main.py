# main.py
from contextlib import asynccontextmanager
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from core.exceptions import APIException
from core.scheduler_manager import scheduler_manager

from core.database import mongodb_manager
from core.logger import configure_logging
from core.config import settings
from routers import (
    ai_router,
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
    scheduler_router,
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

    # Start the dynamic scheduler manager
    await scheduler_manager.start()
    logger.info("Scheduler manager started.")

    yield

    # Shutdown the dynamic scheduler manager
    scheduler_manager.shutdown()
    logger.info("Scheduler manager shut down.")

    # Clean up all running app containers on shutdown
    logger.info("Shutting down all running app containers...")
    app_ids_to_stop = list(running_apps.keys())
    for app_id in app_ids_to_stop:
        await stop_app_container(app_id)
    logger.info("Application shutting down.")


app = FastAPI(lifespan=lifespan)


@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException):
    """
    Global exception handler for APIException.
    Returns a JSON response with the error code and message.
    """
    return JSONResponse(
        status_code=200,
        content={"code": exc.code, "msg": exc.msg},
    )


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
app.include_router(ai_router)
app.include_router(scheduler_router)

# The proxy router must be included last, as it's a catch-all.
app.include_router(proxy_router)
