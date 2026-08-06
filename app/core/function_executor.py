"""Hard per-invocation process, time, memory, and IPC boundaries for user code."""

from __future__ import annotations

import asyncio
import base64
import binascii
import ctypes
import errno
import inspect
import io
import json
import logging
import math
import multiprocessing
import os
import pickle
import resource
import signal
import stat
import struct
import sys
import time
import traceback
import weakref
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from types import SimpleNamespace
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from starlette.datastructures import Headers
from starlette.concurrency import iterate_in_threadpool
from starlette.responses import (
    FileResponse,
    MalformedRangeHeader,
    RangeNotSatisfiable,
    Response,
    StreamingResponse,
)


# The worker buffers responses because live iterators and files cannot safely cross a
# process boundary. Keep every buffer explicit and below the invocation memory floor.
MAX_REQUEST_BODY_BYTES = 4 * 1024 * 1024
MAX_RESULT_PAYLOAD_BYTES = 5 * 1024 * 1024
MAX_RESPONSE_BODY_BYTES = 4 * 1024 * 1024
MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_TRACEBACK_BYTES = 256 * 1024
MAX_IPC_PAYLOAD_BYTES = 32 * 1024 * 1024
LOG_TRUNCATION_MARKER = "\n[hyac log truncated at 2 MiB]"
INVOCATION_REQUEST_SNAPSHOT_KEY = "__hyac_request_snapshot__"
PROCESS_TREE_SNAPSHOT_INTERVAL_SECONDS = 0.025
PROCESS_TREE_DISCOVERY_TIMEOUT_SECONDS = 0.05
PROCESS_TREE_POLL_TIMEOUT_SECONDS = 0.05
MAX_PROCESS_TREE_FRAME_BYTES = 32 * 1024 * 1024
MAX_WORKER_WIRE_DEPTH = 100
MAX_WORKER_WIRE_NODES = 1_000_000
WORKER_RESULT_SCHEMA = "hyac-worker-result-v1"
_PR_SET_NO_NEW_PRIVS = 38
_SCMP_ACT_ALLOW = 0x7FFF0000
_SCMP_ACT_ERRNO = 0x00050000
_DENIED_CHILD_SYSCALLS = (
    # Keep the complete invocation tree in the worker-owned process group.
    "setsid",
    "setpgid",
    "unshare",
    "setns",
    # Do not let same-UID user code control or inspect the runtime/other workers.
    "kill",
    "tkill",
    "tgkill",
    "rt_sigqueueinfo",
    "rt_tgsigqueueinfo",
    "pidfd_send_signal",
    "ptrace",
    "process_vm_readv",
    "process_vm_writev",
    "process_madvise",
    "pidfd_getfd",
    "kcmp",
)
_PAGE_SIZE_BYTES = os.sysconf("SC_PAGE_SIZE")
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequestSnapshot:
    scope: dict[str, Any]
    body: bytes


@dataclass
class FunctionExecutionResult:
    value: Any
    stdout: str
    stderr: str


@dataclass(frozen=True)
class _ProcessIdentity:
    pid: int
    start_time: int


@dataclass(frozen=True)
class _ProcessStat:
    identity: _ProcessIdentity
    parent_pid: int
    process_group_id: int
    rss_bytes: int


@dataclass(frozen=True)
class _ProcessTreeSnapshot:
    children_by_parent: dict[int, tuple[_ProcessStat, ...]]
    processes_by_pid: dict[int, _ProcessStat]


