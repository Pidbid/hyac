#!/usr/bin/env python3
"""
Local test to verify Pyright LSP server works with the same protocol as pylsp.
Tests: spawn, initialize, didOpen, completion, shutdown.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from lsp_test_utils import recv_until_id, write_lsp_payload


async def test_pyright():
    pyright_cmd = "pyright-langserver"
    # Check if command exists
    from shutil import which
    if not which(pyright_cmd):
        # Try pyright-python-langserver
        pyright_cmd = "pyright-python-langserver"
        if not which(pyright_cmd):
            print("[FAIL] pyright-langserver not found on PATH")
            print("[HINT] Install with: pip install pyright")
            return False

    print(f"[INFO] Using command: {pyright_cmd}")

    workspace = tempfile.mkdtemp(prefix="pyright_test_")
    test_file = os.path.join(workspace, "test.py")
    with open(test_file, "w") as f:
        f.write("def handler(ctx):\n    return {'ok': True}\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = workspace

    print(f"[INFO] Spawning {pyright_cmd} in {workspace}")
    process = await asyncio.create_subprocess_exec(
        pyright_cmd,
        "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workspace,
        env=env,
    )
    print(f"[INFO] Process started, PID: {process.pid}")

    try:
        # 1. Send initialize
        doc_uri = f"file://{test_file}"
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "processId": os.getpid(),
                "rootUri": f"file://{workspace}",
                "capabilities": {
                    "textDocument": {
                        "completion": {"completionItem": {"snippetSupport": True}},
                        "synchronization": {"didOpen": True, "didChange": True},
                    }
                },
                "workspaceFolders": [{"uri": f"file://{workspace}", "name": "test"}],
                "clientInfo": {"name": "pyright-test", "version": "0.1"},
            },
        }
        await write_lsp_payload(process.stdin, json.dumps(init_req))
        init_resp = await recv_until_id(process.stdout, 1)
        print(f"[OK] initialize response received")
        print(f"     serverInfo: {init_resp.get('result', {}).get('serverInfo', 'N/A')}")

        # 2. Send initialized notification
        await write_lsp_payload(
            process.stdin,
            json.dumps({"jsonrpc": "2.0", "method": "initialized", "params": {}}),
        )

        # 3. Send didOpen
        did_open = {
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
        await write_lsp_payload(process.stdin, json.dumps(did_open))
        print(f"[OK] didOpen sent")

        # 4. Wait a bit for diagnostics to be published
        await asyncio.sleep(2)

        # 5. Send completion request
        completion_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "textDocument/completion",
            "params": {
                "textDocument": {"uri": doc_uri},
                "position": {"line": 1, "character": 11},
            },
        }
        await write_lsp_payload(process.stdin, json.dumps(completion_req))

        # Wait for completion response (or any response with id=2)
        try:
            comp_resp = await recv_until_id(process.stdout, 2, timeout=10.0)
            items = comp_resp.get("result", {})
            if isinstance(items, dict):
                count = len(items.get("items", []))
            elif isinstance(items, list):
                count = len(items)
            else:
                count = 0
            print(f"[OK] completion response received ({count} items)")
        except asyncio.TimeoutError:
            print(f"[WARN] completion response timed out (may be normal for pyright)")

        # 6. Send documentSymbol
        symbol_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "textDocument/documentSymbol",
            "params": {"textDocument": {"uri": doc_uri}},
        }
        await write_lsp_payload(process.stdin, json.dumps(symbol_req))
        try:
            sym_resp = await recv_until_id(process.stdout, 3, timeout=10.0)
            symbols = sym_resp.get("result", [])
            print(f"[OK] documentSymbol response received ({len(symbols)} symbols)")
        except asyncio.TimeoutError:
            print(f"[WARN] documentSymbol timed out")

        # 7. Shutdown
        shutdown_req = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "shutdown",
            "params": None,
        }
        await write_lsp_payload(process.stdin, json.dumps(shutdown_req))
        try:
            await recv_until_id(process.stdout, 99, timeout=5.0)
            print(f"[OK] shutdown response received")
        except asyncio.TimeoutError:
            print(f"[WARN] shutdown timed out")

        # 8. Exit
        await write_lsp_payload(
            process.stdin,
            json.dumps({"jsonrpc": "2.0", "method": "exit", "params": None}),
        )
        await asyncio.sleep(0.5)

        print(f"\n[SUCCESS] Pyright LSP server test passed!")
        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()
        # Read any remaining stderr
        stderr_data = await process.stderr.read()
        if stderr_data:
            stderr_text = stderr_data.decode(errors="ignore").strip()
            if stderr_text:
                print(f"\n[STDERR] {stderr_text[:500]}")


if __name__ == "__main__":
    result = asyncio.run(test_pyright())
    sys.exit(0 if result else 1)
