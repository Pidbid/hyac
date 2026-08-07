import asyncio
import ctypes
import errno
import inspect
import multiprocessing
import os
import pickle
import resource
import signal
import socket
import struct
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from queue import Empty
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import BackgroundTasks, HTTPException, Request, Response
from loguru import logger
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, StreamingResponse


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("APP_ID", "test-app")
os.environ.setdefault("RUNTIME_TOKEN", "test-runtime-token")


def _write_pickle_marker_and_return_valid_payload(marker_path: str):
    Path(marker_path).write_text("unsafe object construction", encoding="utf-8")
    return {
        "ok": True,
        "result": {"kind": "value", "value": "unsafe"},
        "stdout": "",
        "stderr": "",
    }


def _write_nested_process_marker_and_sleep(marker_path: str):
    Path(marker_path).write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(60)


def _find_file_descriptor_identity(identity: tuple[int, int]) -> bool:
    for entry in os.listdir("/proc/self/fd"):
        try:
            descriptor = int(entry)
            descriptor_stat = os.fstat(descriptor)
        except (OSError, ValueError):
            continue
        if (descriptor_stat.st_dev, descriptor_stat.st_ino) == identity:
            return True
    return False


def _nested_process_pool_result(value: str):
    return os.getpid(), value


def _run_seccomp_attack_probe(result_queue, marker_path: str) -> None:
    from core.function_executor import execute_function

    marker = Path(marker_path)

    async def run_probe():
        async def healthy_handler():
            await asyncio.sleep(0.2)
            return "parallel-healthy"

        def attack_handler():
            parent_pid = os.getppid()
            marker.write_text(str(os.getpid()), encoding="utf-8")
            libc = ctypes.CDLL(None, use_errno=True)
            seccomp = ctypes.CDLL("libseccomp.so.2")
            seccomp.seccomp_syscall_resolve_name.argtypes = (ctypes.c_char_p,)
            seccomp.seccomp_syscall_resolve_name.restype = ctypes.c_int

            def syscall_errno(name: str, *args: int) -> int:
                number = seccomp.seccomp_syscall_resolve_name(name.encode("ascii"))
                ctypes.set_errno(0)
                libc.syscall(number, *args)
                return ctypes.get_errno()

            results = {
                "kill_zero": None,
                "tkill": syscall_errno("tkill", parent_pid, 0),
                "tgkill": syscall_errno("tgkill", parent_pid, parent_pid, 0),
                "rt_sigqueueinfo": syscall_errno(
                    "rt_sigqueueinfo", parent_pid, 0, 0
                ),
                "rt_tgsigqueueinfo": syscall_errno(
                    "rt_tgsigqueueinfo", parent_pid, parent_pid, 0, 0
                ),
                "ptrace": syscall_errno("ptrace", 2, parent_pid, 0, 0),
                "process_vm_readv": syscall_errno(
                    "process_vm_readv", parent_pid, 0, 0, 0, 0, 0
                ),
                "process_vm_writev": syscall_errno(
                    "process_vm_writev", parent_pid, 0, 0, 0, 0, 0
                ),
                "process_madvise": syscall_errno(
                    "process_madvise", -1, 0, 0, 0, 0
                ),
                "kcmp": syscall_errno("kcmp", parent_pid, parent_pid, 0, 0, 0),
                "unshare": syscall_errno("unshare", 0),
                "setns": syscall_errno("setns", -1, 0),
            }
            try:
                os.kill(parent_pid, 0)
            except OSError as exc:
                results["kill_zero"] = exc.errno

            pidfd = os.pidfd_open(parent_pid)
            try:
                results["pidfd_send_signal"] = syscall_errno(
                    "pidfd_send_signal", pidfd, 0, 0, 0
                )
                results["pidfd_getfd"] = syscall_errno(
                    "pidfd_getfd", pidfd, 0, 0
                )
            finally:
                os.close(pidfd)

            # This is intentionally last: without the boundary it kills only the
            # sacrificial supervisor process, never the pytest process.
            try:
                os.kill(parent_pid, signal.SIGKILL)
            except OSError as exc:
                results["kill_sigkill"] = exc.errno
            return results

        attack_task = asyncio.create_task(
            execute_function(
                attack_handler,
                {},
                timeout_seconds=3,
                memory_limit_mb=128,
            )
        )
        healthy_task = asyncio.create_task(
            execute_function(
                healthy_handler,
                {},
                timeout_seconds=3,
                memory_limit_mb=128,
            )
        )
        attack, healthy = await asyncio.gather(attack_task, healthy_task)
        return attack.value, healthy.value

    try:
        result_queue.put(("ok", asyncio.run(run_probe())))
    except BaseException as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)))


def test_memory_limit_is_added_above_the_inherited_runtime_baseline(monkeypatch):
    from core import function_executor as executor

    inherited_vms = 384 * 1024 * 1024
    invocation_budget = 128 * 1024 * 1024
    calls = []
    monkeypatch.setattr(
        executor,
        "_current_virtual_memory_bytes",
        lambda: inherited_vms,
    )
    monkeypatch.setattr(executor.resource, "setrlimit", lambda kind, limits: calls.append((kind, limits)))

    executor._set_resource_limits(memory_limit_mb=128, timeout_seconds=5)

    assert calls[0] == (
        resource.RLIMIT_AS,
        (inherited_vms + invocation_budget, inherited_vms + invocation_budget),
    )


@pytest.mark.asyncio
async def test_invocation_worker_closes_inherited_parent_sockets():
    from core.function_executor import execute_function

    parent_socket, peer_socket = socket.socketpair()
    sentinel_stat = os.fstat(parent_socket.fileno())
    identity = (sentinel_stat.st_dev, sentinel_stat.st_ino)
    try:
        result = await execute_function(
            _find_file_descriptor_identity,
            {"identity": identity},
            timeout_seconds=3,
            memory_limit_mb=128,
        )
    finally:
        parent_socket.close()
        peer_socket.close()

    assert result.value is False


@pytest.mark.asyncio
async def test_worker_result_channel_rejects_pickle_without_object_construction(
    monkeypatch,
    tmp_path,
):
    import core.function_executor as executor

    marker = tmp_path / "pickle-object-construction"

    class MaliciousPayload:
        def __reduce__(self):
            return (
                _write_pickle_marker_and_return_valid_payload,
                (str(marker),),
            )

    def malicious_child(send_connection, *_args):
        send_connection.send_bytes(pickle.dumps(MaliciousPayload()))
        send_connection.close()

    monkeypatch.setattr(executor, "_child_main", malicious_child)

    with pytest.raises(executor.FunctionExecutionError) as caught:
        await executor.execute_function(
            lambda: "unused",
            {},
            timeout_seconds=3,
            memory_limit_mb=128,
        )

    assert caught.value.error_type == "InvalidWorkerPayload"
    assert not marker.exists()


@pytest.mark.asyncio
async def test_worker_result_channel_rejects_malformed_data_frame(monkeypatch):
    import core.function_executor as executor

    def malformed_child(send_connection, *_args):
        send_connection.send_bytes(b'{"schema":"hyac-worker-result-v1"}')
        send_connection.close()

    monkeypatch.setattr(executor, "_child_main", malformed_child)

    with pytest.raises(executor.FunctionExecutionError) as caught:
        await executor.execute_function(
            lambda: "unused",
            {},
            timeout_seconds=3,
            memory_limit_mb=128,
        )

    assert caught.value.error_type == "InvalidWorkerPayload"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_frame", ["partial-eof", "oversized", "trailing"])