class _SharedProcessTreeMonitor:
    """Coalesce procfs reads per event loop and keep blocking I/O off the loop."""

    def __init__(self) -> None:
        self._snapshot: _ProcessTreeSnapshot | None = None
        self._captured_at = 0.0
        self._refresh_task: asyncio.Task[_ProcessTreeSnapshot] | None = None
        self._process: multiprocessing.Process | None = None
        self._connection: Any | None = None
        self._users = 0
        self._generation = 0
        self._retired_shutdown_tasks: set[asyncio.Task[None]] = set()

    def acquire(self) -> None:
        self._users += 1
        if self._process is not None:
            return
        try:
            self._start_generation()
        except BaseException:
            self._users -= 1
            raise

    @property
    def generation(self) -> int:
        return self._generation

    def _start_generation(self) -> None:
        parent_connection = None
        child_connection = None
        try:
            process_context = multiprocessing.get_context("fork")
            parent_connection, child_connection = process_context.Pipe(duplex=True)
            process = process_context.Process(
                target=_process_tree_monitor_main,
                args=(child_connection,),
                name="hyac-process-tree-monitor",
                daemon=True,
            )
            process.start()
        except BaseException:
            if parent_connection is not None:
                parent_connection.close()
            if child_connection is not None:
                child_connection.close()
            raise
        child_connection.close()
        self._generation += 1
        self._process = process
        self._connection = parent_connection

    def _detach_generation(
        self,
    ) -> tuple[
        int,
        asyncio.Task[_ProcessTreeSnapshot] | None,
        Any | None,
        multiprocessing.Process | None,
    ]:
        detached = (
            self._generation,
            self._refresh_task,
            self._connection,
            self._process,
        )
        self._generation += 1
        self._process = None
        self._connection = None
        self._refresh_task = None
        self._snapshot = None
        self._captured_at = 0.0
        return detached

    def invalidate_generation(self, expected_generation: int) -> bool:
        """Detach one stuck generation without waiting on its process teardown."""
        if expected_generation != self._generation or self._process is None:
            return False
        generation, refresh_task, connection, process = self._detach_generation()
        shutdown_task = asyncio.create_task(
            self._shutdown_generation(
                generation,
                refresh_task,
                connection,
                process,
            )
        )
        self._retired_shutdown_tasks.add(shutdown_task)

        def consume_shutdown_result(task: asyncio.Task[None]) -> None:
            self._retired_shutdown_tasks.discard(task)
            if task.cancelled():
                return
            error = task.exception()
            if error is not None:
                _LOGGER.warning(
                    "Retired process-tree monitor generation failed to stop: %s",
                    error,
                )

        shutdown_task.add_done_callback(consume_shutdown_result)
        if self._users > 0:
            try:
                self._start_generation()
            except BaseException as exc:
                _LOGGER.warning(
                    "Failed to restart process-tree monitor generation: %s",
                    exc,
                )
        return True

    async def snapshot(self, *, force: bool = False) -> _ProcessTreeSnapshot:
        now = time.monotonic()
        if (
            not force
            and self._snapshot is not None
            and now - self._captured_at < PROCESS_TREE_SNAPSHOT_INTERVAL_SECONDS
        ):
            return self._snapshot

        if self._refresh_task is None:
            self._refresh_task = asyncio.create_task(
                self._refresh(self._generation, self._connection)
            )
        try:
            return await asyncio.shield(self._refresh_task)
        except asyncio.CancelledError:
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelling():
                raise
            raise RuntimeError("Process-tree monitor generation was invalidated")

    async def _refresh(
        self,
        generation: int,
        connection,
    ) -> _ProcessTreeSnapshot:
        if connection is None:
            raise RuntimeError("Process-tree monitor is not running")
        loop = asyncio.get_running_loop()
        readable: asyncio.Future[None] | None = None
        reader_fd: int | None = None
        current_task = asyncio.current_task()

        def mark_readable() -> None:
            if readable is not None and not readable.done():
                readable.set_result(None)

        try:
            connection.send_bytes(b"snapshot")
            reader_fd = connection.fileno()
            os.set_blocking(reader_fd, False)
            loop.add_reader(reader_fd, mark_readable)
            frame_buffer = bytearray()
            frame_size: int | None = None
            payload_offset = 4
            while True:
                try:
                    chunk = os.read(reader_fd, 64 * 1024)
                except BlockingIOError:
                    readable = loop.create_future()
                    await readable
                    readable = None
                    continue
                if not chunk:
                    raise EOFError("Process-tree monitor closed an incomplete frame")
                frame_buffer.extend(chunk)

                if frame_size is None and len(frame_buffer) >= 4:
                    frame_size = struct.unpack_from("!i", frame_buffer)[0]
                    if frame_size == -1:
                        if len(frame_buffer) < 12:
                            frame_size = None
                            continue
                        frame_size = struct.unpack_from("!Q", frame_buffer, 4)[0]
                        payload_offset = 12
                    elif frame_size < 0:
                        raise RuntimeError(
                            f"Invalid process-tree monitor frame length {frame_size}"
                        )
                    if frame_size > MAX_PROCESS_TREE_FRAME_BYTES:
                        raise RuntimeError(
                            "Process-tree monitor frame exceeds "
                            f"the {MAX_PROCESS_TREE_FRAME_BYTES}-byte limit"
                        )

                if (
                    frame_size is not None
                    and len(frame_buffer) >= payload_offset + frame_size
                ):
                    frame_end = payload_offset + frame_size
                    if len(frame_buffer) != frame_end:
                        raise RuntimeError(
                            "Process-tree monitor sent unexpected trailing frame data"
                        )
                    serialized = bytes(frame_buffer[payload_offset:frame_end])
                    break

            ok, value = pickle.loads(serialized)
            if not ok:
                raise RuntimeError(f"Process-tree monitor failed: {value}")
            if generation != self._generation or connection is not self._connection:
                raise RuntimeError("Discarded stale process-tree monitor snapshot")
            snapshot = value
            self._snapshot = snapshot
            self._captured_at = time.monotonic()
            return snapshot
        finally:
            if reader_fd is not None:
                loop.remove_reader(reader_fd)
            if (
                generation == self._generation
                and self._refresh_task is current_task
            ):
                self._refresh_task = None

    async def release(self) -> None:
        self._users -= 1
        if self._users > 0:
            return

        generation, refresh_task, connection, process = self._detach_generation()
        current_shutdown = asyncio.create_task(
            self._shutdown_generation(
                generation,
                refresh_task,
                connection,
                process,
            )
        )
        pending_shutdowns = [
            *self._retired_shutdown_tasks,
            current_shutdown,
        ]
        shutdown_task = asyncio.create_task(
            self._await_shutdown_tasks(pending_shutdowns)
        )
        cancellation: asyncio.CancelledError | None = None
        current_task = asyncio.current_task()
        while not shutdown_task.done():
            try:
                await asyncio.shield(shutdown_task)
            except asyncio.CancelledError as exc:
                cancellation = cancellation or exc
                if current_task is not None:
                    current_task.uncancel()
        await shutdown_task
        self._retired_shutdown_tasks.difference_update(pending_shutdowns)
        if cancellation is not None:
            raise cancellation

    async def _await_shutdown_tasks(
        self,
        shutdown_tasks: list[asyncio.Task[None]],
    ) -> None:
        results = await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(
                result,
                asyncio.CancelledError,
            ):
                _LOGGER.warning(
                    "Process-tree monitor shutdown failed: %s",
                    result,
                )

    async def _shutdown_generation(
        self,
        generation: int,
        refresh_task: asyncio.Task[_ProcessTreeSnapshot] | None,
        connection,
        process: multiprocessing.Process | None,
    ) -> None:
        refresh_was_active = refresh_task is not None and not refresh_task.done()
        if refresh_was_active:
            refresh_task.cancel()
        if refresh_task is not None:
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass
            except BaseException as exc:
                _LOGGER.warning(
                    "Process-tree monitor generation %s refresh failed during shutdown: %s",
                    generation,
                    exc,
                )

        if connection is not None:
            try:
                connection.send_bytes(b"stop")
            except (BrokenPipeError, OSError):
                pass
            connection.close()
        if process is None:
            return

        if refresh_was_active and process.is_alive():
            process.terminate()
        deadline = time.monotonic() + 0.25
        while process.is_alive() and time.monotonic() < deadline:
            await asyncio.sleep(0.005)
        if process.is_alive():
            process.terminate()
            terminate_deadline = time.monotonic() + 0.25
            while process.is_alive() and time.monotonic() < terminate_deadline:
                await asyncio.sleep(0.005)
        if process.is_alive():
            process.kill()
            kill_deadline = time.monotonic() + 0.25
            while process.is_alive() and time.monotonic() < kill_deadline:
                await asyncio.sleep(0.005)
        process.join(timeout=0)


_PROCESS_TREE_MONITORS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    _SharedProcessTreeMonitor,
] = weakref.WeakKeyDictionary()


class RequestBodyTooLarge(ValueError):
    pass


class FunctionResultTooLarge(ValueError):
    pass


class FunctionExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str = "RuntimeError",
        stdout: str = "",
        stderr: str = "",
        traceback_text: str = "",
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.stdout = stdout
        self.stderr = stderr
        self.traceback_text = traceback_text


class _InvalidWorkerPayload(ValueError):
    pass


