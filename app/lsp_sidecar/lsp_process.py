import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path


CONTENT_LENGTH_PATTERN = re.compile(rb"Content-Length: (\d+)\r\n")


@dataclass
class LspProcess:
    process: asyncio.subprocess.Process
    workspace: str

    @property
    def alive(self) -> bool:
        return self.process.returncode is None

    async def terminate(self) -> None:
        if self.process.returncode is not None:
            return
        self.process.terminate()
        await self.process.wait()


async def spawn_pyright(workspace: str) -> LspProcess:
    workspace_path = Path(workspace).resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    python_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{workspace_path}:{python_path}" if python_path else str(workspace_path)
    )
    process = await asyncio.create_subprocess_exec(
        "pyright-langserver",
        "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(workspace_path),
        env=env,
    )
    return LspProcess(process=process, workspace=str(workspace_path))


async def read_lsp_payload(stdout: asyncio.StreamReader) -> str:
    header_buffer = b""
    while True:
        line = await stdout.readline()
        if not line:
            raise asyncio.IncompleteReadError(partial=header_buffer, expected=1)
        header_buffer += line
        if b"\r\n\r\n" in header_buffer:
            break

    match = CONTENT_LENGTH_PATTERN.search(header_buffer)
    if not match:
        return ""

    content_length = int(match.group(1))
    body_start_index = header_buffer.find(b"\r\n\r\n") + 4
    buffer = header_buffer[body_start_index:]
    body = buffer
    remaining = content_length - len(body)
    if remaining > 0:
        body += await stdout.readexactly(remaining)

    return body.decode("utf-8", errors="ignore")


async def write_lsp_payload(stdin: asyncio.StreamWriter, payload: str) -> None:
    body = payload.encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    stdin.write(header + body)
    await stdin.drain()