async def test_worker_result_channel_rejects_invalid_raw_frames(
    monkeypatch,
    invalid_frame,
):
    import core.function_executor as executor

    valid_payload = executor._serialize_worker_payload(
        {
            "ok": True,
            "result": {"kind": "value", "value": "valid"},
            "stdout": "",
            "stderr": "",
        }
    )

    def invalid_child(send_connection, *_args):
        if invalid_frame == "partial-eof":
            frame = struct.pack("!i", len(valid_payload)) + valid_payload[:1]
        elif invalid_frame == "oversized":
            frame = struct.pack("!i", executor.MAX_IPC_PAYLOAD_BYTES + 1)
        else:
            frame = struct.pack("!i", len(valid_payload)) + valid_payload + b"x"
        os.write(send_connection.fileno(), frame)
        send_connection.close()

    monkeypatch.setattr(executor, "_child_main", invalid_child)

    with pytest.raises(executor.FunctionExecutionError) as caught:
        await executor.execute_function(
            lambda: "unused",
            {},
            timeout_seconds=2,
            memory_limit_mb=128,
        )

    assert caught.value.error_type == "InvalidWorkerPayload"


@pytest.mark.asyncio
async def test_worker_result_channel_accepts_multiprocessing_extended_header(
    monkeypatch,
):
    import core.function_executor as executor

    valid_payload = executor._serialize_worker_payload(
        {
            "ok": True,
            "result": {"kind": "value", "value": "extended"},
            "stdout": "",
            "stderr": "",
        }
    )

    def extended_header_child(send_connection, *_args):
        frame = struct.pack("!iQ", -1, len(valid_payload)) + valid_payload
        os.write(send_connection.fileno(), frame)
        send_connection.close()

    monkeypatch.setattr(executor, "_child_main", extended_header_child)

    execution = await executor.execute_function(
        lambda: "unused",
        {},
        timeout_seconds=2,
        memory_limit_mb=128,
    )

    assert execution.value == "extended"


@pytest.mark.asyncio
async def test_buffered_complete_worker_frame_cannot_bypass_expired_deadline():
    import core.function_executor as executor

    process_context = multiprocessing.get_context("fork")
    receive_connection, send_connection = process_context.Pipe(duplex=False)
    send_connection.send_bytes(
        executor._serialize_worker_payload(
            {
                "ok": True,
                "result": {"kind": "value", "value": "late"},
                "stdout": "",
                "stderr": "",
            }
        )
    )
    send_connection.close()
    try:
        with pytest.raises(TimeoutError):
            await executor._receive_worker_payload(
                receive_connection,
                deadline=time.monotonic() - 0.01,
            )
    finally:
        receive_connection.close()


@pytest.mark.asyncio
async def test_partial_worker_result_frame_respects_deadline_without_blocking_loop(
    monkeypatch,
    tmp_path,
):
    import core.function_executor as executor

    original_child_main = executor._child_main
    worker_marker = tmp_path / "partial-result-worker"

    def partial_handler():
        return "unused"

    def healthy_handler():
        return "parallel-ok"

    def controlled_child(send_connection, handler_func, *args):
        if handler_func is not partial_handler:
            return original_child_main(send_connection, handler_func, *args)
        worker_marker.write_text(
            f"{os.getpid()} {send_connection.fileno()}",
            encoding="utf-8",
        )
        os.write(send_connection.fileno(), struct.pack("!i", 64) + b"{")
        time.sleep(1.6)
        send_connection.close()

    monkeypatch.setattr(executor, "_child_main", controlled_child)

    loop = asyncio.get_running_loop()
    registered_readers: set[int] = set()
    observed_reader_fds: set[int] = set()
    original_add_reader = loop.add_reader
    original_remove_reader = loop.remove_reader

    def tracked_add_reader(fd, callback, *args):
        registered_readers.add(fd)
        observed_reader_fds.add(fd)
        return original_add_reader(fd, callback, *args)

    def tracked_remove_reader(fd):
        registered_readers.discard(fd)
        return original_remove_reader(fd)

    monkeypatch.setattr(loop, "add_reader", tracked_add_reader)
    monkeypatch.setattr(loop, "remove_reader", tracked_remove_reader)

    heartbeat_ticks = 0
    stop_heartbeat = False

    async def heartbeat():
        nonlocal heartbeat_ticks
        while not stop_heartbeat:
            heartbeat_ticks += 1
            await asyncio.sleep(0.01)

    heartbeat_task = asyncio.create_task(heartbeat())
    started_at = time.monotonic()
    partial_invocation = asyncio.create_task(
        executor.execute_function(
            partial_handler,
            {},
            timeout_seconds=1,
            memory_limit_mb=128,
        )
    )
    await asyncio.sleep(0.05)
    parallel_invocation = asyncio.create_task(
        executor.execute_function(
            healthy_handler,
            {},
            timeout_seconds=2,
            memory_limit_mb=128,
        )
    )
    try:
        with pytest.raises(TimeoutError, match="1-second execution limit"):
            await partial_invocation
        elapsed = time.monotonic() - started_at
        parallel_result = await parallel_invocation
    finally:
        stop_heartbeat = True
        await heartbeat_task
        if not partial_invocation.done():
            partial_invocation.cancel()
        if not parallel_invocation.done():
            parallel_invocation.cancel()
        await asyncio.gather(
            partial_invocation,
            parallel_invocation,
            return_exceptions=True,
        )

    worker_pid = int(worker_marker.read_text(encoding="utf-8").split()[0])
    await _wait_until_pid_disappears(worker_pid)
    assert parallel_result.value == "parallel-ok"
    assert 0.8 <= elapsed < 1.35
    assert heartbeat_ticks >= 20
    assert not registered_readers
    for reader_fd in observed_reader_fds:
        with pytest.raises(OSError):
            os.fstat(reader_fd)


@pytest.mark.asyncio
async def test_immediate_worker_exit_never_loses_a_complete_result_frame():
    from core.function_executor import execute_function

    def handler(value):
        return {"value": value}

    executions = await asyncio.gather(
        *(
            execute_function(
                handler,
                {"value": index},
                timeout_seconds=3,
                memory_limit_mb=128,
            )
            for index in range(16)
        )
    )

    assert [execution.value for execution in executions] == [
        {"value": index} for index in range(16)
    ]


def _run_timeout_probe(result_queue) -> None:
    from loguru import logger

    from router import _execute_and_log

    def never_returns():
        while True:
            pass

    try:
        asyncio.run(
            _execute_and_log(
                never_returns,
                {},
                logger,
                timeout_seconds=1,
                memory_limit_mb=128,
            )
        )
    except BaseException as exc:
        result_queue.put((type(exc).__name__, getattr(exc, "error_type", None)))


def _run_memory_probe(result_queue) -> None:
    from loguru import logger

    from router import _execute_and_log

    def exceeds_limit():
        return bytearray(256 * 1024 * 1024)

    try:
        asyncio.run(
            _execute_and_log(
                exceeds_limit,
                {},
                logger,
                timeout_seconds=3,
                memory_limit_mb=128,
            )
        )
    except BaseException as exc:
        result_queue.put((type(exc).__name__, getattr(exc, "error_type", None)))


def _run_top_level_timeout_probe(result_queue) -> None:
    from loguru import logger

    from router import _execute_and_log

    source = "while True:\n    pass\n\ndef handler():\n    return 'unreachable'\n"
    try:
        asyncio.run(
            _execute_and_log(
                source,
                {},
                logger,
                timeout_seconds=1,
                memory_limit_mb=128,
            )
        )
    except BaseException as exc:
        result_queue.put((type(exc).__name__, getattr(exc, "error_type", None)))


def _probe(target, timeout: float = 5.0) -> tuple[str, str | None]:
    context = multiprocessing.get_context("fork")
    result_queue = context.Queue()
    process = context.Process(target=target, args=(result_queue,))
    process.start()
    process.join(timeout)
    was_alive = process.is_alive()
    if was_alive:
        process.terminate()
        process.join(1)
    assert not was_alive, "function invocation escaped its hard execution limit"
    try:
        return result_queue.get(timeout=1)
    except Empty as exc:
        raise AssertionError(f"probe exited without a result: {process.exitcode}") from exc


def test_sync_infinite_loop_is_terminated_at_deadline():
    assert _probe(_run_timeout_probe) == ("TimeoutError", None)