def _encode_worker_wire_node(
    value: Any,
    *,
    depth: int = 0,
    node_count: list[int] | None = None,
) -> list[Any]:
    if depth > MAX_WORKER_WIRE_DEPTH:
        raise ValueError("Worker payload nesting is too deep")
    if node_count is None:
        node_count = [0]
    node_count[0] += 1
    if node_count[0] > MAX_WORKER_WIRE_NODES:
        raise ValueError("Worker payload contains too many values")

    if value is None:
        return ["n"]
    if isinstance(value, bool):
        return ["b", value]
    if isinstance(value, int):
        return ["i", value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Worker payload contains a non-finite number")
        return ["f", value]
    if isinstance(value, str):
        return ["s", value]
    if isinstance(value, bytes):
        return ["y", base64.b64encode(value).decode("ascii")]
    if isinstance(value, (list, tuple)):
        return [
            "l",
            [
                _encode_worker_wire_node(
                    item,
                    depth=depth + 1,
                    node_count=node_count,
                )
                for item in value
            ],
        ]
    if isinstance(value, dict):
        entries = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Worker payload object keys must be strings")
            entries.append(
                [
                    key,
                    _encode_worker_wire_node(
                        item,
                        depth=depth + 1,
                        node_count=node_count,
                    ),
                ]
            )
        return ["d", entries]
    raise TypeError(f"Unsupported worker payload type: {type(value).__name__}")


def _decode_worker_wire_node(
    node: Any,
    *,
    depth: int = 0,
    node_count: list[int] | None = None,
) -> Any:
    if depth > MAX_WORKER_WIRE_DEPTH:
        raise _InvalidWorkerPayload("Worker payload nesting is too deep")
    if node_count is None:
        node_count = [0]
    node_count[0] += 1
    if node_count[0] > MAX_WORKER_WIRE_NODES:
        raise _InvalidWorkerPayload("Worker payload contains too many values")
    if not isinstance(node, list) or not node or not isinstance(node[0], str):
        raise _InvalidWorkerPayload("Worker payload contains an invalid data node")

    tag = node[0]
    if tag == "n":
        if len(node) != 1:
            raise _InvalidWorkerPayload("Invalid null data node")
        return None
    if len(node) != 2:
        raise _InvalidWorkerPayload("Invalid worker data node length")
    value = node[1]
    if tag == "b":
        if not isinstance(value, bool):
            raise _InvalidWorkerPayload("Invalid boolean data node")
        return value
    if tag == "i":
        if not isinstance(value, int) or isinstance(value, bool):
            raise _InvalidWorkerPayload("Invalid integer data node")
        return value
    if tag == "f":
        if not isinstance(value, float) or not math.isfinite(value):
            raise _InvalidWorkerPayload("Invalid floating-point data node")
        return value
    if tag == "s":
        if not isinstance(value, str):
            raise _InvalidWorkerPayload("Invalid string data node")
        return value
    if tag == "y":
        if not isinstance(value, str):
            raise _InvalidWorkerPayload("Invalid byte data node")
        try:
            return base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise _InvalidWorkerPayload("Invalid base64 byte data node") from exc
    if tag == "l":
        if not isinstance(value, list):
            raise _InvalidWorkerPayload("Invalid list data node")
        return [
            _decode_worker_wire_node(
                item,
                depth=depth + 1,
                node_count=node_count,
            )
            for item in value
        ]
    if tag == "d":
        if not isinstance(value, list):
            raise _InvalidWorkerPayload("Invalid object data node")
        decoded: dict[str, Any] = {}
        for entry in value:
            if (
                not isinstance(entry, list)
                or len(entry) != 2
                or not isinstance(entry[0], str)
                or entry[0] in decoded
            ):
                raise _InvalidWorkerPayload("Invalid object entry")
            decoded[entry[0]] = _decode_worker_wire_node(
                entry[1],
                depth=depth + 1,
                node_count=node_count,
            )
        return decoded
    raise _InvalidWorkerPayload(f"Unknown worker data node tag {tag!r}")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidWorkerPayload(f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def _serialize_worker_payload(payload: dict[str, Any]) -> bytes:
    envelope = {
        "schema": WORKER_RESULT_SCHEMA,
        "payload": _encode_worker_wire_node(payload),
    }
    return json.dumps(
        envelope,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_bounded_text(value: Any, name: str, max_bytes: int) -> None:
    if not isinstance(value, str) or len(value.encode("utf-8")) > max_bytes:
        raise _InvalidWorkerPayload(f"Invalid {name}")


def _validate_encoded_result(result: Any) -> None:
    if not isinstance(result, dict) or not isinstance(result.get("kind"), str):
        raise _InvalidWorkerPayload("Invalid encoded function result")
    if result["kind"] == "value":
        if set(result) != {"kind", "value"}:
            raise _InvalidWorkerPayload("Invalid value result schema")
        return
    if result["kind"] != "response" or set(result) != {
        "kind",
        "body",
        "status_code",
        "raw_headers",
    }:
        raise _InvalidWorkerPayload("Invalid response result schema")
    if not isinstance(result["body"], bytes) or len(
        result["body"]
    ) > MAX_RESPONSE_BODY_BYTES:
        raise _InvalidWorkerPayload("Invalid response body")
    if not isinstance(result["status_code"], int) or isinstance(
        result["status_code"], bool
    ):
        raise _InvalidWorkerPayload("Invalid response status code")
    raw_headers = result["raw_headers"]
    if not isinstance(raw_headers, list):
        raise _InvalidWorkerPayload("Invalid response headers")
    normalized_headers: list[tuple[bytes, bytes]] = []
    for header in raw_headers:
        if (
            not isinstance(header, list)
            or len(header) != 2
            or not isinstance(header[0], bytes)
            or not isinstance(header[1], bytes)
        ):
            raise _InvalidWorkerPayload("Invalid raw response header")
        normalized_headers.append((header[0], header[1]))
    result["raw_headers"] = normalized_headers


def _validate_remote_exception(remote: Any) -> None:
    if remote is None:
        return
    if not isinstance(remote, dict) or not isinstance(remote.get("kind"), str):
        raise _InvalidWorkerPayload("Invalid remote exception")
    if remote["kind"] == "api":
        if set(remote) != {"kind", "code", "msg"}:
            raise _InvalidWorkerPayload("Invalid API exception schema")
        if not isinstance(remote["code"], int) or isinstance(remote["code"], bool):
            raise _InvalidWorkerPayload("Invalid API exception code")
        if remote["msg"] is not None and not isinstance(remote["msg"], str):
            raise _InvalidWorkerPayload("Invalid API exception message")
        return
    if remote["kind"] == "http":
        if set(remote) != {"kind", "status_code", "detail", "headers"}:
            raise _InvalidWorkerPayload("Invalid HTTP exception schema")
        if not isinstance(remote["status_code"], int) or isinstance(
            remote["status_code"], bool
        ):
            raise _InvalidWorkerPayload("Invalid HTTP exception status code")
        headers = remote["headers"]
        if headers is not None and (
            not isinstance(headers, dict)
            or any(
                not isinstance(name, str) or not isinstance(value, str)
                for name, value in headers.items()
            )
        ):
            raise _InvalidWorkerPayload("Invalid HTTP exception headers")
        return
    raise _InvalidWorkerPayload("Invalid remote exception kind")


def _validate_worker_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
        raise _InvalidWorkerPayload("Invalid worker result schema")
    for name in ("stdout", "stderr"):
        _validate_bounded_text(payload.get(name), name, MAX_LOG_BYTES)
    if payload["ok"]:
        if set(payload) != {"ok", "result", "stdout", "stderr"}:
            raise _InvalidWorkerPayload("Invalid successful worker result schema")
        _validate_encoded_result(payload["result"])
        return payload
    if set(payload) != {
        "ok",
        "message",
        "error_type",
        "remote_exception",
        "traceback",
        "stdout",
        "stderr",
    }:
        raise _InvalidWorkerPayload("Invalid failed worker result schema")
    _validate_bounded_text(payload["message"], "error message", 64 * 1024)
    _validate_bounded_text(payload["error_type"], "error type", 1024)
    _validate_bounded_text(payload["traceback"], "traceback", MAX_TRACEBACK_BYTES)
    _validate_remote_exception(payload["remote_exception"])
    return payload


def _decode_worker_payload(serialized: bytes) -> dict[str, Any]:
    try:
        envelope = json.loads(
            serialized.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
        if not isinstance(envelope, dict) or set(envelope) != {"schema", "payload"}:
            raise _InvalidWorkerPayload("Invalid worker result envelope")
        if envelope["schema"] != WORKER_RESULT_SCHEMA:
            raise _InvalidWorkerPayload("Unsupported worker result schema")
        payload = _decode_worker_wire_node(envelope["payload"])
        return _validate_worker_payload(payload)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _InvalidWorkerPayload,
        RecursionError,
        ValueError,
    ) as exc:
        raise FunctionExecutionError(
            "Function worker returned an invalid data frame",
            error_type="InvalidWorkerPayload",
        ) from exc


async def _receive_worker_payload(
    receive_connection,
    *,
    deadline: float,
) -> dict[str, Any]:
    """Incrementally drain one multiprocessing frame without blocking the loop."""
    loop = asyncio.get_running_loop()
    reader_fd = receive_connection.fileno()
    readable: asyncio.Future[None] | None = None
    frame_buffer = bytearray()
    frame_size: int | None = None
    payload_offset = 4

    def mark_readable() -> None:
        if readable is not None and not readable.done():
            readable.set_result(None)

    try:
        os.set_blocking(reader_fd, False)
        loop.add_reader(reader_fd, mark_readable)
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError
            try:
                chunk = os.read(reader_fd, 64 * 1024)
            except BlockingIOError:
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    raise TimeoutError
                readable = loop.create_future()
                try:
                    await asyncio.wait_for(readable, timeout=remaining_seconds)
                finally:
                    readable = None
                continue
            except OSError as exc:
                raise FunctionExecutionError(
                    "Function worker returned an invalid data frame",
                    error_type="InvalidWorkerPayload",
                ) from exc

            if not chunk:
                raise FunctionExecutionError(
                    "Function worker closed an incomplete data frame",
                    error_type="InvalidWorkerPayload",
                )
            frame_buffer.extend(chunk)

            if frame_size is None and len(frame_buffer) >= 4:
                frame_size = struct.unpack_from("!i", frame_buffer)[0]
                if frame_size == -1:
                    if len(frame_buffer) < 12:
                        frame_size = None
                        continue
                    frame_size = struct.unpack_from("!Q", frame_buffer, 4)[0]
                    payload_offset = 12
                elif frame_size < 0:
                    raise FunctionExecutionError(
                        f"Function worker returned invalid frame length {frame_size}",
                        error_type="InvalidWorkerPayload",
                    )
                if frame_size > MAX_IPC_PAYLOAD_BYTES:
                    raise FunctionExecutionError(
                        "Function worker returned a data frame exceeding "
                        f"the {MAX_IPC_PAYLOAD_BYTES}-byte limit",
                        error_type="InvalidWorkerPayload",
                    )

            if frame_size is None:
                continue
            frame_end = payload_offset + frame_size
            if len(frame_buffer) < frame_end:
                continue
            if len(frame_buffer) != frame_end:
                raise FunctionExecutionError(
                    "Function worker returned unexpected trailing frame data",
                    error_type="InvalidWorkerPayload",
                )
            payload = _decode_worker_payload(
                bytes(frame_buffer[payload_offset:frame_end])
            )
            if time.monotonic() >= deadline:
                raise TimeoutError
            return payload
    finally:
        loop.remove_reader(reader_fd)


class _BoundedTextCapture(io.TextIOBase):
    """UTF-8 text sink that never retains more than ``limit`` bytes."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._buffer = bytearray()
        self._truncated = False

    @property
    def encoding(self) -> str:
        return "utf-8"

    @property
    def buffer(self) -> _BoundedTextCapture:
        return self

    def writable(self) -> bool:
        return True

    def write(self, value: str | bytes) -> int:
        data = value if isinstance(value, bytes) else value.encode("utf-8", "replace")
        original_length = len(value)
        if self._truncated:
            return original_length

        marker = LOG_TRUNCATION_MARKER.encode("utf-8")
        remaining = self._limit - len(self._buffer)
        if len(data) <= remaining:
            self._buffer.extend(data)
            return original_length

        content_space = max(0, remaining - len(marker))
        self._buffer.extend(data[:content_space])
        self._buffer.extend(marker[: self._limit - len(self._buffer)])
        self._truncated = True
        return original_length

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        # Ignore an incomplete final code point so re-encoding cannot exceed the
        # byte budget due to a three-byte replacement character.
        return bytes(self._buffer).decode("utf-8", "ignore")


async def snapshot_request(request: Request) -> RequestSnapshot:
    """Consume a bounded body in the parent and retain only safe ASGI request data."""
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BODY_BYTES:
            raise RequestBodyTooLarge(
                f"Request body exceeds the {MAX_REQUEST_BODY_BYTES}-byte limit"
            )
        body.extend(chunk)
    body_bytes = bytes(body)
    # Preserve normal parent-side request.json()/form()/body() behavior after the
    # stream has been consumed to create the immutable worker snapshot.
    request._body = body_bytes

    source_scope = request.scope
    scope = {
        "type": "http",
        "asgi": dict(source_scope.get("asgi") or {"version": "3.0"}),
        "http_version": source_scope.get("http_version", "1.1"),
        "method": source_scope.get("method", "GET"),
        "scheme": source_scope.get("scheme", "http"),
        "path": source_scope.get("path", "/"),
        "raw_path": bytes(source_scope.get("raw_path", b"/")),
        "root_path": source_scope.get("root_path", ""),
        "query_string": bytes(source_scope.get("query_string", b"")),
        "headers": [(bytes(name), bytes(value)) for name, value in source_scope.get("headers", [])],
        "client": source_scope.get("client"),
        "server": source_scope.get("server"),
        "path_params": dict(source_scope.get("path_params", {})),
    }
    return RequestSnapshot(scope=scope, body=body_bytes)


def _restore_request(snapshot: RequestSnapshot) -> Request:
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {
            "type": "http.request",
            "body": snapshot.body,
            "more_body": False,
        }

    return Request(dict(snapshot.scope), receive)


def _restore_handler_requests(handler_args: dict[str, Any]) -> dict[str, Any]:
    return {
        name: _restore_request(value) if isinstance(value, RequestSnapshot) else value
        for name, value in handler_args.items()
    }


def _current_virtual_memory_bytes() -> int:
    """Return this worker's inherited virtual-memory baseline on Linux."""
    statm_fields = Path("/proc/self/statm").read_text(encoding="utf-8").split()
    if not statm_fields:
        raise RuntimeError("Unable to determine the invocation memory baseline")
    return int(statm_fields[0]) * os.sysconf("SC_PAGE_SIZE")


def _set_resource_limits(memory_limit_mb: int, timeout_seconds: int) -> None:
    memory_bytes = memory_limit_mb * 1024 * 1024
    # The disposable worker is forked from the fully initialized ASGI runtime. Its
    # inherited interpreter, libraries, and thread stacks can already exceed a
    # function's declared budget. Capping RLIMIT_AS at the budget alone therefore
    # prevents even tiny legitimate allocations. Treat the declared value as the
    # invocation's additional address-space allowance above that immutable baseline.
    address_space_limit = _current_virtual_memory_bytes() + memory_bytes
    _soft_limit, inherited_hard_limit = resource.getrlimit(resource.RLIMIT_AS)
    if inherited_hard_limit != resource.RLIM_INFINITY:
        address_space_limit = min(address_space_limit, inherited_hard_limit)
    resource.setrlimit(
        resource.RLIMIT_AS,
        (address_space_limit, address_space_limit),
    )
    cpu_seconds = max(1, math.ceil(timeout_seconds))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))


def _serialized_size(value: Any) -> int:
    return len(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))


