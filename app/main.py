# app/main.py
import os
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger

from core.exceptions import APIException

from core.logger import configure_logging
from router import router as dynamic_router
from core.dependency_loader import install_app_dependencies
from core.cache_watcher import watch_function_changes
from core.env_manager import get_dynamic_envs, watch_for_env_changes
from core.runtime_client import get_runtime_client
from core.dynamic_cors import DynamicCORSMiddleware, watch_runtime_config
from lsp.router_lsp import router as lsp_router
from code_loader import CodeLoader

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


cors_config = CORSConfig()
app_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_ready
    """
    Asynchronous context manager to handle application startup and shutdown events
    for the execution environment.
    """
    runtime_client = get_runtime_client()
    bootstrap = await runtime_client.bootstrap()
    application = Application.model_validate(bootstrap["application"])
    cors_config = application.cors or CORSConfig()
    app.state.application = application
    app.state.cors_config = cors_config

    # Pre-load common functions
    code_loader = CodeLoader()
    common_modules = await code_loader.load_all_common_functions(application.app_id)
    app.state.common_modules = common_modules
    logger.info(f"Successfully pre-loaded common functions.")

    # Install dependencies for the specific application.
    await install_app_dependencies(application)

    # Configure the logging system.
    configure_logging()
    logger.info("Executor application starting up...")

    # Load initial environment variables into the process.
    initial_envs = await get_dynamic_envs(application)
    os.environ.update(initial_envs)
    logger.info(
        f"Loaded {len(initial_envs)} dynamic environment variables into process."
    )

    # Start the function code cache watcher.
    background_tasks = [asyncio.create_task(watch_function_changes(app))]
    # Start the environment variable watcher.
    background_tasks.append(asyncio.create_task(watch_for_env_changes()))
    background_tasks.append(asyncio.create_task(watch_runtime_config(app)))
    app_ready = True
    logger.info("Executor is now ready to accept requests.")

    yield

    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)
    await runtime_client.close()
    logger.info("Executor application shutting down.")


app = FastAPI(lifespan=lifespan)


@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException):
    """
    Global exception handler for APIException.
    Returns a JSON response with the error code and message.
    """
    return JSONResponse(
        status_code=200,
        content={"code": exc.code, "msg": exc.msg, "data": None},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return runtime HTTP failures using the public API response contract."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": str(exc.detail), "data": None},
        headers=exc.headers,
    )


# Add CORS middleware to allow cross-origin requests.
app.add_middleware(DynamicCORSMiddleware)


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
app.include_router(lsp_router)

if __name__ == "__main__":
    # Run the application using uvicorn server.
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True, workers=1)