def test_memory_limit_terminates_oversized_allocation():
    assert _probe(_run_memory_probe) == ("FunctionExecutionError", "MemoryError")


@pytest.mark.asyncio
async def test_memory_limit_applies_to_aggregate_process_tree_rss(tmp_path):
    from core.function_executor import FunctionExecutionError, execute_function

    memory_limit_bytes = 128 * 1024 * 1024
    pid_file = tmp_path / "aggregate-memory-pids"
    ready_files = [tmp_path / f"aggregate-memory-ready-{index}" for index in range(2)]
    start_file = tmp_path / "aggregate-memory-start"
    stats_file = tmp_path / "aggregate-memory-stats"

    def handler():
        children = []
        for ready_file in ready_files:
            script = (
                "import pathlib, time\n"
                f"ready = pathlib.Path({str(ready_file)!r})\n"
                f"start = pathlib.Path({str(start_file)!r})\n"
                "ready.write_text('ready')\n"
                "while not start.exists(): time.sleep(0.005)\n"
                "allocation = bytearray(int(start.read_text()))\n"
                "for offset in range(0, len(allocation), 4096): allocation[offset] = 1\n"
                "time.sleep(60)\n"
            )
            children.append(subprocess.Popen([sys.executable, "-c", script]))
        pid_file.write_text(
            " ".join(str(child.pid) for child in children),
            encoding="utf-8",
        )
        while not all(ready_file.exists() for ready_file in ready_files):
            time.sleep(0.01)

        def rss_bytes(pid):
            resident_pages = int(
                Path(f"/proc/{pid}/statm").read_text(encoding="utf-8").split()[1]
            )
            return resident_pages * os.sysconf("SC_PAGE_SIZE")

        baseline_rss = rss_bytes(os.getpid()) + sum(
            rss_bytes(child.pid) for child in children
        )
        headroom = memory_limit_bytes - baseline_rss
        allocation_bytes = headroom // 2 + 4 * 1024 * 1024
        if baseline_rss + allocation_bytes >= memory_limit_bytes:
            raise RuntimeError("test process-tree baseline is too close to the limit")
        stats_file.write_text(
            f"{baseline_rss} {allocation_bytes}",
            encoding="utf-8",
        )
        start_tmp = start_file.with_suffix(".tmp")
        start_tmp.write_text(str(allocation_bytes), encoding="utf-8")
        os.replace(start_tmp, start_file)
        time.sleep(60)

    started_at = time.monotonic()
    caught = None
    try:
        with pytest.raises(FunctionExecutionError) as caught:
            await execute_function(
                handler,
                {},
                timeout_seconds=5,
                memory_limit_mb=128,
            )
        elapsed = time.monotonic() - started_at

        assert caught.value.error_type == "MemoryLimitExceeded"
        assert elapsed < 4
        assert all(ready_file.exists() for ready_file in ready_files)
        assert len(pid_file.read_text(encoding="utf-8").split()) == 2
        baseline_rss, allocation_bytes = (
            int(value) for value in stats_file.read_text(encoding="utf-8").split()
        )
        assert baseline_rss < memory_limit_bytes
        assert baseline_rss + allocation_bytes < memory_limit_bytes
        assert baseline_rss + 2 * allocation_bytes > memory_limit_bytes
    finally:
        if pid_file.exists():
            for raw_pid in pid_file.read_text(encoding="utf-8").split():
                _kill_leaked_test_pid(int(raw_pid))


def test_module_top_level_infinite_loop_is_terminated_at_deadline():
    assert _probe(_run_top_level_timeout_probe) == ("TimeoutError", None)


def test_code_loader_only_parses_handler_signature_in_parent(tmp_path):
    from code_loader import CodeLoader

    marker = tmp_path / "parent-side-effect"
    source = (
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\n"
        "async def handler(ctx, request, name='world'):\n    return name\n"
    )

    signature = CodeLoader()._inspect_handler_signature(source)

    assert list(signature.parameters) == ["ctx", "request", "name"]
    assert not marker.exists()


@pytest.mark.asyncio
async def test_isolated_executor_returns_sync_and_response_values():
    from router import _execute_and_log

    def sync_handler():
        return {"ok": True}

    def response_handler():
        return Response("created", status_code=201, headers={"X-Test": "yes"})

    sync_result = await _execute_and_log(
        sync_handler,
        {},
        logger,
        timeout_seconds=2,
        memory_limit_mb=128,
    )
    response_result = await _execute_and_log(
        response_handler,
        {},
        logger,
        timeout_seconds=2,
        memory_limit_mb=128,
    )

    assert sync_result == {"ok": True}
    assert response_result.status_code == 201
    assert response_result.headers["x-test"] == "yes"
    assert response_result.body == b"created"


@pytest.mark.asyncio
async def test_background_tasks_finish_inside_isolated_worker(tmp_path):
    from router import _execute_and_log

    marker = tmp_path / "background-finished"
    tasks = BackgroundTasks()

    def write_marker():
        marker.write_text("done", encoding="utf-8")

    def handler(background_tasks):
        background_tasks.add_task(write_marker)
        return {"scheduled": True}

    result = await _execute_and_log(
        handler,
        {"background_tasks": tasks},
        logger,
        timeout_seconds=2,
        memory_limit_mb=128,
    )

    assert result == {"scheduled": True}
    assert marker.read_text(encoding="utf-8") == "done"


@pytest.mark.asyncio
async def test_background_task_latency_is_part_of_invocation_completion(tmp_path):
    from core.function_executor import execute_function

    marker = tmp_path / "delayed-background-finished"
    tasks = BackgroundTasks()

    def delayed_background():
        time.sleep(0.2)
        marker.write_text("done", encoding="utf-8")

    def handler(background_tasks):
        background_tasks.add_task(delayed_background)
        return {"buffered": True}

    started_at = time.monotonic()
    execution = await execute_function(
        handler,
        {"background_tasks": tasks},
        timeout_seconds=2,
        memory_limit_mb=128,
    )
    elapsed = time.monotonic() - started_at

    assert execution.value == {"buffered": True}
    assert marker.read_text(encoding="utf-8") == "done"
    assert elapsed >= 0.18


@pytest.mark.asyncio
async def test_background_task_time_counts_against_invocation_timeout(tmp_path):
    from core.function_executor import execute_function

    marker = tmp_path / "timed-out-background-worker.pid"
    tasks = BackgroundTasks()

    def blocked_background():
        marker.write_text(str(os.getpid()), encoding="utf-8")
        time.sleep(60)

    def handler(background_tasks):
        background_tasks.add_task(blocked_background)
        return {"must_not_escape": True}

    with pytest.raises(TimeoutError, match="1-second execution limit"):
        await execute_function(
            handler,
            {"background_tasks": tasks},
            timeout_seconds=1,
            memory_limit_mb=128,
        )

    worker_pid = int(marker.read_text(encoding="utf-8"))
    await _wait_until_pid_disappears(worker_pid)


@pytest.mark.asyncio
async def test_value_background_failure_preserves_encoded_value(tmp_path):
    from core.function_executor import execute_function

    marker = tmp_path / "value-background-count"
    tasks = BackgroundTasks()

    def failing_background():
        count = int(marker.read_text(encoding="utf-8")) if marker.exists() else 0
        marker.write_text(str(count + 1), encoding="utf-8")
        raise ValueError("value background exploded")

    def handler(background_tasks):
        background_tasks.add_task(failing_background)
        return {"ok": True}

    execution = await execute_function(
        handler,
        {"background_tasks": tasks},
        timeout_seconds=3,
        memory_limit_mb=128,
    )

    assert execution.value == {"ok": True}
    assert marker.read_text(encoding="utf-8") == "1"
    assert execution.stderr.count("[hyac background task failed: ValueError]") == 1
    assert execution.stderr.count("value background exploded") == 1


