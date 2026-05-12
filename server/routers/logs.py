import asyncio
from typing import Any, AsyncGenerator, Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from core.docker_manager import docker_manager
from core.jwt_auth import get_current_user
from models.applications_model import Application

router = APIRouter(
    prefix="/logs",
    tags=["Logs Management"],
    responses={404: {"description": "Not found"}},
)

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


@router.get("/runtime_stream/{app_id}")
async def stream_runtime_logs(
    request: Request,
    app_id: str,
    tail: int = Query(0, ge=0, le=5000),
    func_id: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    """
    Stream runtime container logs for an application.

    The runtime stream is the single source for live console logs.
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

                normalized = _format_sse_data(chunk)
                if func_id and f"[func:{func_id}]" not in normalized:
                    continue

                yield {
                    "event": "log",
                    "id": str(event_id),
                    "data": normalized,
                }
                event_id += 1
        except Exception as exc:
            logger.warning(f"Runtime log stream for '{container_name}' ended: {exc}")
            yield {"event": "error", "data": str(exc)}
        finally:
            if log_iterator and hasattr(log_iterator, "close"):
                await asyncio.to_thread(log_iterator.close)

    return EventSourceResponse(event_generator())
