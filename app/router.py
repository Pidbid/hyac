# app/router.py
import inspect
import io
import time
import os
import json
from contextlib import redirect_stderr, redirect_stdout

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# These imports will need to be satisfied by copying files into the 'app' directory
from core.config import settings
from context import FunctionContext, EnvContext
from core.faas_minio import app_id_context
from models.applications_model import Application
from models.functions_model import Function
from models.statistics_model import CallStatus, FunctionMetric
from code_loader import CodeLoader
from core.logger import LogType
from core.db_manager import db_manager
from core.common_model import BaseResponse

router = APIRouter()
code_loader = CodeLoader()


def get_app_id() -> str:
    """
    Dependency to extract the app_id from the settings.
    """
    app_id = settings.APP_ID
    if not app_id:
        raise HTTPException(
            status_code=500, detail="APP_ID environment variable is not set."
        )
    return app_id


async def get_application(app_id: str = Depends(get_app_id)) -> Application:
    """
    Dependency to fetch the application object from the database.
    This also ensures the app_id casing is corrected.
    """
    application = await Application.find_one({"app_id": app_id})
    if not application:
        return BaseResponse(code=404, msg="Application not found")
    return application


async def get_dynamic_clients(application: Application = Depends(get_application)):
    """
    Dependency to get dynamic MongoDB clients from the connection manager.
    """
    try:
        pymongo_client, motor_client = await db_manager.get_clients(application)
        yield pymongo_client, motor_client
    except Exception as e:
        logger.error(
            f"Failed to get database clients for app {application.app_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Database connection failed for app {application.app_id}",
        )
    finally:
        # The presence of this finally block is crucial.
        # For a generator-based dependency in FastAPI, after the response is sent,
        # FastAPI will resume the generator. This causes a GeneratorExit exception
        # to be thrown into the generator. Without a `finally` block, this
        # exception would be caught by the `except Exception as e:` block,
        # leading to an erroneous log message. The `finally` block ensures
        # that `GeneratorExit` is handled gracefully without being logged as an error.
        pass


@router.api_route(
    "/{func_id}",  # Simplified route
    methods=["GET", "POST", "PUT", "DELETE"],
    include_in_schema=False,
)
async def dynamic_handler(
    request: Request,
    func_id: str,
    application: Application = Depends(get_application),  # Injected application object
    clients: tuple = Depends(get_dynamic_clients),
):
    """
    Handles all dynamic function calls, routing them to the appropriate loaded code.
    """
    start_time = time.time()
    status = CallStatus.SUCCESS
    error_info = None

    # Get the correctly cased app_id from the application object
    app_id = application.app_id
    function_name = "Unknown"  # Default value

    pymongo_client, motor_client = clients

    try:
        # Set the app_id in the context for MinIO operations.
        app_id_context.set(app_id)

        # Pre-load all common functions for the application.
        common_modules = await code_loader.load_all_common_functions(app_id)

        # Load the endpoint function code and its metadata.
        loaded_data = await code_loader.load_function_by_ids(app_id, func_id)
        if not loaded_data:
            logger.warning(f"Function not found: {app_id}/{func_id}")
            raise HTTPException(status_code=404, detail="Function not found")

        func, func_doc = loaded_data
        function_name = func_doc.function_name  # Get the real-time function name

        # Create a context-specific logger
        log_func = logger.bind(
            app_id=app_id,
            function_id=func_id,
            function_name=function_name,
            logtype=LogType.FUNCTION,
        )
        log_sys = logger.bind(
            app_id=app_id, function_id=func_id, logtype=LogType.SYSTEM
        )

        sys_log_data = {
            "method": request.method,
            "url": request.url._url,
            "headers": dict(request.headers),
            "cookies": dict(request.cookies) or {},
            "query_params": dict(request.query_params) or {},
            "path_params": dict(request.path_params) or {},
        }
        log_sys.info(str(sys_log_data))

        handler_func = func.get("handler")
        if not handler_func:
            raise HTTPException(
                status_code=500,
                detail=f"Function {func_id} loaded but has no 'handler' method.",
            )
        signature = inspect.signature(handler_func)

        handler_args = {}

        # Create the function context, injecting the common modules.
        context = FunctionContext(
            app_id=app_id,
            func_id=func_id,
            pymongo_db=pymongo_client[app_id],
            motor_db=motor_client[app_id],
            code_loader=code_loader,
            env=EnvContext(),
            common=common_modules,
            notification_config=application.notification,
        )
        if "context" in signature.parameters:
            handler_args["context"] = context

        if "request" in signature.parameters:
            handler_args["request"] = request

        # Intelligently pass body/query parameters based on the request method.
        if request.method == "POST":
            try:
                body_params = await request.json()
                for param_name, param_info in signature.parameters.items():
                    if param_name in body_params and param_name not in handler_args:
                        handler_args[param_name] = body_params[param_name]
            except Exception as e:
                log_sys.warning(f"{e}")
                # Do not raise an error if the body is not JSON; let the user function handle it.
                pass
        else:
            query_params = dict(request.query_params)
            for param_name, param_info in signature.parameters.items():
                if param_name in query_params and param_name not in handler_args:
                    handler_args[param_name] = query_params[param_name]

        # Execute the handler function with redirected stdout/stderr.
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        result = None

        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                result = await handler_func(**handler_args)
        finally:
            stdout_output = stdout_capture.getvalue()
            stderr_output = stderr_capture.getvalue()
            if stdout_output:
                log_func.info(f"{stdout_output.strip()}")
            if stderr_output:
                log_func.error(f"{stderr_output.strip()}")

        return result
    except HTTPException as http_exc:
        # Re-raise HTTPException to let FastAPI handle it.
        status = CallStatus.ERROR
        error_info = {"type": "HTTPException", "detail": http_exc.detail}
        raise http_exc
    except Exception as e:
        status = CallStatus.ERROR
        error_info = {"type": "Exception", "detail": str(e)}
        logger.error("Unhandled exception in dynamic_handler: {}", e, exc_info=True)
        # For other unhandled exceptions, return a generic error.
        return {"code": 1, "msg": str(e), "data": None}
    finally:
        execution_time = time.time() - start_time
        metric = FunctionMetric(
            function_id=func_id,
            app_id=app_id,
            function_name=function_name,
            status=status,
            execution_time=execution_time,
            extra=error_info,
        )
        await metric.insert()