@pytest.mark.asyncio
async def test_background_tasks_stop_after_first_failure(tmp_path):
    from core.function_executor import execute_function

    skipped_marker = tmp_path / "later-background-must-not-run"
    tasks = BackgroundTasks()

    def first_background():
        raise ValueError("first background failed")

    def later_background():
        skipped_marker.write_text("unsafe", encoding="utf-8")

    def handler(background_tasks):
        background_tasks.add_task(first_background)
        background_tasks.add_task(later_background)
        return {"buffered": True}

    execution = await execute_function(
        handler,
        {"background_tasks": tasks},
        timeout_seconds=2,
        memory_limit_mb=128,
    )

    assert execution.value == {"buffered": True}
    assert not skipped_marker.exists()
    assert "[hyac background task failed: ValueError]" in execution.stderr
    assert "first background failed" in execution.stderr


@pytest.mark.asyncio
async def test_large_result_and_logs_are_drained_while_worker_is_alive():
    from core.function_executor import MAX_LOG_BYTES, execute_function

    result_size = 2 * 1024 * 1024

    def handler():
        print("l" * result_size, end="")
        return "r" * result_size

    execution = await execute_function(
        handler,
        {},
        timeout_seconds=3,
        memory_limit_mb=128,
    )

    assert execution.value == "r" * result_size
    assert execution.stdout == "l" * result_size
    assert len(execution.stdout.encode()) <= MAX_LOG_BYTES


@pytest.mark.asyncio
async def test_log_capture_has_a_clear_bounded_truncation_contract():
    from core.function_executor import (
        LOG_TRUNCATION_MARKER,
        MAX_LOG_BYTES,
        execute_function,
    )

    def handler():
        print("x" * (MAX_LOG_BYTES + 4096), end="")
        return "ok"

    execution = await execute_function(
        handler,
        {},
        timeout_seconds=3,
        memory_limit_mb=128,
    )

    assert execution.value == "ok"
    assert execution.stdout.endswith(LOG_TRUNCATION_MARKER)
    assert len(execution.stdout.encode()) <= MAX_LOG_BYTES


@pytest.mark.asyncio
async def test_multibyte_log_truncation_stays_within_the_byte_limit():
    from core.function_executor import (
        LOG_TRUNCATION_MARKER,
        MAX_LOG_BYTES,
        execute_function,
    )

    def handler():
        print("界" * MAX_LOG_BYTES, end="")
        return "ok"

    execution = await execute_function(
        handler,
        {},
        timeout_seconds=3,
        memory_limit_mb=128,
    )

    assert execution.stdout.endswith(LOG_TRUNCATION_MARKER)
    assert len(execution.stdout.encode("utf-8")) <= MAX_LOG_BYTES


@pytest.mark.asyncio
async def test_oversized_result_fails_with_an_exact_error_type():
    from core.function_executor import (
        MAX_RESULT_PAYLOAD_BYTES,
        FunctionExecutionError,
        execute_function,
    )

    def handler():
        return "x" * (MAX_RESULT_PAYLOAD_BYTES + 1)

    with pytest.raises(FunctionExecutionError) as caught:
        await execute_function(
            handler,
            {},
            timeout_seconds=3,
            memory_limit_mb=128,
        )

    assert caught.value.error_type == "FunctionResultTooLarge"


@pytest.mark.asyncio
async def test_response_body_limit_is_independent_from_transport_overhead():
    from core.function_executor import MAX_RESPONSE_BODY_BYTES, execute_function

    def handler():
        return Response(b"x" * MAX_RESPONSE_BODY_BYTES)

    execution = await execute_function(
        handler,
        {},
        timeout_seconds=3,
        memory_limit_mb=128,
    )

    assert len(execution.value.body) == MAX_RESPONSE_BODY_BYTES


def _process_is_running(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        state = stat_path.read_text(encoding="utf-8").split()[2]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state != "Z"


async def _wait_until_process_stops(pid: int, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while _process_is_running(pid) and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    assert not _process_is_running(pid), f"descendant process {pid} remained alive"


@pytest.mark.asyncio
async def test_normal_completion_reaps_conventional_subprocesses():
    from core.function_executor import execute_function

    def handler():
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        return child.pid

    execution = await execute_function(
        handler,
        {},
        timeout_seconds=3,
        memory_limit_mb=128,
    )

    await _wait_until_process_stops(execution.value)


@pytest.mark.asyncio
async def test_seccomp_boundary_failure_is_fail_closed_before_user_code(
    monkeypatch,
    tmp_path,
):
    import core.function_executor as executor

    marker = tmp_path / "handler-must-not-run"

    def fail_boundary():
        raise RuntimeError("injected seccomp load failure")

    def handler():
        marker.write_text("unsafe", encoding="utf-8")
        return "unsafe"

    monkeypatch.setattr(executor, "_install_child_seccomp_boundary", fail_boundary)

    with pytest.raises(executor.FunctionExecutionError) as caught:
        await executor.execute_function(
            handler,
            {},
            timeout_seconds=2,
            memory_limit_mb=128,
        )

    assert caught.value.error_type == "RuntimeError"
    assert "injected seccomp load failure" in str(caught.value)
    assert not marker.exists()


@pytest.mark.asyncio
async def test_parent_cleanup_survives_monkeypatch_and_blocks_session_escape(
    tmp_path,
):
    from core.function_executor import execute_function

    report_path = tmp_path / "escape-report"

    def handler():
        import core.function_executor as runtime_executor

        original_send_payload = runtime_executor._send_payload
        runtime_executor._cleanup_child_descendants = lambda *_args, **_kwargs: None
        runtime_executor._send_payload = (
            lambda connection, payload: original_send_payload(connection, payload)
        )
        script = (
            "import os, pathlib, sys, time\n"
            "report = pathlib.Path(sys.argv[1])\n"
            "script_pid = os.getpid()\n"
            "try:\n"
            "    os.setsid()\n"
            "    setsid_errno = 0\n"
            "except OSError as exc:\n"
            "    setsid_errno = exc.errno\n"
            "child_pid = os.fork()\n"
            "if child_pid == 0:\n"
            "    try:\n"
            "        os.setpgid(0, 0)\n"
            "        setpgid_errno = 0\n"
            "    except OSError as exc:\n"
            "        setpgid_errno = exc.errno\n"
            "    grandchild_pid = os.fork()\n"
            "    if grandchild_pid == 0:\n"
            "        time.sleep(60)\n"
            "    report.write_text(\n"
            "        f'{script_pid} {os.getpid()} {grandchild_pid} ' \n"
            "        f'{setsid_errno} {setpgid_errno}'\n"
            "    )\n"
            "    time.sleep(60)\n"
            "time.sleep(60)\n"
        )
        process = subprocess.Popen([sys.executable, "-c", script, str(report_path)])
        deadline = time.monotonic() + 2
        while not report_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not report_path.exists():
            raise RuntimeError("escape probe did not report")
        values = [int(value) for value in report_path.read_text().split()]
        return {
            "pids": values[:3],
            "setsid_errno": values[3],
            "setpgid_errno": values[4],
            "popen_pid": process.pid,
        }

    execution = await execute_function(
        handler,
        {},
        timeout_seconds=4,
        memory_limit_mb=256,
    )

    descendant_pids = set(execution.value["pids"])
    descendant_pids.add(execution.value["popen_pid"])
    try:
        assert execution.value["setsid_errno"] == errno.EPERM
        assert execution.value["setpgid_errno"] == errno.EPERM
        for descendant_pid in descendant_pids:
            await _wait_until_pid_disappears(descendant_pid)
    finally:
        for descendant_pid in descendant_pids:
            _kill_leaked_test_pid(descendant_pid)


def test_seccomp_blocks_same_uid_runtime_attacks_and_parallel_call_survives(tmp_path):
    context = multiprocessing.get_context("fork")
    result_queue = context.Queue()
    marker_path = tmp_path / "attack-worker.pid"
    supervisor = context.Process(
        target=_run_seccomp_attack_probe,
        args=(result_queue, str(marker_path)),
    )
    supervisor.start()
    supervisor.join(8)
    if supervisor.is_alive():
        supervisor.kill()
        supervisor.join(1)

    attack_worker_pid = None
    if marker_path.exists():
        attack_worker_pid = int(marker_path.read_text(encoding="utf-8"))
    try:
        assert supervisor.exitcode == 0, (
            "the sacrificial runtime supervisor was killed by user code: "
            f"exit code {supervisor.exitcode}"
        )
        status, payload = result_queue.get(timeout=1)
        assert status == "ok", payload
        syscall_results, healthy_result = payload
        assert healthy_result == "parallel-healthy"
        assert syscall_results
        assert set(syscall_results.values()) == {errno.EPERM}
    finally:
        if attack_worker_pid is not None:
            _kill_leaked_test_pid(attack_worker_pid)


@pytest.mark.asyncio
async def test_timeout_reaps_conventional_subprocesses(tmp_path):
    from core.function_executor import execute_function

    pid_file = tmp_path / "descendant.pid"

    def handler():
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        pid_file.write_text(str(child.pid), encoding="utf-8")
        while True:
            pass

    with pytest.raises(TimeoutError, match="1-second execution limit"):
        await execute_function(
            handler,
            {},
            timeout_seconds=1,
            memory_limit_mb=128,
        )

    descendant_pid = int(pid_file.read_text(encoding="utf-8"))
    await _wait_until_process_stops(descendant_pid)


async def _wait_until_pid_disappears(pid: int, timeout: float = 3.0) -> None:
    stat_path = Path(f"/proc/{pid}/stat")
    deadline = time.monotonic() + timeout
    while stat_path.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    assert not stat_path.exists(), f"descendant PID {pid} still exists"


def _kill_leaked_test_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("nested_kind", ["process", "process-pool"])
async def test_invocation_worker_allows_nested_processes_without_leaks(
    tmp_path,
    nested_kind,
):
    from core.function_executor import execute_function

    marker = tmp_path / f"nested-{nested_kind}"

    def handler():
        process_context = multiprocessing.get_context("fork")
        if nested_kind == "process":
            child = process_context.Process(
                target=_write_nested_process_marker_and_sleep,
                args=(str(marker),),
            )
            child.start()
            deadline = time.monotonic() + 2
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not marker.exists():
                raise RuntimeError("nested process did not start")
            return {"pid": child.pid, "value": "process-started"}

        with ProcessPoolExecutor(
            max_workers=1,
            mp_context=process_context,
        ) as pool:
            child_pid, value = pool.submit(
                _nested_process_pool_result,
                "pool-returned",
            ).result(timeout=2)
        return {"pid": child_pid, "value": value}

    execution = await execute_function(
        handler,
        {},
        timeout_seconds=5,
        memory_limit_mb=256,
    )

    try:
        assert execution.value["value"] == (
            "process-started" if nested_kind == "process" else "pool-returned"
        )
        await _wait_until_pid_disappears(execution.value["pid"])
    finally:
        _kill_leaked_test_pid(execution.value["pid"])


@pytest.mark.asyncio
async def test_normal_completion_denies_new_session_subprocesses():
    from core.function_executor import execute_function

    def handler():
        try:
            subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                start_new_session=True,
            )
        except PermissionError as exc:
            return exc.errno
        return None

    execution = await execute_function(
        handler,
        {},
        timeout_seconds=3,
        memory_limit_mb=128,
    )

    assert execution.value == 1


@pytest.mark.asyncio
async def test_timeout_keeps_new_session_creation_denied(tmp_path):
    from core.function_executor import execute_function

    pid_file = tmp_path / "escaped-descendant.pid"

    def handler():
        try:
            subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                start_new_session=True,
            )
        except PermissionError as exc:
            pid_file.write_text(str(exc.errno), encoding="utf-8")
        while True:
            pass

    with pytest.raises(TimeoutError, match="1-second execution limit"):
        await execute_function(
            handler,
            {},
            timeout_seconds=1,
            memory_limit_mb=128,
        )

    assert pid_file.read_text(encoding="utf-8") == "1"


