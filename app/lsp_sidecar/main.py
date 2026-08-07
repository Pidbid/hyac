import asyncio
import json
from contextlib import asynccontextmanager
from shutil import which

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger
from starlette.websockets import WebSocketState

from lsp_sidecar.formatter import run_formatter
from lsp_sidecar.lsp_process import LspProcess, read_lsp_payload, write_lsp_payload
from lsp_sidecar.pool import LspProcessPool
from lsp_sidecar.runtime_requirements import REQUIRED_COMMANDS


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = LspProcessPool(idle_ttl_seconds=300)
    logger.info("LSP sidecar started (pyright)")
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    missing = [
        command
        for command in REQUIRED_COMMANDS
        if which(command) is None
    ]
    if missing:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "missing": missing,
                "hint": "Rebuild the lsp-sidecar image.",
            },
        )
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
                pass


async def _bridge_messages(websocket: WebSocket, process: LspProcess) -> None:
    if not process.process.stdin or not process.process.stdout or not process.process.stderr:
        raise RuntimeError("LSP stdio streams are not initialized")

    docs: dict[str, str] = {}

    up_task = asyncio.create_task(
        _client_to_lsp(websocket=websocket, stdin=process.process.stdin, docs=docs)
    )
    down_task = asyncio.create_task(
        _lsp_to_client(websocket=websocket, stdout=process.process.stdout)
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


def _track_document(docs: dict[str, str], payload: str) -> None:
    """Track document content from didOpen/didChange for formatting support."""
    try:
        msg = json.loads(payload)
    except json.JSONDecodeError:
        return
    method = msg.get("method")
    params = msg.get("params", {})

    if method == "textDocument/didOpen":
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        text = td.get("text", "")
        if uri:
            docs[uri] = text
    elif method == "textDocument/didChange":
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        changes = params.get("contentChanges", [])
        if uri and changes:
            # Full sync: last change has the full text
            last = changes[-1]
            if "text" in last and "range" not in last:
                docs[uri] = last["text"]


def _handle_formatting(payload: str, docs: dict[str, str]) -> str | None:
    """Intercept textDocument/formatting and run autopep8."""
    try:
        msg = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if msg.get("method") != "textDocument/formatting":
        return None

    req_id = msg.get("id")
    params = msg.get("params", {})
    td = params.get("textDocument", {})
    uri = td.get("uri", "")

    source = docs.get(uri, "")
    if not source:
        return json.dumps({
            "jsonrpc": "2.0", "id": req_id, "result": []
        })

    try:
        result = run_formatter(source)
        lines = source.split("\n")
        total_lines = len(lines)
        last_col = len(lines[-1]) if lines else 0
        edit = {
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": total_lines - 1, "character": last_col}
            },
            "newText": result
        }
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": [edit]})
    except Exception as exc:
        logger.error(f"autopep8 format failed: {exc}")
        return json.dumps({
            "jsonrpc": "2.0", "id": req_id, "result": []
        })


async def _client_to_lsp(
    websocket: WebSocket, stdin: asyncio.StreamWriter, docs: dict[str, str]
) -> None:
    async for message in websocket.iter_text():
        _track_document(docs, message)
        formatting_resp = _handle_formatting(message, docs)
        if formatting_resp:
            await websocket.send_text(formatting_resp)
            continue
        await write_lsp_payload(stdin=stdin, payload=message)


async def _lsp_to_client(
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
            logger.debug(f"[pyright] {line.decode(errors='ignore').strip()}")


if __name__ == "__main__":
    uvicorn.run("lsp_sidecar.main:app", host="0.0.0.0", port=9002, workers=1)
