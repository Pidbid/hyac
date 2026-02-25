import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass

from lsp_sidecar.lsp_process import LspProcess, spawn_pylsp


PoolKey = tuple[str, str]


@dataclass
class IdleEntry:
    process: LspProcess
    last_used_ts: float


class LspProcessPool:
    """
    Simple process pool keyed by (app_id, workspace).
    A process is leased to one websocket session at a time.
    """

    def __init__(self, idle_ttl_seconds: int = 300):
        self.idle_ttl_seconds = idle_ttl_seconds
        self._idle: dict[PoolKey, list[IdleEntry]] = defaultdict(list)
        self._busy: dict[int, PoolKey] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: PoolKey) -> LspProcess:
        async with self._lock:
            await self._cleanup_expired_locked()
            idle_list = self._idle.get(key, [])
            while idle_list:
                entry = idle_list.pop()
                if entry.process.alive:
                    self._busy[id(entry.process)] = key
                    return entry.process
            process = await spawn_pylsp(workspace=key[1])
            self._busy[id(process)] = key
            return process

    async def release(self, process: LspProcess) -> None:
        async with self._lock:
            key = self._busy.pop(id(process), None)
            if not key:
                if process.alive:
                    await process.terminate()
                return
            if process.alive:
                self._idle[key].append(IdleEntry(process=process, last_used_ts=time.time()))

    async def discard(self, process: LspProcess) -> None:
        async with self._lock:
            self._busy.pop(id(process), None)
        await process.terminate()

    async def _cleanup_expired_locked(self) -> None:
        now = time.time()
        for key in list(self._idle.keys()):
            fresh_entries: list[IdleEntry] = []
            for entry in self._idle[key]:
                is_expired = now - entry.last_used_ts > self.idle_ttl_seconds
                if is_expired or not entry.process.alive:
                    await entry.process.terminate()
                else:
                    fresh_entries.append(entry)
            if fresh_entries:
                self._idle[key] = fresh_entries
            else:
                self._idle.pop(key, None)

