#!/usr/bin/env python3
"""Shared helpers for LSP smoke tests."""

from __future__ import annotations

import asyncio
import json
import re


async def write_lsp_payload(stdin, payload: str) -> None:
    body = payload.encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    stdin.write(header + body)
    await stdin.drain()


async def read_lsp_payload(stdout) -> str:
    header_buffer = b""
    while True:
        line = await stdout.readline()
        if not line:
            raise asyncio.IncompleteReadError(partial=header_buffer, expected=1)
        header_buffer += line
        if b"\r\n\r\n" in header_buffer:
            break
    match = re.search(rb"Content-Length: (\d+)\r\n", header_buffer)
    if not match:
        return ""
    content_length = int(match.group(1))
    body_start = header_buffer.find(b"\r\n\r\n") + 4
    buffer = header_buffer[body_start:]
    body = buffer
    remaining = content_length - len(body)
    if remaining > 0:
        body += await stdout.readexactly(remaining)
    return body.decode("utf-8", errors="ignore")


async def recv_until_id(stdout, req_id: int, timeout: float = 10.0) -> dict:
    while True:
        raw = await asyncio.wait_for(read_lsp_payload(stdout), timeout=timeout)
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("id") == req_id:
            return data
