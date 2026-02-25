import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from loguru import logger
from starlette.websockets import WebSocketState

from lsp_sidecar.lsp_process import LspProcess, read_lsp_payload, write_lsp_payload
from lsp_sidecar.pool import LspProcessPool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = LspProcessPool(idle_ttl_seconds=300)
    logger.info("LSP sidecar started.")
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/lsp")
async def lsp_bridge(websocket: WebSocket):
    await websocket.accept()
    app_id = websocket.query_params.get("app_id", "unknown")
    session_id = websocket.query_params.get("session_id", "unknown")
    workspace = websocket.query_params.get("workspace", "/app")
    pool_key = (app_id, workspace)
    pool: LspProcessPool = app.state.pool

    process: LspProcess | None = None
    try:
        process = await pool.acquire(pool_key)
        logger.info(
            f"Sidecar session opened: session={session_id}, app_id={app_id}, workspace={workspace}, pid={process.process.pid}"
        )
        await _bridge_messages(websocket, process)
    except WebSocketDisconnect:
        logger.info(f"Sidecar client disconnected: session={session_id}")
    except Exception as exc:
        logger.error(
            f"Sidecar bridge error: session={session_id}, app_id={app_id}, error={exc}"
        )
    finally:
        if process:
            if process.alive:
                await pool.release(process)
            else:
                await pool.discard(process)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except RuntimeError:
                # The websocket may already be closed by the ASGI server.
                pass


async def _bridge_messages(websocket: WebSocket, process: LspProcess) -> None:
    if not process.process.stdin or not process.process.stdout or not process.process.stderr:
        raise RuntimeError("pylsp stdio streams are not initialized")

    up_task = asyncio.create_task(
        _client_to_pylsp(websocket=websocket, stdin=process.process.stdin)
    )
    down_task = asyncio.create_task(
        _pylsp_to_client(websocket=websocket, stdout=process.process.stdout)
    )
    err_task = asyncio.create_task(_log_stderr(stderr=process.process.stderr))

    done, pending = await asyncio.wait(
        [up_task, down_task, err_task], return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    for task in done:
        exc = task.exception()
        if exc and not isinstance(exc, WebSocketDisconnect):
            raise exc


async def _client_to_pylsp(
    websocket: WebSocket, stdin: asyncio.StreamWriter
) -> None:
    async for message in websocket.iter_text():
        await write_lsp_payload(stdin=stdin, payload=message)


async def _pylsp_to_client(
    websocket: WebSocket, stdout: asyncio.StreamReader
) -> None:
    while not stdout.at_eof():
        payload = await read_lsp_payload(stdout=stdout)
        if payload:
            await websocket.send_text(payload)


async def _log_stderr(stderr: asyncio.StreamReader) -> None:
    while not stderr.at_eof():
        line = await stderr.readline()
        if line:
            logger.debug(f"[pylsp] {line.decode(errors='ignore').strip()}")


if __name__ == "__main__":
    uvicorn.run("lsp_sidecar.main:app", host="0.0.0.0", port=9002, workers=1)
