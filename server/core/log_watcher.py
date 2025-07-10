import asyncio
from collections import defaultdict
from loguru import logger
from typing import Dict, List, Callable, Coroutine, Any

from beanie.odm.documents import Document
from fastapi import WebSocket

from models.logger_model import LogEntry


class LogWatcherManager:
    """
    Manages MongoDB Change Streams to watch for new log entries and notify subscribers.
    """

    def __init__(self):
        # {app_id: {func_id: [WebSocket]}}
        self._subscribers: Dict[str, Dict[str, List[WebSocket]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # {app_id: asyncio.Task}
        self._watch_tasks: Dict[str, asyncio.Task] = {}
        logger.info("LogWatcherManager initialized.")

    async def subscribe(self, app_id: str, func_id: str, websocket: WebSocket):
        """Subscribe a websocket to a specific function's logs."""
        self._subscribers[app_id][func_id].append(websocket)
        logger.info(
            f"WebSocket {websocket.client} subscribed to logs for app '{app_id}', func '{func_id}'"
        )
        if app_id not in self._watch_tasks:
            self._start_watching(app_id)

    async def unsubscribe(self, app_id: str, func_id: str, websocket: WebSocket):
        """Unsubscribe a websocket from a specific function's logs."""
        if websocket in self._subscribers[app_id][func_id]:
            self._subscribers[app_id][func_id].remove(websocket)
            logger.info(
                f"WebSocket {websocket.client} unsubscribed from logs for app '{app_id}', func '{func_id}'"
            )
            if not self._subscribers[app_id][func_id]:
                del self._subscribers[app_id][func_id]

        if not self._subscribers[app_id]:
            del self._subscribers[app_id]
            self._stop_watching(app_id)

    def _start_watching(self, app_id: str):
        """Start a new change stream watch task for an application."""
        if app_id in self._watch_tasks:
            logger.warning(f"Watch task for app '{app_id}' already running.")
            return

        task = asyncio.create_task(self._watch_logs(app_id))
        self._watch_tasks[app_id] = task
        logger.info(f"Started watching logs for app '{app_id}'.")

    def _stop_watching(self, app_id: str):
        """Stop the change stream watch task for an application."""
        if app_id not in self._watch_tasks:
            logger.warning(f"No watch task found for app '{app_id}'.")
            return

        task = self._watch_tasks.pop(app_id)
        task.cancel()
        logger.info(f"Stopped watching logs for app '{app_id}'.")

    async def _watch_logs(self, app_id: str):
        """The core task that watches the LogEntry collection for changes."""
        pipeline = [
            {
                "$match": {
                    "operationType": "insert",
                    "fullDocument.app_id": app_id,
                }
            }
        ]
        try:
            collection = LogEntry.get_motor_collection()
            async with collection.watch(pipeline) as stream:
                async for change in stream:
                    log_entry_data = change["fullDocument"]
                    func_id = log_entry_data.get("function_id")
                    if not func_id:
                        continue

                    log_entry = LogEntry.model_validate(log_entry_data)

                    # Create a list of coroutines to send messages
                    tasks = []
                    subscribers = self._subscribers.get(app_id, {}).get(func_id, [])
                    for ws in subscribers:
                        tasks.append(self._send_log(ws, log_entry))

                    if tasks:
                        await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            logger.info(f"Watch task for app '{app_id}' was cancelled.")
        except Exception as e:
            from pymongo.errors import OperationFailure

            if isinstance(
                e, OperationFailure
            ) and "The $changeStream stage is only supported on replica sets" in str(e):
                logger.error(
                    f"MongoDB Change Stream failed for app '{app_id}'. "
                    "Please ensure your MongoDB is running as a replica set. "
                    f"Original error: {e}"
                )
            else:
                logger.error(
                    f"An unexpected error occurred in the watch task for app '{app_id}': {e}",
                    exc_info=True,
                )
        finally:
            logger.info(f"Watch task for app '{app_id}' finished.")
            # Ensure task is removed if it exits unexpectedly
            if app_id in self._watch_tasks:
                del self._watch_tasks[app_id]

    async def _send_log(self, websocket: WebSocket, log_entry: LogEntry):
        """Send a single log entry to a websocket."""
        try:
            await websocket.send_text(log_entry.model_dump_json(by_alias=True))
        except Exception as e:
            logger.warning(
                f"Failed to send log to {websocket.client}. It might be disconnected. Error: {e}"
            )


# Create a singleton instance
log_watcher = LogWatcherManager()
