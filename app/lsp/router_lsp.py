import asyncio
import os
import re
import traceback

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from starlette.websockets import WebSocketState

from core.config import settings
from lsp.session_manager import LspSessionManager
from lsp.sidecar_client import SidecarBridge, SidecarBridgeError

router = APIRouter()
session_manager = LspSessionManager()

CONTENT_LENGTH_PATTERN = re.compile(rb"Content-Length: (\d+)\r\n")


async def _run_legacy_lsp_session(websocket: WebSocket) -> None:
    lsp_process = None
    try:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        lsp_env = os.environ.copy()
        python_path = lsp_env.get("PYTHONPATH", "")
        lsp_env["PYTHONPATH"] = (
            f"{project_root}:{python_path}" if python_path else project_root
        )

        logger.info(f"Starting pyright-langserver with PYTHONPATH: {lsp_env['PYTHONPATH']}")

        lsp_process = await asyncio.create_subprocess_exec(
            "pyright-langserver",
            "--stdio",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/app",
            env=lsp_env,
        )
        logger.info(f"pyright-langserver started, PID: {lsp_process.pid}")

        reader_task = asyncio.create_task(_read_from_lsp(lsp_process, websocket))
        writer_task = asyncio.create_task(_write_to_lsp(lsp_process, websocket))
        stderr_task = asyncio.create_task(_log_lsp_stderr(lsp_process))

        done, pending = await asyncio.wait(
            [reader_task, writer_task, stderr_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        logger.info("Client disconnected.")
    except Exception as e:
        logger.error(f"LSP session error: {e}\n{traceback.format_exc()}")
    finally:
        if lsp_process and lsp_process.returncode is None:
            logger.info(f"Terminating LSP process (PID: {lsp_process.pid})...")
            lsp_process.terminate()
            await lsp_process.wait()
            logger.info("LSP process terminated.")


async def _read_from_lsp(
    process: asyncio.subprocess.Process, websocket: WebSocket
):
    try:
        if not process.stdout:
            return
        while not process.stdout.at_eof():
            header_buffer = b""
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                header_buffer += line
                if b"\r\n\r\n" in header_buffer:
                    break
            match = CONTENT_LENGTH_PATTERN.search(header_buffer)
            if not match:
                if header_buffer:
                    logger.warning(f"Cannot parse Content-Length: {header_buffer.decode(errors='ignore')}")
                continue
            content_length = int(match.group(1))
            body_start = header_buffer.find(b"\r\n\r\n") + 4
            buffer = header_buffer[body_start:]
            body = buffer
            remaining = content_length - len(body)
            if remaining > 0:
                body += await process.stdout.readexactly(remaining)
            await websocket.send_text(body.decode("utf-8"))
    except asyncio.IncompleteReadError:
        logger.info("LSP stdout closed.")
    except WebSocketDisconnect:
        logger.info("Client disconnected while reading LSP output.")
    except Exception as e:
        logger.error(f"Error reading from LSP: {e}\n{traceback.format_exc()}")


async def _write_to_lsp(
    process: asyncio.subprocess.Process, websocket: WebSocket
):
    try:
        if not process.stdin:
            return
        async for message in websocket.iter_text():
            body = message.encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
            process.stdin.write(header + body)
            await process.stdin.drain()
    except WebSocketDisconnect:
        logger.info("Client disconnected while writing to LSP.")
    except Exception as e:
        logger.error(f"Error writing to LSP: {e}\n{traceback.format_exc()}")


async def _log_lsp_stderr(process: asyncio.subprocess.Process):
    if not process.stderr:
        return
    while not process.stderr.at_eof():
        line = await process.stderr.readline()
        if line:
            pass


async def _run_sidecar_lsp_session(websocket: WebSocket, app_id: str, session_id: str):
    bridge = SidecarBridge(
        sidecar_url=settings.LSP_SIDECAR_URL,
        timeout_seconds=settings.LSP_SIDECAR_TIMEOUT_SECONDS,
    )
    await bridge.proxy(
        websocket=websocket,
        app_id=app_id,
        session_id=session_id,
        workspace="/app/.hyac_lsp",
    )


def _use_sidecar_mode() -> bool:
    return settings.LSP_MODE.strip().lower() == "sidecar"


@router.websocket("/__lsp__")
async def lsp_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    app_id = os.environ.get("APP_ID", "unknown")
    mode = "sidecar" if _use_sidecar_mode() else "legacy"
    session = session_manager.create(app_id=app_id, mode=mode)
    logger.info(
        f"LSP WebSocket connected. session={session.session_id}, app_id={app_id}, mode={mode}, active={session_manager.size()}"
    )

    try:
        if mode == "sidecar":
            try:
                await _run_sidecar_lsp_session(
                    websocket=websocket, app_id=app_id, session_id=session.session_id
                )
            except SidecarBridgeError as exc:
                logger.error(f"Sidecar mode failed: {exc}")
                if not settings.LSP_SIDECAR_FALLBACK_LEGACY:
                    raise
                logger.warning("Falling back to legacy pyright mode")
                await _run_legacy_lsp_session(websocket)
        else:
            await _run_legacy_lsp_session(websocket)
    except WebSocketDisconnect:
        logger.info("Client disconnected.")
    except Exception as e:
        logger.error(f"LSP endpoint error: {e}\n{traceback.format_exc()}")
    finally:
        session_manager.remove(session.session_id)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except RuntimeError:
                pass
        logger.info(
            f"LSP WebSocket closed. session={session.session_id}, active={session_manager.size()}"
        )