@pytest.mark.asyncio
async def test_concurrent_invocations_share_process_table_scans(monkeypatch):
    import core.function_executor as executor

    parent_pid = os.getpid()
    original_snapshot = executor._snapshot_process_table
    scan_count = multiprocessing.Value("i", 0)

    def counted_snapshot():
        is_async_monitor = (
            multiprocessing.current_process().name == "hyac-process-tree-monitor"
        )
        if os.getpid() == parent_pid or is_async_monitor:
            with scan_count.get_lock():
                scan_count.value += 1
        return original_snapshot()

    monkeypatch.setattr(executor, "_snapshot_process_table", counted_snapshot)

    async def handler():
        await asyncio.sleep(0.15)
        return "done"

    results = await asyncio.gather(
        *(
            executor.execute_function(
                handler,
                {},
                timeout_seconds=3,
                memory_limit_mb=128,
            )
            for _ in range(6)
        )
    )

    assert [result.value for result in results] == ["done"] * 6
    assert scan_count.value <= 8, (
        f"concurrent invocations performed {scan_count.value} independent /proc scans"
    )


@pytest.mark.asyncio
async def test_process_table_scan_does_not_block_the_event_loop(monkeypatch):
    import core.function_executor as executor

    await asyncio.sleep(0.1)
    parent_pid = os.getpid()
    original_snapshot = executor._snapshot_process_table
    scan_started = multiprocessing.Event()
    release_scan = multiprocessing.Event()
    scan_stalled_event_loop = multiprocessing.Value("b", False)

    def controlled_snapshot():
        is_async_monitor = (
            multiprocessing.current_process().name == "hyac-process-tree-monitor"
        )
        if (os.getpid() == parent_pid or is_async_monitor) and not scan_started.is_set():
            scan_started.set()
            if not release_scan.wait(timeout=0.25):
                scan_stalled_event_loop.value = True
        return original_snapshot()

    monkeypatch.setattr(executor, "_snapshot_process_table", controlled_snapshot)

    async def release_from_event_loop():
        while not scan_started.is_set():
            await asyncio.sleep(0)
        await asyncio.sleep(0.01)
        release_scan.set()

    async def handler():
        await asyncio.sleep(0.05)
        return "done"

    execution, _ = await asyncio.gather(
        executor.execute_function(
            handler,
            {},
            timeout_seconds=2,
            memory_limit_mb=128,
        ),
        release_from_event_loop(),
    )

    assert execution.value == "done"
    assert not scan_stalled_event_loop.value, "synchronous /proc scan blocked the event loop"


@pytest.mark.parametrize("monitor_failure", ["helper-error", "closed-pipe"])
@pytest.mark.asyncio
async def test_monitor_failure_does_not_block_timeout_cleanup(
    monkeypatch,
    tmp_path,
    monitor_failure,
):
    import core.function_executor as executor

    original_snapshot = executor._SharedProcessTreeMonitor.snapshot

    async def faulty_snapshot(self, *, force=False):
        if force:
            if monitor_failure == "helper-error":
                raise RuntimeError("injected process-tree helper error")
            self._connection.close()
        return await original_snapshot(self, force=force)

    monkeypatch.setattr(
        executor._SharedProcessTreeMonitor,
        "snapshot",
        faulty_snapshot,
    )
    pid_file = tmp_path / f"{monitor_failure}.pid"

    def handler():
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
        )
        pid_file.write_text(
            f"{os.getpid()} {descendant.pid}",
            encoding="utf-8",
        )
        time.sleep(60)

    caught: BaseException | None = None
    worker_pid = None
    descendant_pid = None
    try:
        try:
            await executor.execute_function(
                handler,
                {},
                timeout_seconds=1,
                memory_limit_mb=128,
            )
        except BaseException as exc:
            caught = exc

        worker_pid, descendant_pid = (
            int(value) for value in pid_file.read_text(encoding="utf-8").split()
        )
        await _wait_until_pid_disappears(worker_pid)
        await _wait_until_pid_disappears(descendant_pid)
        assert isinstance(caught, TimeoutError), repr(caught)
    finally:
        if worker_pid is not None:
            _kill_leaked_test_pid(worker_pid)
        if descendant_pid is not None:
            _kill_leaked_test_pid(descendant_pid)