def _ensure_result_size(value: Any) -> None:
    size = _serialized_size(value)
    if size > MAX_RESULT_PAYLOAD_BYTES:
        raise FunctionResultTooLarge(
            f"Function result exceeds the {MAX_RESULT_PAYLOAD_BYTES}-byte limit"
        )


def _append_response_chunk(buffer: bytearray, chunk: str | bytes) -> None:
    data = chunk.encode("utf-8") if isinstance(chunk, str) else bytes(chunk)
    if len(buffer) + len(data) > MAX_RESPONSE_BODY_BYTES:
        raise FunctionResultTooLarge(
            f"Response body exceeds the {MAX_RESPONSE_BODY_BYTES}-byte limit"
        )
    buffer.extend(data)


async def _response_body(result: Response) -> bytes:
    if isinstance(result, StreamingResponse):
        body = bytearray()
        body_iterator = result.body_iterator
        if (
            inspect.isasyncgen(body_iterator)
            and body_iterator.ag_code is iterate_in_threadpool.__code__
            and body_iterator.ag_frame is not None
        ):
            # Starlette wraps synchronous iterators in AnyIO's thread pool. A forked
            # worker cannot reuse the parent's threads, and this process is already
            # dedicated to one invocation, so drain the original iterator directly.
            iterator = body_iterator.ag_frame.f_locals["iterator"]
            for chunk in iterator:
                _append_response_chunk(body, chunk)
            await body_iterator.aclose()
        else:
            async for chunk in body_iterator:
                _append_response_chunk(body, chunk)
        return bytes(body)

    body = bytes(getattr(result, "body", b""))
    if len(body) > MAX_RESPONSE_BODY_BYTES:
        raise FunctionResultTooLarge(
            f"Response body exceeds the {MAX_RESPONSE_BODY_BYTES}-byte limit"
        )
    return body


def _bounded_file_read(
    path: str | os.PathLike[str],
    start: int,
    length: int,
    *,
    require_eof: bool = False,
) -> bytes:
    if length > MAX_RESPONSE_BODY_BYTES:
        raise FunctionResultTooLarge(
            f"Response body exceeds the {MAX_RESPONSE_BODY_BYTES}-byte limit"
        )
    with Path(path).open("rb") as response_file:
        response_file.seek(start)
        data = response_file.read(length + 1 if require_eof else length)
    if (require_eof and len(data) > length) or len(data) > MAX_RESPONSE_BODY_BYTES:
        raise FunctionResultTooLarge(
            f"Response body exceeds the {MAX_RESPONSE_BODY_BYTES}-byte limit"
        )
    return data


