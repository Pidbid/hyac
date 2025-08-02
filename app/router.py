# app/router.py
import inspect
import io
import json
import time
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Dict, Tuple, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from loguru import logger

from code_loader import CodeLoader
from context import EnvContext, FunctionContext
from core.common_model import BaseResponse
from core.config import settings
from core.db_manager import db_manager
from core.exceptions import APIException
from core.faas_minio import app_id_context
from core.logger import LogType
from models.applications_model import Application
from models.functions_model import Function
from models.statistics_model import CallStatus, FunctionMetric

router = APIRouter()
code_loader = CodeLoader()


# --- Dependencies ---


def get_app_id() -> str:
    """Dependency to extract the app_id from the settings."""
    app_id = settings.APP_ID
    if not app_id:
        raise APIException(code=500, msg="APP_ID environment variable is not set.")
    return app_id


async def get_application(request: Request) -> Application:
    """Dependency to provide the pre-loaded application object from app.state."""
    if not hasattr(request.app.state, "application"):
        raise APIException(code=503, msg="Application not ready or pre-loading failed.")
    return request.app.state.application


async def get_dynamic_clients(application: Application = Depends(get_application)):
    """Dependency to get dynamic MongoDB clients from the connection manager."""
    try:
        pymongo_client, motor_client = await db_manager.get_clients(application)
        yield pymongo_client, motor_client
    except Exception as e:
        logger.error(
            f"Failed to get database clients for app {application.app_id}: {e}"
        )
        raise APIException(
            code=500, msg=f"Database connection failed for app {application.app_id}"
        )


# --- Helper Functions for Refactoring ---


async def _load_function_details(
    request: Request, app_id: str, func_id: str
) -> Tuple[dict, Function, inspect.Signature]:
    """Loads function code, document, and signature, handling errors."""
    loaded_data = await code_loader.load_function_by_ids(app_id, func_id)
    if not loaded_data:
        logger.warning(f"Function not found: {app_id}/{func_id}")
        raise APIException(code=404, msg="Function not found")

    func, func_doc, signature = loaded_data
    handler_func = func.get("handler")

    if not handler_func or not signature:
        raise APIException(
            code=500,
            msg=f"Function {func_id} loaded but has no valid 'handler' method or signature.",
        )
    return handler_func, func_doc, signature


async def _prepare_arguments(
    request: Request, signature: inspect.Signature, context: FunctionContext
) -> Dict[str, Any]:
    """Prepares the arguments for the handler function based on its signature."""
    handler_args = {}
    if "context" in signature.parameters:
        handler_args["context"] = context
    if "request" in signature.parameters:
        handler_args["request"] = request

    # Intelligently pass body/query parameters
    body_params = {}
    if request.method in ["POST", "PUT", "PATCH"]:
        content_type = request.headers.get("content-type", "").lower()
        try:
            if "application/json" in content_type:
                body_params = await request.json()
            elif (
                "application/x-www-form-urlencoded" in content_type
                or "multipart/form-data" in content_type
            ):
                body_params = await request.form()
            elif "body" in signature.parameters:  # For raw body
                handler_args["body"] = await request.body()
        except json.JSONDecodeError:
            raise APIException(code=400, msg="Invalid JSON body")

    # Combine query and body params, giving body params precedence
    request_params = {**dict(request.query_params), **body_params}

    for param_name in signature.parameters:
        if param_name in request_params and param_name not in handler_args:
            handler_args[param_name] = request_params[param_name]

    return handler_args


async def _execute_and_log(handler_func, handler_args: dict, log_func: logger) -> Any:
    """Executes the handler, capturing and logging its stdout/stderr."""
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    result = None
    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            result = await handler_func(**handler_args)
    finally:
        stdout = stdout_capture.getvalue().strip()
        stderr = stderr_capture.getvalue().strip()
        if stdout:
            log_func.info(stdout)
        if stderr:
            log_func.error(stderr)
    return result


async def _track_metric(
    start_time: float,
    app_id: str,
    func_id: str,
    function_name: str,
    status: CallStatus,
    error_info: Optional[dict],
):
    """Asynchronously inserts a function call metric into the database."""
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


# --- Main API Route ---


@router.api_route(
    "/{func_id:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    include_in_schema=False,
)
async def dynamic_handler(
    request: Request,
    func_id: str,
    background_tasks: BackgroundTasks,
    application: Application = Depends(get_application),
    clients: tuple = Depends(get_dynamic_clients),
):
    """Handles all dynamic function calls, routing them to the appropriate loaded code."""
    if func_id == "favicon.ico":
        return Response(status_code=204)

    start_time = time.time()
    status = CallStatus.SUCCESS
    error_info = None
    app_id = application.app_id
    function_name = "Unknown"

    try:
        app_id_context.set(app_id)

        # 1. Load function details (code, doc, signature)
        handler_func, func_doc, signature = await _load_function_details(
            request, app_id, func_id
        )
        function_name = func_doc.function_name

        # 2. Create context and loggers
        pymongo_client, motor_client = clients
        context = FunctionContext(
            app_id=app_id,
            func_id=func_id,
            pymongo_db=pymongo_client[app_id],
            motor_db=motor_client[app_id],
            code_loader=code_loader,
            env=EnvContext(),
            common=request.app.state.common_modules,
            notification_config=application.notification,
        )
        log_func = logger.bind(
            app_id=app_id,
            function_id=func_id,
            function_name=function_name,
            logtype=LogType.FUNCTION,
        )

        # 3. Prepare arguments for the handler
        handler_args = await _prepare_arguments(request, signature, context)

        # 4. Execute the function and return its result
        return await _execute_and_log(handler_func, handler_args, log_func)

    except APIException as api_exc:
        status = CallStatus.ERROR
        error_info = {"type": "APIException", "detail": api_exc.msg}
        raise api_exc
    except Exception as e:
        status = CallStatus.ERROR
        error_info = {"type": "Exception", "detail": str(e)}
        logger.error("Unhandled exception in dynamic_handler: {}", e, exc_info=True)
        return BaseResponse(code=500, msg=str(e))
    finally:
        # 5. Track the metric in the background
        background_tasks.add_task(
            _track_metric,
            start_time,
            app_id,
            func_id,
            function_name,
            status,
            error_info,
        )
