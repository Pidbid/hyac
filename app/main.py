# app/main.py
import os
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# Assuming a shared database manager and logger configuration
from core.database import MongoDBManager
from core.logger import configure_logging
from router import router as dynamic_router
from core.db_manager import db_manager
from core.dependency_loader import install_app_dependencies
from core.cache_watcher import watch_function_changes
from core.env_manager import get_dynamic_envs

from models.applications_model import Application, CORSConfig


# Filter for health check endpoint to prevent logging
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # The message format for uvicorn access logs is a tuple.
        # e.g. ('127.0.0.1:52995', 'GET', '/__runtime_health__', 'HTTP/1.1', 200)
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            # Check if the path is the health check endpoint
            if record.args[2] == "/__runtime_health__":
                return False
        return True


# Add the filter to the uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


mongodb_manager = MongoDBManager()
cors_config = CORSConfig()
app_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_ready
    """
    Asynchronous context manager to handle application startup and shutdown events
    for the execution environment.
    """
    # Initialize the database connection.
    await mongodb_manager.init_beanie()
    logger.info("Executor database initialized.")

    # Load CORS configuration
    app = await Application.find_one(Application.app_id == os.environ.get("APP_ID"))
    cors_config = app.cors or None
    if not cors_config:
        logger.error("Failed to load CORS configuration.")
        cors_config = CORSConfig(
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    # Install dependencies for the specific application.
    await install_app_dependencies()

    # Configure the logging system.
    configure_logging()
    logger.info("Executor application starting up...")

    # Load initial environment variables into the process.
    initial_envs = await get_dynamic_envs()
    os.environ.update(initial_envs)
    logger.info(
        f"Loaded {len(initial_envs)} dynamic environment variables into process."
    )

    # Start the function code cache watcher.
    asyncio.create_task(watch_function_changes())
    # await watch_for_env_changes()
    app_ready = True
    logger.info("Executor is now ready to accept requests.")

    yield

    # Close all database connections managed by the connection pool.
    db_manager.close_all()
    logger.info("Executor application shutting down.")


app = FastAPI(lifespan=lifespan)

# Add CORS middleware to allow cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config.allow_origins,
    allow_credentials=cors_config.allow_credentials,
    allow_methods=cors_config.allow_methods,
    allow_headers=cors_config.allow_headers,
)


@app.get("/")
async def hyac_app_base_route():
    return {"message": "Hyac Executor is up and running!"}


@app.get("/__runtime_health__")
async def health_check(response: Response):
    """
    Health check endpoint to verify if the application is ready.
    """
    if app_ready:
        return {"status": "ready"}
    else:
        response.status_code = 503
        return {"status": "not_ready"}


# Include the dynamic execution router.
app.include_router(dynamic_router)

if __name__ == "__main__":
    # Run the application using uvicorn server.
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True, workers=1)