def _file_response_payload(
    result: FileResponse,
    request_scope: dict[str, Any] | None,
) -> dict[str, Any]:
    stat_result = result.stat_result or os.stat(result.path)
    if not stat.S_ISREG(stat_result.st_mode):
        raise RuntimeError(f"File at path {result.path} is not a file.")
    result.stat_result = stat_result
    result.set_stat_headers(stat_result)

    scope = dict(request_scope or {})
    method = str(scope.get("method", "GET")).upper()
    headers = Headers(raw=list(scope.get("headers", [])))
    http_range = headers.get("range")
    http_if_range = headers.get("if-range")
    send_header_only = method == "HEAD"

    if http_range is None or (
        http_if_range is not None and not result._should_use_range(http_if_range)
    ):
        body = (
            b""
            if send_header_only
            else _bounded_file_read(
                result.path,
                0,
                stat_result.st_size,
                require_eof=True,
            )
        )
        return {
            "kind": "response",
            "body": body,
            "status_code": result.status_code,
            "raw_headers": list(result.raw_headers),
        }

    try:
        ranges = result._parse_range_header(http_range, stat_result.st_size)
    except MalformedRangeHeader as exc:
        response = Response(exc.content, status_code=400, media_type="text/plain")
        return {
            "kind": "response",
            "body": response.body,
            "status_code": response.status_code,
            "raw_headers": list(response.raw_headers),
        }
    except RangeNotSatisfiable as exc:
        response = Response(
            b"",
            status_code=416,
            headers={"Content-Range": f"*/{exc.max_size}"},
        )
        return {
            "kind": "response",
            "body": response.body,
            "status_code": response.status_code,
            "raw_headers": list(response.raw_headers),
        }

    if len(ranges) != 1:
        boundary = token_hex(13)
        content_length, header_generator = result.generate_multipart(
            ranges,
            boundary,
            stat_result.st_size,
            result.headers["content-type"],
        )
        if content_length > MAX_RESPONSE_BODY_BYTES:
            raise FunctionResultTooLarge(
                f"Response body exceeds the {MAX_RESPONSE_BODY_BYTES}-byte limit"
            )
        result.headers["content-range"] = (
            f"multipart/byteranges; boundary={boundary}"
        )
        result.headers["content-length"] = str(content_length)
        body = bytearray()
        if not send_header_only:
            for range_start, range_end in ranges:
                _append_response_chunk(
                    body,
                    header_generator(range_start, range_end),
                )
                _append_response_chunk(
                    body,
                    _bounded_file_read(
                        result.path,
                        range_start,
                        range_end - range_start,
                    ),
                )
                _append_response_chunk(body, b"\n")
            _append_response_chunk(body, f"--{boundary}--\n")
        return {
            "kind": "response",
            "body": bytes(body),
            "status_code": 206,
            "raw_headers": list(result.raw_headers),
        }

    start, end = ranges[0]
    result.headers["content-range"] = f"bytes {start}-{end - 1}/{stat_result.st_size}"
    result.headers["content-length"] = str(end - start)
    body = b"" if send_header_only else _bounded_file_read(result.path, start, end - start)
    return {
        "kind": "response",
        "body": body,
        "status_code": 206,
        "raw_headers": list(result.raw_headers),
    }


async def _run_response_background(background: Any) -> None:
    try:
        await _run_background(background)
    except Exception as exc:
        print(
            f"[hyac background task failed: {type(exc).__name__}]",
            file=sys.stderr,
        )
        print("Traceback (most recent call last):", file=sys.stderr)
        for frame in traceback.extract_tb(exc.__traceback__):
            print(
                f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}',
                file=sys.stderr,
            )
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)


async def _encode_result(
    result: Any,
    request_scope: dict[str, Any] | None = None,
    additional_background: Any = None,
) -> dict[str, Any]:
    if isinstance(result, Response):
        if isinstance(result, FileResponse):
            encoded = _file_response_payload(result, request_scope)
        else:
            body = await _response_body(result)
            encoded = {
                "kind": "response",
                "body": body,
                "status_code": result.status_code,
                # raw_headers retains duplicate Set-Cookie values and original bytes.
                "raw_headers": list(result.raw_headers),
            }
        _ensure_result_size(encoded)
        if additional_background is not None:
            await _run_response_background(additional_background)
        if result.background is not None:
            # Background failures are recorded inside the isolated worker but do not
            # replace an already-buffered successful response.
            await _run_response_background(result.background)
            result.background = None
        return encoded

    encoded = {
        "kind": "value",
        "value": jsonable_encoder(result, custom_encoder={ObjectId: str}),
    }
    _ensure_result_size(encoded)
    if additional_background is not None:
        await _run_response_background(additional_background)
    return encoded


def _decode_result(payload: dict[str, Any]) -> Any:
    if payload["kind"] == "response":
        response = Response(
            content=payload["body"],
            status_code=payload["status_code"],
        )
        response.raw_headers = list(payload["raw_headers"])
        # Response.background is deliberately completed inside the isolated worker.
        response.background = None
        return response
    return payload["value"]


async def _refresh_child_context(handler_args: dict[str, Any]):
    """Replace inherited database clients with connections created after fork."""
    context = handler_args.get("ctx")
    if context is None:
        return None, None

    from pymongo import AsyncMongoClient, MongoClient

    from core.config import settings

    if not settings.APP_DB_USERNAME or not settings.APP_DB_PASSWORD:
        raise RuntimeError("Application database identity is not configured")
    mongo_uri = (
        f"mongodb://{settings.APP_DB_USERNAME}:{settings.APP_DB_PASSWORD}"
        f"@mongodb:27017/{context.app_id}?authSource=admin&replicaSet=rs0"
    )
    sync_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    async_client = AsyncMongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    context.pymongo_db = sync_client[context.app_id]
    context.async_db = async_client[context.app_id]
    common_modules = {}
    for name, source in vars(context.common).items():
        namespace = _compile_source(source)
        common_modules[name] = SimpleNamespace(**namespace)
    context.common = SimpleNamespace(**common_modules)
    return sync_client, async_client


def _compile_source(source: str) -> dict[str, Any]:
    from core.faas_s3 import s3_open

    namespace = {"s3_open": s3_open}
    exec(compile(source, "<hyac-function>", "exec"), namespace)
    return namespace


async def _run_background(background: Any) -> None:
    if background is None:
        return
    # Starlette dispatches synchronous BackgroundTask callables through AnyIO's
    # inherited thread-pool state. That state is not fork-safe, so invoke the
    # underlying callable directly inside this disposable worker instead.
    tasks = getattr(background, "tasks", None)
    if tasks is not None:
        for task in tasks:
            await _run_background(task)
        return
    if hasattr(background, "func"):
        result = background.func(*background.args, **background.kwargs)
    else:
        result = background()
    if inspect.isawaitable(result):
        await result


async def _invoke(handler_func, handler_args: dict[str, Any]) -> Any:
    sync_client = None
    async_client = None
    handler_args = dict(handler_args)
    request_snapshot = handler_args.pop(INVOCATION_REQUEST_SNAPSHOT_KEY, None)
    handler_args = _restore_handler_requests(handler_args)
    try:
        sync_client, async_client = await _refresh_child_context(handler_args)
        if isinstance(handler_func, str):
            namespace = _compile_source(handler_func)
            handler_func = namespace.get("handler")
            if not callable(handler_func):
                raise RuntimeError("Function source did not define a callable handler")
        invocation = handler_func(**handler_args)
        result = await invocation if inspect.isawaitable(invocation) else invocation

        argument_background = handler_args.get("background_tasks")
        response_background = result.background if isinstance(result, Response) else None
        additional_background = None
        if argument_background is not None and argument_background is not response_background:
            additional_background = argument_background
        # Consume response iterators and response background work before leaving this
        # event loop or closing per-invocation database clients.
        request_scope = (
            request_snapshot.scope
            if isinstance(request_snapshot, RequestSnapshot)
            else None
        )
        return await _encode_result(
            result,
            request_scope,
            additional_background,
        )
    finally:
        if sync_client is not None:
            sync_client.close()
        if async_client is not None:
            await async_client.close()


