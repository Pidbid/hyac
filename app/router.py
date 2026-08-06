# app/router.py
import inspect
import json
import time
import traceback
from typing import Any, Dict, Tuple, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from bson import ObjectId
from loguru import logger

from code_loader import CodeLoader
from context import EnvContext, FunctionContext
from core.common_model import BaseResponse
from core.config import settings
from core.exceptions import APIException
from core.faas_s3 import app_id_context
from core.function_executor import (
    FunctionExecutionError,
    INVOCATION_REQUEST_SNAPSHOT_KEY,
    RequestBodyTooLarge,
    execute_function,
    snapshot_request,
)
from core.logger import LogType, prefix_runtime_lines
from core.runtime_client import get_runtime_client
from models.applications_model import Application
from models.functions_model import Function
from models.statistics_model import CallStatus

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


# --- Helper Functions for Refactoring ---


async def _load_function_details(
    request: Request, app_id: str, func_id: str
) -> Tuple[dict, Function, inspect.Signature]:
    """Loads function code, document, and signature, handling errors."""
    loaded_data = await code_loader.load_function_by_ids(app_id, func_id)
    if not loaded_data:
        logger.warning(f"Function not found: {app_id}/{func_id}")
        raise APIException(code=404, msg="Function not found")

    handler_func, func_doc, signature = loaded_data

    if not handler_func or not signature:
        raise APIException(
            code=500,
            msg=f"Function {func_id} loaded but has no valid 'handler' method or signature.",
        )
    return handler_func, func_doc, signature


async def _prepare_arguments(
    request: Request,
    signature: inspect.Signature,
    context: FunctionContext,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Prepares the arguments for the handler function based on its signature."""
    handler_args = {}
    try:
        request_snapshot = await snapshot_request(request)
    except RequestBodyTooLarge as exc:
        raise APIException(code=413, msg=str(exc)) from exc
    handler_args[INVOCATION_REQUEST_SNAPSHOT_KEY] = request_snapshot

    if "ctx" in signature.parameters:
        handler_args["ctx"] = context
    if "request" in signature.parameters:
        handler_args["request"] = request_snapshot
    if "background_tasks" in signature.parameters:
        handler_args["background_tasks"] = background_tasks

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
                handler_args["body"] = request_snapshot.body
        except json.JSONDecodeError:
            raise APIException(code=400, msg="Invalid JSON body")

    if "body" in signature.parameters and "body" not in handler_args:
        handler_args["body"] = request_snapshot.body

    # Combine query and body params, giving body params precedence
    request_params = {**dict(request.query_params), **body_params}

    for param_name in signature.parameters:
        if param_name in request_params and param_name not in handler_args:
            handler_args[param_name] = request_params[param_name]

    return handler_args


async def _execute_and_log(
    handler_func,
    handler_args: dict,
    log_func: logger,
    timeout_seconds: int,
    memory_limit_mb: int,
    log_context: Optional[dict[str, object]] = None,
) -> Any:
    """Execute one handler inside a disposable, resource-limited process."""
    def log_remote_exception(exc: BaseException) -> None:
        stdout = getattr(exc, "remote_stdout", "").strip()
        stderr = getattr(exc, "remote_stderr", "").strip()
        traceback_text = getattr(exc, "remote_traceback", "")
        if stdout:
            log_func.info(stdout)
        if stderr:
            log_func.error(stderr)
        if traceback_text:
            log_func.error(traceback_text.rstrip())

    try:
        execution = await execute_function(
            handler_func,
            handler_args,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            log_context=log_context,
        )
    except FunctionExecutionError as exc:
        stdout = exc.stdout.strip()
        stderr = exc.stderr.strip()
        if stdout:
            log_func.info(stdout)
        if stderr:
            log_func.error(stderr)
        if exc.traceback_text:
            log_func.error(exc.traceback_text.rstrip())
        raise
    except (APIException, HTTPException) as exc:
        log_remote_exception(exc)
        raise

    if execution.stdout.strip():
        log_func.info(execution.stdout.strip())
    if execution.stderr.strip():
        log_func.error(execution.stderr.strip())
    return execution.value


def _serialize_handler_result(result: Any) -> Any:
    """
    Converts handler return values into JSON-compatible data.
    """
    if isinstance(result, Response):
        return result
    return JSONResponse(
        content=jsonable_encoder(result, custom_encoder={ObjectId: str})
    )


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
    await get_runtime_client().write_metric(
        {
            "function_id": func_id,
            "function_name": function_name,
            "status": status.value,
            "execution_time": execution_time,
            "extra": error_info,
        }
    )


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
):
    """Handles all dynamic function calls, routing them to the appropriate loaded code."""
    if func_id == "favicon.ico":
        return Response(status_code=204)

    start_time = time.time()
    status = CallStatus.SUCCESS
    error_info = None
    app_id = application.app_id
    function_name = "Unknown"
    function_log = logger.bind(
        app_id=app_id,
        function_id=func_id,
        function_name=function_name,
        logtype=LogType.FUNCTION,
        runtime_label=f"[func:{func_id}] ",
    )

    try:
        app_id_context.set(app_id)

        # 1. Load function details (code, doc, signature)
        handler_func, func_doc, signature = await _load_function_details(
            request, app_id, func_id
        )
        function_name = func_doc.function_name

        try:
            await get_runtime_client().authorize_function(
                func_doc.function_id,
                request.headers.get("authorization"),
            )
        except httpx.HTTPStatusError as exc:
            detail = "Function authorization failed"
            try:
                detail = exc.response.json().get("detail", detail)
            except ValueError:
                pass
            raise HTTPException(status_code=exc.response.status_code, detail=detail)

        # 2. Create context and loggers
        context = FunctionContext(
            app_id=app_id,
            func_id=func_id,
            pymongo_db=None,
            async_db=None,
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
            runtime_label=f"[func:{func_id}] ",
        )
        function_log = log_func
        log_context = {
            "app_id": app_id,
            "function_id": func_id,
            "function_name": function_name,
            "logtype": LogType.FUNCTION,
            "runtime_label": f"[func:{func_id}] ",
        }

        # 3. Prepare arguments for the handler
        handler_args = await _prepare_arguments(
            request, signature, context, background_tasks
        )

        # 4. Execute the function and return its result
        result = await _execute_and_log(
            handler_func,
            handler_args,
            log_func,
            timeout_seconds=func_doc.timeout,
            memory_limit_mb=func_doc.memory_limit,
            log_context=log_context,
        )
        return _serialize_handler_result(result)

    except APIException as api_exc:
        status = CallStatus.ERROR
        error_info = {"type": "APIException", "detail": api_exc.msg}
        function_log.warning("Function request failed: {}", api_exc.msg)
        raise api_exc
    except HTTPException as http_exc:
        status = CallStatus.ERROR
        error_info = {"type": "HTTPException", "detail": str(http_exc.detail)}
        raise
    except Exception as e:
        status = CallStatus.ERROR
        error_type = (
            e.error_type if isinstance(e, FunctionExecutionError) else type(e).__name__
        )
        error_info = {"type": error_type, "detail": str(e)}
        traceback_text = traceback.format_exc().strip()
        runtime_traceback = prefix_runtime_lines(
            traceback_text, f"[func:{func_id}] "
        )
        function_log.error(
            "Unhandled exception in dynamic_handler\n{}", runtime_traceback
        )
        return BaseResponse(
            code=500,
            msg=str(e),
            data={
                "error_type": error_type,
                "function_id": func_id,
                "function_name": function_name,
            },
        )
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