@pytest.mark.asyncio
async def test_cancelled_invocation_reaps_blocked_monitor_and_reuses_loop(
    monkeypatch,
    tmp_path,
):
    import core.function_executor as executor

    original_snapshot = executor._snapshot_process_table
    scan_started = multiprocessing.Event()
    release_scan = multiprocessing.Event()

    def blocked_snapshot():
        is_async_monitor = (
            multiprocessing.current_process().name == "hyac-process-tree-monitor"
        )
        if is_async_monitor and not scan_started.is_set():
            scan_started.set()
            release_scan.wait(timeout=10)
        return original_snapshot()

    monkeypatch.setattr(executor, "_snapshot_process_table", blocked_snapshot)

    loop = asyncio.get_running_loop()
    registered_readers: set[int] = set()
    original_add_reader = loop.add_reader
    original_remove_reader = loop.remove_reader

    def tracked_add_reader(fd, callback, *args):
        registered_readers.add(fd)
        return original_add_reader(fd, callback, *args)

    def tracked_remove_reader(fd):
        registered_readers.discard(fd)
        return original_remove_reader(fd)

    monkeypatch.setattr(loop, "add_reader", tracked_add_reader)
    monkeypatch.setattr(loop, "remove_reader", tracked_remove_reader)
    exception_contexts: list[dict] = []
    original_exception_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: exception_contexts.append(context))

    pid_file = tmp_path / "cancelled-monitor-worker.pid"

    def handler():
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
        )
        pid_file.write_text(
            f"{os.getpid()} {descendant.pid}",
            encoding="utf-8",
        )
        time.sleep(60)

    invocation = asyncio.create_task(
        executor.execute_function(
            handler,
            {},
            timeout_seconds=5,
            memory_limit_mb=128,
        )
    )

    async def release_failsafe():
        await asyncio.sleep(0.6)
        release_scan.set()

    failsafe = asyncio.create_task(release_failsafe())
    worker_pid = None
    descendant_pid = None
    helper_process = None
    try:
        deadline = time.monotonic() + 2
        while (
            not scan_started.is_set() or not pid_file.exists()
        ) and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert scan_started.is_set()
        worker_pid, descendant_pid = (
            int(value) for value in pid_file.read_text(encoding="utf-8").split()
        )

        monitor = executor._get_process_tree_monitor()
        helper_process = monitor._process
        assert helper_process is not None
        invocation.cancel()
        cancel_started = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await invocation
        cancel_elapsed = time.monotonic() - cancel_started

        await _wait_until_pid_disappears(worker_pid)
        await _wait_until_pid_disappears(descendant_pid)
        assert monitor._users == 0
        assert monitor._process is None
        assert monitor._connection is None
        assert monitor._refresh_task is None
        assert not helper_process.is_alive()
        assert helper_process.exitcode is not None
        assert not registered_readers

        follow_up = await executor.execute_function(
            lambda: "reused",
            {},
            timeout_seconds=2,
            memory_limit_mb=128,
        )
        await asyncio.sleep(0)
        assert follow_up.value == "reused"
        assert not exception_contexts
        assert cancel_elapsed < 0.4
    finally:
        if helper_process is None or helper_process.is_alive():
            release_scan.set()
        failsafe.cancel()
        await asyncio.gather(failsafe, return_exceptions=True)
        loop.set_exception_handler(original_exception_handler)
        if not invocation.done():
            invocation.cancel()
            await asyncio.gather(invocation, return_exceptions=True)
        if worker_pid is not None:
            _kill_leaked_test_pid(worker_pid)
        if descendant_pid is not None:
            _kill_leaked_test_pid(descendant_pid)


@pytest.mark.asyncio
async def test_blocked_monitor_snapshot_respects_invocation_deadline_and_restarts(
    monkeypatch,
    tmp_path,
):
    import core.function_executor as executor

    original_snapshot = executor._snapshot_process_table
    block_claimed = multiprocessing.Value("b", False)
    helper_pids = multiprocessing.Array("i", 4)

    def blocked_first_snapshot():
        is_async_monitor = (
            multiprocessing.current_process().name == "hyac-process-tree-monitor"
        )
        should_block = False
        if is_async_monitor:
            current_pid = os.getpid()
            with helper_pids.get_lock():
                if current_pid not in helper_pids[:]:
                    for index, recorded_pid in enumerate(helper_pids):
                        if recorded_pid == 0:
                            helper_pids[index] = current_pid
                            break
            with block_claimed.get_lock():
                if not block_claimed.value:
                    block_claimed.value = True
                    should_block = True
        if should_block:
            time.sleep(1.6)
        return original_snapshot()

    monkeypatch.setattr(executor, "_snapshot_process_table", blocked_first_snapshot)
    pid_file = tmp_path / "blocked-monitor-deadline.pid"

    def handler():
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
        )
        pid_file.write_text(
            f"{os.getpid()} {descendant.pid}",
            encoding="utf-8",
        )
        time.sleep(60)

    caught: BaseException | None = None
    worker_pid = None
    descendant_pid = None
    observed_helper_pids: set[int] = set()
    started_at = time.monotonic()
    try:
        try:
            await executor.execute_function(
                handler,
                {},
                timeout_seconds=1,
                memory_limit_mb=128,
            )
        except BaseException as exc:
            caught = exc
        elapsed = time.monotonic() - started_at

        worker_pid, descendant_pid = (
            int(value) for value in pid_file.read_text(encoding="utf-8").split()
        )
        observed_helper_pids = {pid for pid in helper_pids[:] if pid}
        await _wait_until_pid_disappears(worker_pid)
        await _wait_until_pid_disappears(descendant_pid)
        for helper_pid in observed_helper_pids:
            await _wait_until_pid_disappears(helper_pid)

        monitor = executor._get_process_tree_monitor()
        assert isinstance(caught, TimeoutError), repr(caught)
        assert 0.8 <= elapsed < 1.35
        assert len(observed_helper_pids) >= 2
        assert monitor._users == 0
        assert monitor._process is None
        assert monitor._connection is None
        assert monitor._refresh_task is None

        follow_up = await executor.execute_function(
            lambda: "fresh-generation",
            {},
            timeout_seconds=2,
            memory_limit_mb=128,
        )
        assert follow_up.value == "fresh-generation"
    finally:
        if worker_pid is not None:
            _kill_leaked_test_pid(worker_pid)
        if descendant_pid is not None:
            _kill_leaked_test_pid(descendant_pid)
        for helper_pid in observed_helper_pids:
            _kill_leaked_test_pid(helper_pid)


