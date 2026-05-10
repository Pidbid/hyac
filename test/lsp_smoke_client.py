#!/usr/bin/env python3
import argparse
import asyncio
import json
import sys
from typing import Any

try:
    import websockets
except Exception as exc:  # pragma: no cover
    print(f"[ERROR] failed to import websockets: {exc}", file=sys.stderr)
    print("[HINT] install with: pip install websockets", file=sys.stderr)
    sys.exit(2)


def build_initialize_request(doc_uri: str) -> dict[str, Any]:
    root_uri = doc_uri.rsplit("/", 1)[0]
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "processId": None,
            "rootUri": root_uri,
            "capabilities": {},
            "workspaceFolders": [{"uri": root_uri, "name": "smoke"}],
            "clientInfo": {"name": "hyac-lsp-smoke", "version": "0.1"},
        },
    }


async def recv_until_id(ws, req_id: int, timeout_seconds: float) -> dict[str, Any]:
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout_seconds)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("id") == req_id:
            return data


async def smoke(url: str, doc_uri: str, timeout_seconds: float) -> None:
    async with websockets.connect(url, open_timeout=timeout_seconds) as ws:
        init_req = build_initialize_request(doc_uri)
        await ws.send(json.dumps(init_req))
        init_resp = await recv_until_id(ws, 1, timeout_seconds)
        if "result" not in init_resp:
            raise RuntimeError(f"initialize response invalid: {init_resp}")

        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": doc_uri,
                            "languageId": "python",
                            "version": 1,
                            "text": "def handler(ctx):\n    return {'ok': True}\n",
                        }
                    },
                }
            )
        )
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "textDocument/documentSymbol",
                    "params": {"textDocument": {"uri": doc_uri}},
                }
            )
        )
        symbol_resp = await recv_until_id(ws, 2, timeout_seconds)
        if "result" not in symbol_resp:
            raise RuntimeError(f"documentSymbol response invalid: {symbol_resp}")

        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": None}))
        _ = await recv_until_id(ws, 3, timeout_seconds)
        await ws.send(json.dumps({"jsonrpc": "2.0", "method": "exit", "params": None}))


def main() -> int:
    parser = argparse.ArgumentParser(description="LSP websocket smoke test")
    parser.add_argument("--url", required=True, help="LSP websocket URL")
    parser.add_argument(
        "--doc-uri",
        default="inmemory:///tmp/smoke.py",
        help="Document URI for didOpen",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="Timeout seconds")
    args = parser.parse_args()

    try:
        asyncio.run(smoke(args.url, args.doc_uri, args.timeout))
        print(f"[OK] smoke passed: {args.url}")
        return 0
    except Exception as exc:
        print(f"[FAIL] smoke failed: {args.url}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

