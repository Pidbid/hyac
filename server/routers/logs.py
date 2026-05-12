# routers/services/logs.py
import asyncio
import math
from loguru import logger
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Iterator, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.websockets import WebSocketState
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.jwt_auth import get_current_user, get_current_user_for_websocket
from core.docker_manager import docker_manager
from core.log_watcher import log_watcher
from models.applications_model import Application
from models.common_model import BaseResponse
from models.functions_model import Function
from models.logger_model import LogEntry, LogLevel, LogType

router = APIRouter(
    prefix="/logs",
    tags=["Logs Management"],
    responses={404: {"description": "Not found"}},
)


class LogQueryExtra(BaseModel):
    """Request model for log query filters."""

    level: Optional[LogLevel] = None
    logtype: Optional[LogType] = None
    dateStart: Optional[datetime] = None
    dateEnd: Optional[datetime] = None


class FunctionLogRequest(BaseModel):
    """Request model for querying function logs."""

    appId: str
    funcId: str
    page: int = 1
    length: int = 10
    extra: Optional[LogQueryExtra] = None


class AppLogRequest(BaseModel):
    """Request model for querying application logs."""

    appId: str
    page: int = 1
    length: int = 10
    extra: Optional[LogQueryExtra] = None


_STREAM_END = object()


def _next_log_chunk(log_iterator: Iterator[bytes]) -> bytes | object:
    """Read one chunk from Docker's blocking log iterator."""
    return next(log_iterator, _STREAM_END)


def _format_sse_data(raw: bytes | str) -> str:
    """Normalize Docker log bytes for SSE delivery."""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw


