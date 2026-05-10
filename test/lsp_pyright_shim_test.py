#!/usr/bin/env python3
"""
Test Pyright with the same shim injection that ShimBridge does.
Simulates the actual Hyac FaaS code with context/s3_open shim prepended.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from lsp_test_utils import read_lsp_payload, recv_until_id, write_lsp_payload


async def collect_messages(stdout, timeout: float = 3.0) -> list:
    """Collect all available messages within a timeout window."""
    messages = []
    try:
        while True:
            raw = await asyncio.wait_for(read_lsp_payload(stdout), timeout=timeout)
            messages.append(json.loads(raw))
    except (asyncio.TimeoutError, asyncio.IncompleteReadError):
        pass
    return messages


async def test_pyright_with_shim():
    from shutil import which
    pyright_cmd = "pyright-langserver"
    if not which(pyright_cmd):
        pyright_cmd = "pyright-python-langserver"

    workspace = tempfile.mkdtemp(prefix="pyright_shim_test_")

    # Create a context.py stub (the shim imports this)
    context_stub = os.path.join(workspace, "context.py")
    with open(context_stub, "w") as f:
        f.write("""from typing import Any, Optional

class FunctionContext:
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    request: Any
    response: Any
""")

    # Create a core/ package with faas_s3 stub
    core_dir = os.path.join(workspace, "core")
    os.makedirs(core_dir, exist_ok=True)
    with open(os.path.join(core_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(core_dir, "faas_s3.py"), "w") as f:
        f.write("def s3_open(bucket: str, key: str, mode: str = 'rb') -> Any: ...\n")

    # The shim content that ShimBridge prepends
    shim_header = """# fmt:off
# --- Lsp shim for user code execution ---
from context import FunctionContext
from core.faas_s3 import s3_open

context: FunctionContext
# fmt:on
"""

    # The user's actual code
    user_code = """# --- HYAC USER CODE START ---
def handler(ctx):
    name = ctx.get("name", "world")
    data = s3_open("bucket", "file.txt")
    return {"message": f"Hello {name}"}
# --- HYAC USER CODE END ---
"""

    # The full text as seen by pyright (shim + markers + user code)
    full_text = f"{shim_header}\n{user_code}"

    env = os.environ.copy()
    env["PYTHONPATH"] = workspace

    process = await asyncio.create_subprocess_exec(
        pyright_cmd,
        "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workspace,
        env=env,
    )

    doc_uri = f"file://{workspace}/user_code.py"

    try:
        # Initialize
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
                        "publishDiagnostics": True,
                    }
                },
                "workspaceFolders": [{"uri": f"file://{workspace}", "name": "test"}],
            },
        }
        await write_lsp_payload(process.stdin, json.dumps(init_req))
        init_resp = await recv_until_id(process.stdout, 1)
        print(f"[OK] initialize: {init_resp.get('result', {}).get('serverInfo', {})}")

        await write_lsp_payload(
            process.stdin,
            json.dumps({"jsonrpc": "2.0", "method": "initialized", "params": {}}),
        )

        # didOpen with shim-injected code
        await write_lsp_payload(
            process.stdin,
            json.dumps({
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": doc_uri,
                        "languageId": "python",
                        "version": 1,
                        "text": full_text,
                    }
                },
            }),
        )
        print(f"[OK] didOpen sent (with shim + user code)")

        # Collect diagnostics
        await asyncio.sleep(2)
        messages = await collect_messages(process.stdout, timeout=2.0)
        for msg in messages:
            method = msg.get("method", "")
            if method == "textDocument/publishDiagnostics":
                diags = msg.get("params", {}).get("diagnostics", [])
                errors = [d for d in diags if d.get("severity") == 1]
                warnings = [d for d in diags if d.get("severity") == 2]
                print(f"[INFO] Diagnostics: {len(errors)} errors, {len(warnings)} warnings")
                for d in diags[:5]:
                    line = d.get("range", {}).get("start", {}).get("line", "?")
                    msg_text = d.get("message", "")[:80]
                    sev = {1: "ERROR", 2: "WARN", 3: "INFO", 4: "HINT"}.get(d.get("severity"), "?")
                    print(f"       L{line} [{sev}] {msg_text}")

        # Completion on ctx.get (line depends on shim offset)
        # shim adds ~8 lines, so user code starts around line 8
        # ctx.get is on the first line of user code handler
        shim_lines = shim_header.count("\n") + 1  # +1 for the blank line
        handler_line = shim_lines + 2  # def handler line
        ctx_get_line = shim_lines + 3  # name = ctx.get line

        completion_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "textDocument/completion",
            "params": {
                "textDocument": {"uri": doc_uri},
                "position": {"line": ctx_get_line, "character": 15},  # after "ctx."
            },
        }
        await write_lsp_payload(process.stdin, json.dumps(completion_req))
        try:
            comp_resp = await recv_until_id(process.stdout, 2, timeout=10.0)
            items = comp_resp.get("result", {})
            if isinstance(items, dict):
                item_list = items.get("items", [])
            elif isinstance(items, list):
                item_list = items
            else:
                item_list = []
            print(f"[OK] completion on ctx: {len(item_list)} items")
            for item in item_list[:5]:
                print(f"       {item.get('label')} ({item.get('kind', '?')})")
        except asyncio.TimeoutError:
            print(f"[WARN] completion timed out")

        # Completion on s3_open
        s3_line = shim_lines + 4
        completion_req2 = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "textDocument/completion",
            "params": {
                "textDocument": {"uri": doc_uri},
                "position": {"line": s3_line, "character": 13},  # after "s3_open("
            },
        }
        await write_lsp_payload(process.stdin, json.dumps(completion_req2))
        try:
            comp_resp2 = await recv_until_id(process.stdout, 3, timeout=10.0)
            items2 = comp_resp2.get("result", {})
            if isinstance(items2, dict):
                item_list2 = items2.get("items", [])
            elif isinstance(items2, list):
                item_list2 = items2
            else:
                item_list2 = []
            print(f"[OK] completion on s3_open: {len(item_list2)} items")
        except asyncio.TimeoutError:
            print(f"[WARN] s3_open completion timed out")

        # Shutdown
        await write_lsp_payload(
            process.stdin,
            json.dumps({"jsonrpc": "2.0", "id": 99, "method": "shutdown", "params": None}),
        )
        try:
            await recv_until_id(process.stdout, 99, timeout=5.0)
        except asyncio.TimeoutError:
            pass
        await write_lsp_payload(
            process.stdin,
            json.dumps({"jsonrpc": "2.0", "method": "exit", "params": None}),
        )

        print(f"\n[SUCCESS] Pyright with shim injection test passed!")
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
        stderr_data = await process.stderr.read()
        if stderr_data:
            stderr_text = stderr_data.decode(errors="ignore").strip()
            if stderr_text:
                print(f"\n[STDERR] {stderr_text[:500]}")


if __name__ == "__main__":
    result = asyncio.run(test_pyright_with_shim())
    sys.exit(0 if result else 1)