@pytest.mark.asyncio
async def test_partial_monitor_frame_never_blocks_event_loop_or_cleanup(
    monkeypatch,
    tmp_path,
):
    import core.function_executor as executor

    original_monitor_main = executor._process_tree_monitor_main
    partial_claimed = multiprocessing.Value("b", False)
    helper_pids = multiprocessing.Array("i", 4)

    def partial_frame_monitor(connection):
        current_pid = os.getpid()
        with helper_pids.get_lock():
            if current_pid not in helper_pids[:]:
                for index, recorded_pid in enumerate(helper_pids):
                    if recorded_pid == 0:
                        helper_pids[index] = current_pid
                        break
        with partial_claimed.get_lock():
            send_partial = not partial_claimed.value
            if send_partial:
                partial_claimed.value = True
        if not send_partial:
            return original_monitor_main(connection)

        try:
            if connection.recv_bytes() == b"snapshot":
                prefix = (64).to_bytes(4, byteorder="big", signed=True)
                os.write(connection.fileno(), prefix + b"x")
                time.sleep(1.6)
        finally:
            connection.close()

    monkeypatch.setattr(
        executor,
        "_process_tree_monitor_main",
        partial_frame_monitor,
    )

    loop = asyncio.get_running_loop()
    registered_readers: set[int] = set()
    observed_reader_fds: set[int] = set()
    original_add_reader = loop.add_reader
    original_remove_reader = loop.remove_reader

    def tracked_add_reader(fd, callback, *args):
        registered_readers.add(fd)
        observed_reader_fds.add(fd)
        return original_add_reader(fd, callback, *args)

    def tracked_remove_reader(fd):
        registered_readers.discard(fd)
        return original_remove_reader(fd)

    monkeypatch.setattr(loop, "add_reader", tracked_add_reader)
    monkeypatch.setattr(loop, "remove_reader", tracked_remove_reader)

    heartbeat_ticks = 0
    stop_heartbeat = False

    async def heartbeat():
        nonlocal heartbeat_ticks
        while not stop_heartbeat:
            heartbeat_ticks += 1
            await asyncio.sleep(0.01)

    heartbeat_task = asyncio.create_task(heartbeat())
    pid_file = tmp_path / "partial-frame-worker.pid"

    def handler():
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
        )
        pid_file.write_text(
            f"{os.getpid()} {descendant.pid}",
            encoding="utf-8",
        )
        time.sleep(60)

    caught: BaseException | None = None
    worker_pid = None
    descendant_pid = None
    observed_helper_pids: set[int] = set()
    started_at = time.monotonic()
    try:
        try:
            await executor.execute_function(
                handler,
                {},
                timeout_seconds=1,
                memory_limit_mb=128,
            )
        except BaseException as exc:
            caught = exc
        elapsed = time.monotonic() - started_at
    finally:
        stop_heartbeat = True
        await heartbeat_task

    try:
        worker_pid, descendant_pid = (
            int(value) for value in pid_file.read_text(encoding="utf-8").split()
        )
        observed_helper_pids = {pid for pid in helper_pids[:] if pid}
        await _wait_until_pid_disappears(worker_pid)
        await _wait_until_pid_disappears(descendant_pid)
        for helper_pid in observed_helper_pids:
            await _wait_until_pid_disappears(helper_pid)

        monitor = executor._get_process_tree_monitor()
        assert isinstance(caught, TimeoutError), repr(caught)
        assert 0.8 <= elapsed < 1.35
        assert heartbeat_ticks >= 20
        assert len(observed_helper_pids) >= 2
        assert not registered_readers
        assert monitor._users == 0
        assert monitor._process is None
        assert monitor._connection is None
        assert monitor._refresh_task is None
        assert not monitor._retired_shutdown_tasks
        for reader_fd in observed_reader_fds:
            with pytest.raises(OSError):
                os.fstat(reader_fd)

        follow_up = await executor.execute_function(
            lambda: "after-partial-frame",
            {},
            timeout_seconds=2,
            memory_limit_mb=128,
        )
        assert follow_up.value == "after-partial-frame"
    finally:
        if worker_pid is not None:
            _kill_leaked_test_pid(worker_pid)
        if descendant_pid is not None:
            _kill_leaked_test_pid(descendant_pid)
        for helper_pid in observed_helper_pids:
            _kill_leaked_test_pid(helper_pid)


@pytest.mark.asyncio
async def test_streaming_and_file_responses_are_bounded_and_preserve_raw_headers(tmp_path):
    from router import _execute_and_log

    file_path = tmp_path / "download.bin"
    file_path.write_bytes(b"file-content")

    async def streaming_handler():
        async def chunks():
            yield b"one-"
            yield b"two"

        response = StreamingResponse(chunks(), status_code=202)
        response.set_cookie("a", "1")
        response.set_cookie("b", "2")
        return response

    def file_handler():
        response = FileResponse(file_path, filename="download.bin")
        response.set_cookie("a", "1")
        response.set_cookie("b", "2")
        return response

    streaming = await _execute_and_log(
        streaming_handler, {}, logger, timeout_seconds=3, memory_limit_mb=128
    )
    file_response = await _execute_and_log(
        file_handler, {}, logger, timeout_seconds=3, memory_limit_mb=128
    )

    assert streaming.status_code == 202
    assert streaming.body == b"one-two"
    assert streaming.headers.getlist("set-cookie") == [
        "a=1; Path=/; SameSite=lax",
        "b=2; Path=/; SameSite=lax",
    ]
    assert file_response.body == b"file-content"
    assert file_response.headers["content-disposition"].startswith("attachment;")
    assert file_response.headers.getlist("set-cookie") == [
        "a=1; Path=/; SameSite=lax",
        "b=2; Path=/; SameSite=lax",
    ]


@pytest.mark.asyncio
async def test_streaming_response_is_consumed_on_the_handler_event_loop():
    from router import _execute_and_log

    async def handler():
        handler_loop = asyncio.get_running_loop()

        async def chunks():
            assert asyncio.get_running_loop() is handler_loop
            yield b"same-loop"

        return StreamingResponse(chunks())

    result = await _execute_and_log(
        handler, {}, logger, timeout_seconds=3, memory_limit_mb=128
    )

    assert result.body == b"same-loop"


@pytest.mark.asyncio
async def test_streaming_response_accepts_a_synchronous_iterator_after_fork():
    from router import _execute_and_log

    def handler():
        return StreamingResponse(iter([b"sync-", b"iterator"]))

    result = await _execute_and_log(
        handler, {}, logger, timeout_seconds=3, memory_limit_mb=128
    )

    assert result.body == b"sync-iterator"


@pytest.mark.asyncio
async def test_response_background_runs_once_inside_isolated_worker(tmp_path):
    from router import _execute_and_log

    marker = tmp_path / "response-background"

    def record_background():
        marker.write_text("done", encoding="utf-8")

    def handler():
        return Response("ok", background=BackgroundTask(record_background))

    result = await _execute_and_log(
        handler, {}, logger, timeout_seconds=3, memory_limit_mb=128
    )

    assert result.body == b"ok"
    assert result.background is None
    assert marker.read_text(encoding="utf-8") == "done"


@pytest.mark.asyncio
async def test_file_response_background_runs_after_the_file_is_buffered(tmp_path):
    from router import _execute_and_log

    file_path = tmp_path / "delete-after-send.bin"
    file_path.write_bytes(b"buffer-before-background")

    def handler():
        return FileResponse(
            file_path,
            background=BackgroundTask(file_path.unlink),
        )

    result = await _execute_and_log(
        handler, {}, logger, timeout_seconds=3, memory_limit_mb=128
    )

    assert result.body == b"buffer-before-background"
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_delete_octet_stream_request_is_snapshotted_before_fork():
    from context import EnvContext, FunctionContext
    from router import _execute_and_log, _prepare_arguments

    parent_pid = os.getpid()
    body = b"\x00delete-body\xff"
    delivered = False

    async def parent_only_receive():
        nonlocal delivered
        if os.getpid() != parent_pid:
            raise RuntimeError("live request receive crossed the fork boundary")
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "DELETE",
            "scheme": "http",
            "path": "/delete",
            "raw_path": b"/delete",
            "query_string": b"mode=hard",
            "headers": [(b"content-type", b"application/octet-stream")],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
        },
        parent_only_receive,
    )

    async def handler(request):
        return {
            "body": (await request.body()).hex(),
            "method": request.method,
            "mode": request.query_params["mode"],
        }

    args = await _prepare_arguments(
        request,
        inspect.signature(handler),
        FunctionContext(
            app_id="test-app",
            func_id="test-function",
            pymongo_db=None,
            async_db=None,
            code_loader=None,
            env=EnvContext(),
            common={},
            notification_config=None,
        ),
        BackgroundTasks(),
    )
    result = await _execute_and_log(
        handler, args, logger, timeout_seconds=3, memory_limit_mb=128
    )

    assert result == {"body": body.hex(), "method": "DELETE", "mode": "hard"}