def _enable_child_subreaper() -> None:
    try:
        ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0)
    except (AttributeError, OSError):
        pass


def _install_child_seccomp_boundary() -> None:
    """Install an inherited, additive syscall deny-list before user code runs."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        prctl = libc.prctl
        prctl.argtypes = (
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
        )
        prctl.restype = ctypes.c_int
        if prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, os.strerror(error_number))

        seccomp = ctypes.CDLL("libseccomp.so.2", use_errno=True)
        seccomp.seccomp_init.argtypes = (ctypes.c_uint32,)
        seccomp.seccomp_init.restype = ctypes.c_void_p
        seccomp.seccomp_release.argtypes = (ctypes.c_void_p,)
        seccomp.seccomp_release.restype = None
        seccomp.seccomp_syscall_resolve_name.argtypes = (ctypes.c_char_p,)
        seccomp.seccomp_syscall_resolve_name.restype = ctypes.c_int
        seccomp.seccomp_rule_add.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.c_uint,
        )
        seccomp.seccomp_rule_add.restype = ctypes.c_int
        seccomp.seccomp_load.argtypes = (ctypes.c_void_p,)
        seccomp.seccomp_load.restype = ctypes.c_int
    except (AttributeError, OSError) as exc:
        raise RuntimeError("Failed to initialize the child seccomp boundary") from exc

    context = seccomp.seccomp_init(_SCMP_ACT_ALLOW)
    if not context:
        raise RuntimeError("Failed to allocate the child seccomp boundary")
    try:
        deny_action = _SCMP_ACT_ERRNO | errno.EPERM
        for syscall_name in _DENIED_CHILD_SYSCALLS:
            syscall_number = seccomp.seccomp_syscall_resolve_name(
                syscall_name.encode("ascii")
            )
            if syscall_number < 0:
                raise RuntimeError(
                    f"Failed to resolve required syscall {syscall_name!r}"
                )
            result = seccomp.seccomp_rule_add(
                context,
                deny_action,
                syscall_number,
                0,
            )
            if result != 0:
                raise RuntimeError(
                    f"Failed to deny syscall {syscall_name!r}: errno {-result}"
                )
        result = seccomp.seccomp_load(context)
        if result != 0:
            raise RuntimeError(
                f"Failed to load the child seccomp boundary: errno {-result}"
            )
    finally:
        seccomp.seccomp_release(context)


def _read_process_stat(pid: int) -> _ProcessStat | None:
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = stat_text[stat_text.rfind(")") + 2 :].split()
        return _ProcessStat(
            identity=_ProcessIdentity(pid=pid, start_time=int(fields[19])),
            parent_pid=int(fields[1]),
            process_group_id=int(fields[2]),
            rss_bytes=max(0, int(fields[21])) * _PAGE_SIZE_BYTES,
        )
    except (FileNotFoundError, IndexError, PermissionError, ProcessLookupError, ValueError):
        return None


def _snapshot_process_table() -> dict[int, _ProcessStat]:
    processes: dict[int, _ProcessStat] = {}
    for proc_path in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(proc_path.name)
        except ValueError:
            continue
        process_stat = _read_process_stat(pid)
        if process_stat is not None:
            processes[pid] = process_stat
    return processes


def _build_process_tree_snapshot() -> _ProcessTreeSnapshot:
    process_table = _snapshot_process_table()
    children_by_parent: dict[int, list[_ProcessStat]] = {}
    for process_stat in process_table.values():
        children_by_parent.setdefault(process_stat.parent_pid, []).append(process_stat)
    return _ProcessTreeSnapshot(
        children_by_parent={
            parent_pid: tuple(children)
            for parent_pid, children in children_by_parent.items()
        },
        processes_by_pid=process_table,
    )


def _process_tree_monitor_main(connection) -> None:
    try:
        while True:
            command = connection.recv_bytes()
            if command == b"stop":
                return
            if command != b"snapshot":
                continue
            try:
                response: tuple[bool, Any] = (True, _build_process_tree_snapshot())
            except BaseException as exc:
                response = (False, f"{type(exc).__name__}: {exc}")
            connection.send_bytes(
                pickle.dumps(response, protocol=pickle.HIGHEST_PROTOCOL)
            )
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


def _get_process_tree_monitor() -> _SharedProcessTreeMonitor:
    loop = asyncio.get_running_loop()
    monitor = _PROCESS_TREE_MONITORS.get(loop)
    if monitor is None:
        monitor = _SharedProcessTreeMonitor()
        _PROCESS_TREE_MONITORS[loop] = monitor
    return monitor


def _descendant_identities(
    root_pid: int,
    process_tree: _ProcessTreeSnapshot | None = None,
) -> list[_ProcessIdentity]:
    if process_tree is None:
        process_tree = _build_process_tree_snapshot()

    descendants: list[_ProcessIdentity] = []
    pending = [root_pid]
    seen = {root_pid}
    while pending:
        parent_pid = pending.pop()
        for child in process_tree.children_by_parent.get(parent_pid, ()):
            if child.identity.pid in seen:
                continue
            seen.add(child.identity.pid)
            descendants.append(child.identity)
            pending.append(child.identity.pid)
    return descendants


def _identity_exists(identity: _ProcessIdentity) -> bool:
    current = _read_process_stat(identity.pid)
    return current is not None and current.identity.start_time == identity.start_time


def _signal_process_identity(identity: _ProcessIdentity, signum: int) -> None:
    if not _identity_exists(identity):
        return
    try:
        os.kill(identity.pid, signum)
    except ProcessLookupError:
        pass


def _merge_descendants(
    tracked: dict[int, _ProcessIdentity],
    root_pid: int,
    process_tree: _ProcessTreeSnapshot | None = None,
) -> list[_ProcessIdentity]:
    discovered: list[_ProcessIdentity] = []
    for identity in _descendant_identities(root_pid, process_tree):
        previous = tracked.get(identity.pid)
        if previous != identity:
            tracked[identity.pid] = identity
            discovered.append(identity)
    return discovered


def _aggregate_process_tree_rss_bytes(
    root_pid: int,
    process_tree: _ProcessTreeSnapshot,
) -> int:
    root = process_tree.processes_by_pid.get(root_pid)
    if root is None:
        return 0
    total_rss_bytes = 0
    pending = [root]
    seen: set[_ProcessIdentity] = set()
    while pending:
        process_stat = pending.pop()
        if process_stat.identity in seen:
            continue
        seen.add(process_stat.identity)
        total_rss_bytes += process_stat.rss_bytes
        pending.extend(
            process_tree.children_by_parent.get(process_stat.identity.pid, ())
        )
    return total_rss_bytes


def _live_identities(
    tracked: dict[int, _ProcessIdentity],
) -> list[_ProcessIdentity]:
    live: list[_ProcessIdentity] = []
    for pid, identity in list(tracked.items()):
        if _identity_exists(identity):
            live.append(identity)
        else:
            tracked.pop(pid, None)
    return live


def _reap_available_children() -> None:
    while True:
        try:
            child_pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if child_pid == 0:
            return


def _cleanup_child_descendants(grace_seconds: float = 0.25) -> None:
    """Stop and reap the complete Linux descendant tree, across sessions and PGIDs."""
    own_pid = os.getpid()
    tracked: dict[int, _ProcessIdentity] = {}
    for identity in _merge_descendants(tracked, own_pid):
        _signal_process_identity(identity, signal.SIGTERM)

    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        _reap_available_children()
        for identity in _merge_descendants(tracked, own_pid):
            _signal_process_identity(identity, signal.SIGTERM)
        live = _live_identities(tracked)
        if not live:
            return
        time.sleep(0.01)

    for identity in _live_identities(tracked):
        _signal_process_identity(identity, signal.SIGKILL)
    final_deadline = time.monotonic() + grace_seconds
    while time.monotonic() < final_deadline:
        _reap_available_children()
        for identity in _merge_descendants(tracked, own_pid):
            _signal_process_identity(identity, signal.SIGKILL)
        if not _live_identities(tracked):
            return
        time.sleep(0.01)
    _reap_available_children()


def _install_child_process_boundary() -> None:
    os.setsid()
    _enable_child_subreaper()

    def terminate(_signum, _frame) -> None:
        os._exit(143)

    signal.signal(signal.SIGTERM, terminate)
    _install_child_seccomp_boundary()


def _close_inherited_file_descriptors(*, keep_fds: set[int]) -> None:
    """Drop parent runtime sockets and IPC handles before invoking user code."""
    preserved = {0, 1, 2, *keep_fds}
    try:
        inherited = [int(entry) for entry in os.listdir("/proc/self/fd")]
    except OSError:
        descriptor_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        if descriptor_limit == resource.RLIM_INFINITY:
            descriptor_limit = 1 << 20
        next_descriptor = 3
        for descriptor in sorted(
            fd for fd in preserved if 3 <= fd < descriptor_limit
        ):
            os.closerange(next_descriptor, descriptor)
            next_descriptor = descriptor + 1
        os.closerange(next_descriptor, int(descriptor_limit))
        return

    for descriptor in inherited:
        if descriptor in preserved:
            continue
        try:
            os.close(descriptor)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise


def _truncate_text(value: str, max_bytes: int) -> str:
    data = value.encode("utf-8", "replace")
    if len(data) <= max_bytes:
        return value
    return data[:max_bytes].decode("utf-8", "ignore")


def _error_payload(exc: BaseException, stdout: str, stderr: str) -> dict[str, Any]:
    from core.exceptions import APIException

    remote_exception: dict[str, Any] | None = None
    if isinstance(exc, APIException):
        remote_exception = {"kind": "api", "code": exc.code, "msg": exc.msg}
    elif isinstance(exc, HTTPException):
        remote_exception = {
            "kind": "http",
            "status_code": exc.status_code,
            "detail": exc.detail,
            "headers": exc.headers,
        }

    return {
        "ok": False,
        "message": _truncate_text(str(exc), 64 * 1024),
        "error_type": (
            "FunctionResultTooLarge"
            if isinstance(exc, FunctionResultTooLarge)
            else type(exc).__name__
        ),
        "remote_exception": remote_exception,
        "traceback": _truncate_text(traceback.format_exc(), MAX_TRACEBACK_BYTES),
        "stdout": stdout,
        "stderr": stderr,
    }


def _send_payload(send_connection, payload: dict[str, Any]) -> None:
    try:
        serialized = _serialize_worker_payload(payload)
    except (TypeError, ValueError, RecursionError) as exc:
        fallback = _error_payload(exc, "", "")
        serialized = _serialize_worker_payload(fallback)
    if len(serialized) > MAX_IPC_PAYLOAD_BYTES:
        fallback = _error_payload(
            FunctionResultTooLarge(
                f"Invocation payload exceeds the {MAX_IPC_PAYLOAD_BYTES}-byte limit"
            ),
            "",
            "",
        )
        serialized = _serialize_worker_payload(fallback)
    send_connection.send_bytes(serialized)


def _child_main(
    send_connection,
    handler_func,
    handler_args: dict[str, Any],
    memory_limit_mb: int,
    timeout_seconds: int,
    log_context: dict[str, object],
) -> None:
    stdout_capture = _BoundedTextCapture(MAX_LOG_BYTES)
    stderr_capture = _BoundedTextCapture(MAX_LOG_BYTES)
    payload: dict[str, Any]
    try:
        _close_inherited_file_descriptors(
            keep_fds={send_connection.fileno()},
        )
        _install_child_process_boundary()
        _set_resource_limits(memory_limit_mb, timeout_seconds)
        from core.logger import function_runtime_log_context
        from core.runtime_client import reset_runtime_client_after_fork

        reset_runtime_client_after_fork()

        with function_runtime_log_context(**log_context):
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                encoded_result = asyncio.run(_invoke(handler_func, handler_args))
        payload = {
            "ok": True,
            "result": encoded_result,
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
        }
    except BaseException as exc:
        payload = _error_payload(
            exc,
            stdout_capture.getvalue(),
            stderr_capture.getvalue(),
        )
    try:
        # Descendant ownership never transfers with a result. The parent drains the
        # payload concurrently and then tears down the worker-owned process group.
        _send_payload(send_connection, payload)
    finally:
        send_connection.close()


def _signal_worker_group(process: multiprocessing.Process, signum: int) -> None:
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        if process.is_alive():
            try:
                os.kill(process.pid, signum)
            except ProcessLookupError:
                pass


async def _stop_worker_group(
    process: multiprocessing.Process,
    tracked_descendants: dict[int, _ProcessIdentity],
    process_monitor: _SharedProcessTreeMonitor,
    *,
    discover_descendants: bool,
) -> BaseException | None:
    # The child calls setsid() before invoking user source, so its PID is the PGID.
    # Explicit identities also cover descendants that created a new session or PGID.
    cleanup_errors: list[BaseException] = []

    def worker_is_alive() -> bool:
        try:
            return process.is_alive()
        except BaseException as exc:
            cleanup_errors.append(exc)
            return True

    def signal_tracked(signum: int) -> list[_ProcessIdentity]:
        try:
            identities = _live_identities(tracked_descendants)
        except BaseException as exc:
            cleanup_errors.append(exc)
            return []
        for identity in identities:
            try:
                _signal_process_identity(identity, signum)
            except BaseException as exc:
                cleanup_errors.append(exc)
        return identities

    def signal_worker(signum: int) -> None:
        try:
            _signal_worker_group(process, signum)
        except BaseException as exc:
            cleanup_errors.append(exc)

    async def discover_and_signal(signum: int, *, force: bool = False) -> None:
        if not discover_descendants or not worker_is_alive():
            return
        try:
            process_tree = await asyncio.wait_for(
                process_monitor.snapshot(force=force),
                timeout=PROCESS_TREE_DISCOVERY_TIMEOUT_SECONDS,
            )
            discovered = _merge_descendants(
                tracked_descendants,
                process.pid,
                process_tree,
            )
            for identity in discovered:
                _signal_process_identity(identity, signum)
        except BaseException as exc:
            cleanup_errors.append(exc)

    async def pause() -> None:
        try:
            await asyncio.sleep(0.01)
        except asyncio.CancelledError as exc:
            cleanup_errors.append(exc)

    try:
        await discover_and_signal(signal.SIGTERM, force=True)
        signal_tracked(signal.SIGTERM)
        signal_worker(signal.SIGTERM)
        deadline = time.monotonic() + 0.75
        while time.monotonic() < deadline:
            await discover_and_signal(signal.SIGTERM)
            live_descendants = signal_tracked(signal.SIGTERM)
            if not worker_is_alive() and not live_descendants:
                break
            await pause()
    finally:
        signal_tracked(signal.SIGKILL)
        await discover_and_signal(signal.SIGKILL, force=True)
        signal_worker(signal.SIGKILL)
        kill_deadline = time.monotonic() + 0.5
        while time.monotonic() < kill_deadline:
            await discover_and_signal(signal.SIGKILL)
            live_descendants = signal_tracked(signal.SIGKILL)
            if not worker_is_alive() and not live_descendants:
                break
            await pause()
        if worker_is_alive():
            try:
                process.kill()
            except BaseException as exc:
                cleanup_errors.append(exc)
            direct_kill_deadline = time.monotonic() + 0.25
            while worker_is_alive() and time.monotonic() < direct_kill_deadline:
                await pause()
        try:
            process.join(timeout=0)
        except BaseException as exc:
            cleanup_errors.append(exc)

    reportable_errors = [
        exc
        for exc in cleanup_errors
        if not isinstance(exc, (asyncio.CancelledError, TimeoutError))
    ]
    if reportable_errors:
        _LOGGER.warning(
            "Worker cleanup completed with process-tree monitor errors: %s",
            "; ".join(
                f"{type(exc).__name__}: {exc}" for exc in reportable_errors
            ),
        )
    return cleanup_errors[0] if cleanup_errors else None


def _raise_remote_error(payload: dict[str, Any]) -> None:
    remote = payload.get("remote_exception")
    if remote:
        if remote["kind"] == "api":
            from core.exceptions import APIException

            exc: BaseException = APIException(code=remote["code"], msg=remote["msg"])
        else:
            exc = HTTPException(
                status_code=remote["status_code"],
                detail=remote["detail"],
                headers=remote["headers"],
            )
        setattr(exc, "remote_stdout", payload["stdout"])
        setattr(exc, "remote_stderr", payload["stderr"])
        setattr(exc, "remote_traceback", payload["traceback"])
        raise exc

    raise FunctionExecutionError(
        payload["message"] or payload["error_type"],
        error_type=payload["error_type"],
        stdout=payload["stdout"],
        stderr=payload["stderr"],
        traceback_text=payload["traceback"],
    )


async def execute_function(
    handler_func,
    handler_args: dict[str, Any],
    *,
    timeout_seconds: int,
    memory_limit_mb: int,
    log_context: dict[str, object] | None = None,
) -> FunctionExecutionResult:
    """Run one invocation in a disposable Linux process group."""
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")
    if memory_limit_mb < 128:
        raise ValueError("memory_limit_mb must be at least 128")

    process_monitor = _get_process_tree_monitor()
    process_monitor.acquire()
    receive_connection = None
    send_connection = None
    try:
        process_context = multiprocessing.get_context("fork")
        receive_connection, send_connection = process_context.Pipe(duplex=False)
        process = process_context.Process(
            target=_child_main,
            args=(
                send_connection,
                handler_func,
                handler_args,
                memory_limit_mb,
                timeout_seconds,
                log_context or {},
            ),
            daemon=False,
        )
        process.start()
        worker_pid = process.pid
        if worker_pid is None:
            raise RuntimeError("Function worker started without a PID")
    except BaseException:
        if receive_connection is not None:
            receive_connection.close()
        if send_connection is not None:
            send_connection.close()
        await process_monitor.release()
        raise
    send_connection.close()
    payload: dict[str, Any] | None = None
    deadline = time.monotonic() + timeout_seconds
    payload_task = asyncio.create_task(
        _receive_worker_payload(receive_connection, deadline=deadline)
    )
    timed_out = False
    memory_exceeded = False
    cleanup_error: BaseException | None = None
    tracked_descendants: dict[int, _ProcessIdentity] = {}
    last_safe_process_tree: _ProcessTreeSnapshot | None = None
    try:
        while True:
            if payload_task.done():
                try:
                    payload = payload_task.result()
                except TimeoutError:
                    timed_out = True
                break
            if not process.is_alive():
                # A worker can close immediately after its final write. Give the
                # nonblocking reader a small, deadline-bounded drain window so a
                # complete frame is never mistaken for a result-less worker exit.
                drain_seconds = min(0.05, max(0.0, deadline - time.monotonic()))
                if drain_seconds > 0:
                    try:
                        payload = await asyncio.wait_for(
                            asyncio.shield(payload_task),
                            timeout=drain_seconds,
                        )
                    except TimeoutError:
                        timed_out = time.monotonic() >= deadline
                break
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                break

            monitor_generation = process_monitor.generation
            try:
                process_tree = await asyncio.wait_for(
                    process_monitor.snapshot(),
                    timeout=min(
                        remaining_seconds,
                        PROCESS_TREE_POLL_TIMEOUT_SECONDS,
                    ),
                )
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                if last_safe_process_tree is not None:
                        _merge_descendants(
                            tracked_descendants,
                            worker_pid,
                            last_safe_process_tree,
                        )
                process_monitor.invalidate_generation(monitor_generation)
            except (EOFError, OSError, RuntimeError) as exc:
                _LOGGER.warning(
                    "Invalidating failed process-tree monitor generation %s: %s",
                    monitor_generation,
                    exc,
                )
                if last_safe_process_tree is not None:
                        _merge_descendants(
                            tracked_descendants,
                            worker_pid,
                            last_safe_process_tree,
                        )
                process_monitor.invalidate_generation(monitor_generation)
            else:
                last_safe_process_tree = process_tree
                _merge_descendants(
                    tracked_descendants,
                    worker_pid,
                    process_tree,
                )
                if _aggregate_process_tree_rss_bytes(
                    worker_pid,
                    process_tree,
                ) > memory_limit_mb * 1024 * 1024:
                    memory_exceeded = True
                    break

            if payload_task.done():
                try:
                    payload = payload_task.result()
                except TimeoutError:
                    timed_out = True
                break
            if not process.is_alive():
                drain_seconds = min(0.05, max(0.0, deadline - time.monotonic()))
                if drain_seconds > 0:
                    try:
                        payload = await asyncio.wait_for(
                            asyncio.shield(payload_task),
                            timeout=drain_seconds,
                        )
                    except TimeoutError:
                        timed_out = time.monotonic() >= deadline
                break
            sleep_seconds = min(0.01, max(0.0, deadline - time.monotonic()))
            if sleep_seconds > 0:
                await asyncio.sleep(sleep_seconds)

        if payload is None and not memory_exceeded:
            timed_out = process.is_alive() or time.monotonic() >= deadline
    finally:
        if not payload_task.done():
            payload_task.cancel()
        try:
            await payload_task
        except BaseException:
            # The main loop either already propagated the reader failure or selected
            # a stronger timeout/memory/cancellation outcome. Always consume the task.
            pass
        receive_connection.close()
        try:
            cleanup_error = await _stop_worker_group(
                process,
                tracked_descendants,
                process_monitor,
                discover_descendants=True,
            )
        finally:
            await process_monitor.release()

    if isinstance(cleanup_error, asyncio.CancelledError):
        raise cleanup_error

    if memory_exceeded:
        memory_error = FunctionExecutionError(
            "Function process tree exceeded its "
            f"{memory_limit_mb}-MiB aggregate RSS limit",
            error_type="MemoryLimitExceeded",
        )
        if cleanup_error is not None:
            raise memory_error from cleanup_error
        raise memory_error

    if payload is None:
        if timed_out or process.exitcode == -signal.SIGXCPU:
            timeout_error = TimeoutError(
                f"Function exceeded its {timeout_seconds}-second execution limit"
            )
            if cleanup_error is not None:
                raise timeout_error from cleanup_error
            raise timeout_error
        worker_exit_error = FunctionExecutionError(
            f"Function worker exited without a result (exit code {process.exitcode})",
            error_type="WorkerExit",
        )
        if cleanup_error is not None:
            raise worker_exit_error from cleanup_error
        raise worker_exit_error

    if cleanup_error is not None:
        raise cleanup_error

    if not payload["ok"]:
        _raise_remote_error(payload)
    return FunctionExecutionResult(
        value=_decode_result(payload["result"]),
        stdout=payload["stdout"],
        stderr=payload["stderr"],
    )