async def _resolve_runtime_container(app_id: str, username: str) -> tuple[str, Any]:
    """Validate app access and return its runtime container."""
    app = await Application.find_one(
        Application.app_id == app_id, Application.users == username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    container_name = f"hyac-app-runtime-{app.app_id.lower()}"
    if not docker_manager.client:
        raise HTTPException(status_code=503, detail="Docker client is not available")

    try:
        container = await asyncio.to_thread(
            docker_manager.client.containers.get, container_name
        )
    except Exception as exc:
        logger.warning(f"Runtime log container '{container_name}' is unavailable: {exc}")
        raise HTTPException(status_code=404, detail="Runtime container not found")

    return container_name, container


@router.post("/function_logs", response_model=BaseResponse)
async def get_function_logs(
    data: FunctionLogRequest, current_user=Depends(get_current_user)
):
    """
    Query function logs with pagination and filters.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    query_filter: Dict[str, Any] = {
        "app_id": data.appId,
        "function_id": data.funcId,
    }

    if data.extra:
        if data.extra.level:
            query_filter["level"] = data.extra.level
        if data.extra.logtype:
            query_filter["logtype"] = data.extra.logtype
        if data.extra.dateStart and data.extra.dateEnd:
            query_filter["timestamp"] = {
                "$gte": data.extra.dateStart,
                "$lte": data.extra.dateEnd,
            }
        elif data.extra.dateStart:
            query_filter["timestamp"] = {"$gte": data.extra.dateStart}
        elif data.extra.dateEnd:
            query_filter["timestamp"] = {"$lte": data.extra.dateEnd}

    query = LogEntry.find(query_filter)
    total_count = await query.count()
    skip = (data.page - 1) * data.length
    logs = await query.sort("-timestamp").skip(skip).limit(data.length).to_list()

    page_num = math.ceil(total_count / data.length) if data.length > 0 else 0

    return BaseResponse(
        code=0,
        msg="success",
        data={
            "data": logs,
            "pageNum": page_num,
            "pageSize": data.length,
            "total": total_count,
        },
    )


@router.post("/app_logs", response_model=BaseResponse)
async def get_app_logs(data: AppLogRequest, current_user=Depends(get_current_user)):
    """
    Query application logs with pagination and filters.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    query_filter: Dict[str, Any] = {"app_id": data.appId}

    if data.extra:
        if data.extra.level:
            query_filter["level"] = data.extra.level
        if data.extra.logtype:
            query_filter["logtype"] = data.extra.logtype
        if data.extra.dateStart and data.extra.dateEnd:
            query_filter["timestamp"] = {
                "$gte": data.extra.dateStart,
                "$lte": data.extra.dateEnd,
            }
        elif data.extra.dateStart:
            query_filter["timestamp"] = {"$gte": data.extra.dateStart}
        elif data.extra.dateEnd:
            query_filter["timestamp"] = {"$lte": data.extra.dateEnd}

    query = LogEntry.find(query_filter)
    total_count = await query.count()
    skip = (data.page - 1) * data.length
    logs = await query.sort("-timestamp").skip(skip).limit(data.length).to_list()

    page_num = math.ceil(total_count / data.length) if data.length > 0 else 0

    return BaseResponse(
        code=0,
        msg="success",
        data={
            "data": logs,
            "pageNum": page_num,
            "pageSize": data.length,
            "total": total_count,
        },
    )


@router.get("/runtime_stream/{app_id}")
async def stream_runtime_logs(
    request: Request,
    app_id: str,
    tail: int = Query(1000, ge=1, le=5000),
    current_user=Depends(get_current_user),
):
    """
    Stream runtime container logs for an application.

    This path follows the Laf-style live log model: real-time display reads from
    the running container stream, while MongoDB remains the historical store.
    """
    container_name, container = await _resolve_runtime_container(
        app_id, current_user.username
    )

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        log_iterator = None
        event_id = 1
        try:
            log_iterator = await asyncio.to_thread(
                container.logs,
                stream=True,
                follow=True,
                tail=tail,
                stdout=True,
                stderr=True,
            )

            while not await request.is_disconnected():
                chunk = await asyncio.to_thread(_next_log_chunk, log_iterator)
                if chunk is _STREAM_END:
                    break

                yield {
                    "event": "log",
                    "id": str(event_id),
                    "data": _format_sse_data(chunk),
                }
                event_id += 1
        except Exception as exc:
            logger.warning(f"Runtime log stream for '{container_name}' ended: {exc}")
            yield {"event": "error", "data": str(exc)}
        finally:
            if log_iterator and hasattr(log_iterator, "close"):
                await asyncio.to_thread(log_iterator.close)

    return EventSourceResponse(event_generator())


@router.websocket("/websocket_logs/{app_id}")
async def websocket_logs(
    websocket: WebSocket,
    app_id: str,
    current_user=Depends(get_current_user_for_websocket),
):
    """
    Websocket endpoint to stream logs for a specific function using MongoDB Change Streams.
    The client can send messages to subscribe or unsubscribe from function logs.
    Message format:
    - Subscribe: {"type": "subscribe", "funcId": "your_function_id"}
    - Unsubscribe: {"type": "unsubscribe"}
    """
    await websocket.accept()

    # Verify user has access to the application
    app = await Application.find_one(
        Application.app_id == app_id, Application.users == current_user.username
    )
    if not app:
        await websocket.close(
            code=4001, reason="Application not found or permission denied"
        )
        return

    current_function_id = None
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "subscribe":
                func_id = data.get("funcId")
                if not func_id:
                    await websocket.send_json(
                        {"error": "funcId is required for subscription"}
                    )
                    continue

                # Do nothing if already subscribed to the same function
                if current_function_id == func_id:
                    continue

                # Verify function exists
                func = await Function.find_one(
                    Function.function_id == func_id, Function.app_id == app.app_id
                )
                if not func:
                    await websocket.send_json(
                        {"error": f"Function {func_id} not found or permission denied"}
                    )
                    continue

                # If there's an active subscription, unsubscribe from it first.
                if current_function_id:
                    await log_watcher.unsubscribe(
                        app_id, current_function_id, websocket
                    )
                    logger.info(
                        f"Client switched subscription: Unsubscribed from {app_id}/{current_function_id}"
                    )

                # Subscribe to the new function
                current_function_id = func_id
                await log_watcher.subscribe(app_id, current_function_id, websocket)
                logger.info(
                    f"Client switched subscription: Subscribed to {app_id}/{current_function_id}"
                )

            elif msg_type == "unsubscribe":
                if current_function_id:
                    await log_watcher.unsubscribe(
                        app_id, current_function_id, websocket
                    )
                    logger.info(
                        f"Client unsubscribed from logs for {app_id}/{current_function_id}"
                    )
                    current_function_id = None

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from logs for {app_id}")
    except Exception as e:
        logger.error(f"An error occurred in websocket handling for {app_id}: {e}")
    finally:
        if current_function_id:
            await log_watcher.unsubscribe(app_id, current_function_id, websocket)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close(code=1000)
            except Exception as e:
                logger.warning(f"Error closing websocket for {app_id}: {e}")
        logger.info(f"Websocket connection closed for app {app_id}.")
