import asyncio

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from lsp.shim_bridge import ShimBridge


class SidecarBridgeError(RuntimeError):
    pass


class SidecarBridge:
    def __init__(self, sidecar_url: str, timeout_seconds: int):
        self.sidecar_url = sidecar_url
        self.timeout_seconds = timeout_seconds

    async def proxy(
        self,
        websocket: WebSocket,
        app_id: str,
        session_id: str,
        workspace: str = "/app",
    ) -> None:
        url = (
            f"{self.sidecar_url}?app_id={app_id}&session_id={session_id}&workspace={workspace}"
        )
        bridge = ShimBridge(virtual_workspace="/app/.hyac_lsp")
        try:
            async with websockets.connect(url, open_timeout=self.timeout_seconds) as conn:
                await self._run_bidirectional_proxy(websocket, conn, bridge)
        except Exception as exc:
            raise SidecarBridgeError(str(exc)) from exc

    async def _run_bidirectional_proxy(
        self, client_ws: WebSocket, sidecar_ws, bridge: ShimBridge
    ) -> None:
        upstream = asyncio.create_task(
            self._client_to_sidecar(client_ws, sidecar_ws, bridge)
        )
        downstream = asyncio.create_task(
            self._sidecar_to_client(client_ws, sidecar_ws, bridge)
        )
        done, pending = await asyncio.wait(
            [upstream, downstream], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            err = task.exception()
            if err and not isinstance(err, WebSocketDisconnect):
                logger.warning(f"LSP sidecar proxy task ended with error: {err}")

    async def _client_to_sidecar(
        self, client_ws: WebSocket, sidecar_ws, bridge: ShimBridge
    ) -> None:
        async for message in client_ws.iter_text():
            await sidecar_ws.send(bridge.outbound(message))

    async def _sidecar_to_client(
        self, client_ws: WebSocket, sidecar_ws, bridge: ShimBridge
    ) -> None:
        async for message in sidecar_ws:
            if isinstance(message, bytes):
                payload = message.decode("utf-8", errors="ignore")
                await client_ws.send_text(bridge.inbound(payload))
            else:
                await client_ws.send_text(bridge.inbound(message))