@pytest.mark.asyncio
async def test_request_snapshot_rejects_a_body_above_its_declared_limit():
    from core.function_executor import (
        MAX_REQUEST_BODY_BYTES,
        RequestBodyTooLarge,
        snapshot_request,
    )

    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {
            "type": "http.request",
            "body": b"x" * (MAX_REQUEST_BODY_BYTES + 1),
            "more_body": False,
        }

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/upload",
            "headers": [],
            "query_string": b"",
        },
        receive,
    )

    with pytest.raises(RequestBodyTooLarge, match="4194304-byte limit"):
        await snapshot_request(request)


@pytest.mark.asyncio
async def test_object_id_and_http_exception_semantics_survive_isolation():
    from core.exceptions import APIException
    from router import _execute_and_log

    object_id = ObjectId()

    def object_id_handler():
        return {"id": object_id}

    def api_error_handler():
        raise APIException(code=409, msg="conflict")

    def http_error_handler():
        raise HTTPException(
            status_code=429,
            detail={"retry": True},
            headers={"Retry-After": "1"},
        )

    assert await _execute_and_log(
        object_id_handler, {}, logger, timeout_seconds=3, memory_limit_mb=128
    ) == {"id": str(object_id)}

    with pytest.raises(APIException) as api_error:
        await _execute_and_log(
            api_error_handler, {}, logger, timeout_seconds=3, memory_limit_mb=128
        )
    assert (api_error.value.code, api_error.value.msg) == (409, "conflict")

    with pytest.raises(HTTPException) as http_error:
        await _execute_and_log(
            http_error_handler, {}, logger, timeout_seconds=3, memory_limit_mb=128
        )
    assert http_error.value.status_code == 429
    assert http_error.value.detail == {"retry": True}
    assert http_error.value.headers == {"Retry-After": "1"}


@pytest.mark.asyncio
@pytest.mark.parametrize("response_kind", ["response", "file"])
@pytest.mark.parametrize("background_source", ["response", "argument"])
async def test_response_background_failure_preserves_success_response(
    tmp_path, response_kind, background_source
):
    from core.function_executor import execute_function

    marker = tmp_path / f"{response_kind}-background-count"
    file_path = tmp_path / "background-file.bin"
    file_path.write_bytes(b"file-body")

    def failing_background():
        count = int(marker.read_text(encoding="utf-8")) if marker.exists() else 0
        marker.write_text(str(count + 1), encoding="utf-8")
        if response_kind == "file":
            file_path.unlink()
        raise ValueError("background exploded")

    def handler(background_tasks=None):
        if response_kind == "file":
            response = FileResponse(file_path, status_code=207)
        else:
            response = Response(b"response-body", status_code=207)
        response.set_cookie("a", "1")
        response.set_cookie("b", "2")
        if background_source == "response":
            response.background = BackgroundTask(failing_background)
        else:
            background_tasks.add_task(failing_background)
        return response

    tasks = BackgroundTasks()
    execution = await execute_function(
        handler,
        {"background_tasks": tasks},
        timeout_seconds=3,
        memory_limit_mb=128,
    )

    expected_body = b"file-body" if response_kind == "file" else b"response-body"
    assert execution.value.status_code == 207
    assert execution.value.body == expected_body
    assert execution.value.headers.getlist("set-cookie") == [
        "a=1; Path=/; SameSite=lax",
        "b=2; Path=/; SameSite=lax",
    ]
    assert marker.read_text(encoding="utf-8") == "1"
    assert "[hyac background task failed: ValueError]" in execution.stderr
    assert "background exploded" in execution.stderr


@pytest.mark.asyncio
async def test_file_response_preserves_range_and_if_range_semantics(tmp_path):
    from context import EnvContext, FunctionContext
    from router import _execute_and_log, _prepare_arguments

    file_path = tmp_path / "range.bin"
    file_path.write_bytes(b"0123456789")
    stat_result = file_path.stat()
    etag = FileResponse(file_path, stat_result=stat_result).headers["etag"]

    def handler():
        return FileResponse(file_path, stat_result=stat_result)

    context = FunctionContext(
        app_id="test-app",
        func_id="test-function",
        pymongo_db=None,
        async_db=None,
        code_loader=None,
        env=EnvContext(),
        common={},
        notification_config=None,
    )

    async def invoke(headers: list[tuple[bytes, bytes]]):
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/range.bin",
                "raw_path": b"/range.bin",
                "query_string": b"",
                "headers": headers,
                "client": ("127.0.0.1", 1234),
                "server": ("test", 80),
            },
            receive,
        )
        args = await _prepare_arguments(
            request,
            inspect.signature(handler),
            context,
            BackgroundTasks(),
        )
        return await _execute_and_log(
            handler, args, logger, timeout_seconds=3, memory_limit_mb=128
        )

    partial = await invoke([(b"range", b"bytes=2-4")])
    matching_if_range = await invoke(
        [(b"range", b"bytes=2-4"), (b"if-range", etag.encode())]
    )
    mismatched_if_range = await invoke(
        [(b"range", b"bytes=2-4"), (b"if-range", b'"stale-etag"')]
    )
    unsatisfiable = await invoke([(b"range", b"bytes=20-30")])
    multipart = await invoke([(b"range", b"bytes=0-1,8-9")])

    for response in (partial, matching_if_range):
        assert response.status_code == 206
        assert response.body == b"234"
        assert response.headers["content-range"] == "bytes 2-4/10"
        assert response.headers["content-length"] == "3"
    assert mismatched_if_range.status_code == 200
    assert mismatched_if_range.body == b"0123456789"
    assert unsatisfiable.status_code == 416
    assert unsatisfiable.body == b""
    assert unsatisfiable.headers["content-range"] == "*/10"
    assert multipart.status_code == 206
    assert multipart.headers["content-range"].startswith("multipart/byteranges;")
    assert int(multipart.headers["content-length"]) == len(multipart.body)
    assert b"Content-Range: bytes 0-1/10" in multipart.body
    assert b"Content-Range: bytes 8-9/10" in multipart.body
    assert b"01" in multipart.body
    assert b"89" in multipart.body


@pytest.mark.asyncio
async def test_dynamic_handler_preserves_remote_and_worker_exit_error_types(monkeypatch):
    import router as router_module
    from core.function_executor import FunctionExecutionError
    from models.applications_model import Application
    from models.functions_model import Function

    application = Application(
        app_id="test-app",
        app_name="Test App",
        db_password="not-used",
    )
    function = Function(
        function_id="test-function",
        function_name="failing-function",
        app_id="test-app",
        code="def handler():\n    raise ValueError('bad input')\n",
        timeout=3,
        memory_limit=128,
    )

    def value_error_handler():
        raise ValueError("bad input")

    async def load_function(_request, _app_id, _func_id):
        return value_error_handler, function, inspect.signature(value_error_handler)

    class FakeRuntimeClient:
        async def authorize_function(self, _function_id, _authorization):
            return None

        async def write_metric(self, _payload):
            return None

    monkeypatch.setattr(router_module, "_load_function_details", load_function)
    monkeypatch.setattr(
        router_module, "get_runtime_client", lambda: FakeRuntimeClient()
    )

    def make_request():
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}

        return Request(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/test-function",
                "raw_path": b"/test-function",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 1234),
                "server": ("test", 80),
                "app": SimpleNamespace(
                    state=SimpleNamespace(common_modules=SimpleNamespace())
                ),
            },
            receive,
        )

    value_error_response = await router_module.dynamic_handler(
        make_request(), "test-function", BackgroundTasks(), application
    )

    async def raise_worker_exit(*_args, **_kwargs):
        raise FunctionExecutionError(
            "worker exited",
            error_type="WorkerExit",
        )

    monkeypatch.setattr(router_module, "_execute_and_log", raise_worker_exit)
    worker_exit_response = await router_module.dynamic_handler(
        make_request(), "test-function", BackgroundTasks(), application
    )

    assert value_error_response.data["error_type"] == "ValueError"
    assert worker_exit_response.data["error_type"] == "WorkerExit"
