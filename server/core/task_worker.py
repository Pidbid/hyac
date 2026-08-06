"""Lease-based, crash-recoverable application task worker."""

import asyncio
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger
from docker import errors as docker_errors
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from core.app_storage import app_storage_service
from core.database import mongodb_manager
from core.docker_manager import (
    _cleanup_runtime_generation,
    clear_expired_generic_runtime_owner,
    delete_application_background,
    docker_manager,
    generic_runtime_owner_is_expired,
    runtime_container_matches_ingress,
    running_apps,
    start_app_container,
    stop_app_container,
)
from core.environment_contract import LEGACY_PLATFORM_ENV_KEYS
from core.utils import check_mongodb_user_exists, create_mongodb_user
from models.applications_model import Application, ApplicationStatus
from models.tasks_model import Task, TaskAction, TaskStatus


LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 15
RECONCILE_SECONDS = 30
TASK_POLL_SECONDS = 0.25
MAX_CONCURRENT_TASKS = 8
MAX_TASK_ATTEMPTS = 5
MAX_BACKOFF_SECONDS = 60
WORKER_ID = str(uuid.uuid4())

_ACTION_SOURCE_STATUS = {
    TaskAction.START_APP: ApplicationStatus.STARTING,
    TaskAction.RESTART_APP: ApplicationStatus.STARTING,
    TaskAction.STOP_APP: ApplicationStatus.STOPPING,
    TaskAction.DELETE_APP: ApplicationStatus.DELETING,
}
_ACTION_TERMINAL_STATUS = {
    TaskAction.START_APP: ApplicationStatus.RUNNING,
    TaskAction.RESTART_APP: ApplicationStatus.RUNNING,
    TaskAction.STOP_APP: ApplicationStatus.STOPPED,
}


class LeaseLostError(RuntimeError):
    """Raised when this worker no longer owns the task lease."""


class ReconcileFenceLostError(RuntimeError):
    """Raised when another lifecycle transition wins reconciliation."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def find_one_and_update(query: dict, update: dict):
    """Atomic Task claim wrapper kept explicit for auditability and testing."""
    collection = mongodb_manager.get_collection(Task)
    return await collection.find_one_and_update(
        query,
        update,
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def claim_next_task(excluded_app_ids: set[str] | None = None) -> Task | None:
    now = _now()
    excluded_app_query = {}
    if excluded_app_ids:
        app_ids = sorted(excluded_app_ids)
        excluded_app_query = {
            "$nor": [
                {"app_id": {"$in": app_ids}},
                {"payload.app_id": {"$in": app_ids}},
            ]
        }

    # A final-attempt worker can crash after the action but before writing a
    # terminal state. Reclaim that expired lease without consuming another
    # attempt so the task can converge instead of staying RUNNING forever.
    recovery_query = {
        "status": TaskStatus.RUNNING,
        "attempts": {"$gte": MAX_TASK_ATTEMPTS},
        "lease_expires_at": {"$lte": now},
        **excluded_app_query,
    }
    recovered_doc = await find_one_and_update(
        recovery_query,
        {
            "$set": {
                "status": TaskStatus.RUNNING,
                "lease_owner": WORKER_ID,
                "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                "updated_at": now,
            }
        },
    )
    if recovered_doc:
        return Task.model_validate(recovered_doc)

    query = {
        "attempts": {"$lt": MAX_TASK_ATTEMPTS},
        "$or": [
            {
                "status": TaskStatus.PENDING,
                "$or": [
                    {"next_attempt_at": None},
                    {"next_attempt_at": {"$lte": now}},
                ],
            },
            {
                "status": TaskStatus.RUNNING,
                "lease_expires_at": {"$lte": now},
            },
        ],
        **excluded_app_query,
    }
    doc = await find_one_and_update(
        query,
        {
            "$set": {
                "status": TaskStatus.RUNNING,
                "lease_owner": WORKER_ID,
                "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                "updated_at": now,
            },
            "$inc": {"attempts": 1},
        },
    )
    return Task.model_validate(doc) if doc else None


async def _heartbeat(task_id: str, lease_lost: asyncio.Event) -> None:
    try:
        while True:
            if not await _renew_owned_task_lease(task_id):
                lease_lost.set()
                logger.warning("Task {} lease was lost", task_id)
                return
            await asyncio.sleep(HEARTBEAT_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception:
        lease_lost.set()
        logger.exception("Task {} heartbeat failed", task_id)


async def _renew_owned_task_lease(task_id: str) -> bool:
    """Renew only the task claim owned by this worker."""
    now = _now()
    result = await mongodb_manager.get_collection(Task).update_one(
        {
            "task_id": task_id,
            "status": TaskStatus.RUNNING,
            "lease_owner": WORKER_ID,
        },
        {
            "$set": {
                "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                "updated_at": now,
            }
        },
    )
    return result.matched_count > 0


async def _recover_runtime_cleanup_before_destructive_action(
    task: Task,
    app: Application,
    runtime_state: dict,
) -> None:
    """Resolve stale cleanup ownership before stop, restart, or delete work."""
    runtime_generation = runtime_state["runtime_generation"]
    pending_generation = getattr(
        app, "pending_traefik_cleanup_generation", None
    )
    owner_task_id = getattr(app, "runtime_cleanup_task_id", None)
    owner = getattr(app, "runtime_cleanup_lease_owner", None)
    generic_owner_expired = generic_runtime_owner_is_expired(app)

    if owner_task_id not in {None, task.task_id}:
        raise RuntimeError("Runtime cleanup ownership belongs to another task")
    if owner_task_id is None and owner and not generic_owner_expired:
        raise RuntimeError("Runtime cleanup ownership is still active")

    task_owned_cleanup = owner_task_id == task.task_id
    current_pending_cleanup = pending_generation == runtime_generation
    if task_owned_cleanup or current_pending_cleanup:
        cleaned = await _cleanup_runtime_generation(
            app.app_id,
            f"hyac-app-runtime-{app.app_id.lower()}",
            runtime_generation,
            None,
            getattr(app, "runtime_token_hash", None),
            cleanup_task_id=task.task_id,
            cleanup_lease_owner=WORKER_ID,
        )
        if not cleaned:
            raise RuntimeError("Failed to recover runtime cleanup ownership")
        app.runtime_token_hash = None
        app.pending_traefik_cleanup_generation = None
        app.runtime_cleanup_task_id = None
        app.runtime_cleanup_lease_owner = None
        app.runtime_cleanup_lease_expires_at = None
        runtime_state["runtime_token_hash"] = None
        return

    if pending_generation is not None:
        raise RuntimeError("Runtime cleanup generation is not authoritative")
    if generic_owner_expired:
        if not await clear_expired_generic_runtime_owner(app):
            raise RuntimeError("Failed to clear expired runtime cleanup ownership")


async def _run_action(
    task: Task,
    app_id: str,
    app: Application | None,
    runtime_state: dict | None = None,
) -> None:
    if task.action != TaskAction.DELETE_APP and not app:
        raise ValueError(f"Application with app_id {app_id} not found")

    runtime_state = runtime_state if runtime_state is not None else {}
    source_status = runtime_state.setdefault(
        "source_status", _ACTION_SOURCE_STATUS.get(task.action)
    )
    lifecycle_revision = runtime_state.setdefault(
        "lifecycle_revision", getattr(app, "lifecycle_revision", 0) if app else 0
    )
    if app and runtime_state.get("runtime_generation") is None:
        runtime_state["runtime_generation"] = app.runtime_generation
    if app and task.action in {
        TaskAction.STOP_APP,
        TaskAction.RESTART_APP,
        TaskAction.DELETE_APP,
    }:
        await _recover_runtime_cleanup_before_destructive_action(
            task,
            app,
            runtime_state,
        )

    async def publish_running(container_info: dict) -> None:
        try:
            await _mark_runtime_running(
                app_id,
                container_info["generation"],
                source_status,
                lifecycle_revision,
                task.task_id,
                runtime_owner_task_id=container_info.get(
                    "runtime_owner_task_id"
                ),
                runtime_owner=container_info.get("runtime_owner"),
            )
        except LeaseLostError:
            # The successor that owns the task lease may also own this exact
            # generation. A stale worker must never delete its runtime.
            raise
        except Exception as exc:
            # An unknown commit result can still become visible after the
            # client gives up. Recovery will converge from immutable evidence;
            # destructive cleanup is therefore unsafe.
            if isinstance(exc, PyMongoError) and exc.has_error_label(
                "UnknownTransactionCommitResult"
            ):
                raise
            if not await _reserve_unpublished_runtime_cleanup(task.task_id):
                raise LeaseLostError(
                    f"Task {task.task_id} lost cleanup ownership"
                ) from exc
            await _cleanup_runtime_generation(
                app_id,
                container_info["name"],
                container_info["generation"],
                container_info.get("id"),
                runtime_state.get("runtime_token_hash"),
                cleanup_task_id=task.task_id,
                cleanup_lease_owner=WORKER_ID,
            )
            raise

    if task.action == TaskAction.START_APP:
        if not app.db_password:
            raise ValueError(f"DB password for app {app_id} is not set")
        if not await check_mongodb_user_exists(username=app.app_id):
            if not await create_mongodb_user(
                username=app.app_id,
                password=app.db_password,
                target_db=app.app_id,
            ):
                raise RuntimeError(f"Failed to create MongoDB user for app {app_id}")
        await app_storage_service.ensure_ready(app.app_id)
        container_info = await start_app_container(
            app,
            runtime_state=runtime_state,
            expected_status=source_status,
            expected_lifecycle_revision=lifecycle_revision,
            cleanup_task_id=task.task_id,
            cleanup_lease_owner=WORKER_ID,
        )
        if not container_info:
            raise RuntimeError("Failed to start application container")
        await publish_running(container_info)
    elif task.action == TaskAction.STOP_APP:
        stopped = await stop_app_container(
            app_id,
            runtime_state["runtime_generation"],
            source_status,
            lifecycle_revision,
        )
        if not stopped:
            raise RuntimeError("Runtime authority changed before stop")
        await _mark_runtime_status(
            app_id,
            app.runtime_generation,
            ApplicationStatus.STOPPED,
            source_status,
            lifecycle_revision,
            task.task_id,
        )
    elif task.action == TaskAction.RESTART_APP:
        stopped = await stop_app_container(
            app_id,
            runtime_state["runtime_generation"],
            source_status,
            lifecycle_revision,
        )
        if not stopped:
            raise RuntimeError("Runtime authority changed before restart")
        container_info = await start_app_container(
            app,
            runtime_state=runtime_state,
            expected_status=source_status,
            expected_lifecycle_revision=lifecycle_revision,
            cleanup_task_id=task.task_id,
            cleanup_lease_owner=WORKER_ID,
        )
        if not container_info:
            raise RuntimeError("Failed to restart application container")
        await publish_running(container_info)
    elif task.action == TaskAction.DELETE_APP:
        if app:
            await delete_application_background(
                app,
                expected_runtime_generation=runtime_state["runtime_generation"],
                expected_status=source_status,
                expected_lifecycle_revision=lifecycle_revision,
            )


async def _mark_runtime_running(
    app_id: str,
    runtime_generation: int,
    expected_status: ApplicationStatus,
    expected_lifecycle_revision: int,
    completed_task_id: str,
    *,
    runtime_owner_task_id: str | None = None,
    runtime_owner: str | None = None,
) -> None:
    """Mark only the authoritative runtime generation as running."""
    await _mark_runtime_status(
        app_id,
        runtime_generation,
        ApplicationStatus.RUNNING,
        expected_status,
        expected_lifecycle_revision,
        completed_task_id,
        runtime_owner_task_id=runtime_owner_task_id,
        runtime_owner=runtime_owner,
    )


async def _reserve_unpublished_runtime_cleanup(task_id: str) -> bool:
    """Extend this task's lease before destructively cleaning its generation."""
    now = _now()
    result = await mongodb_manager.get_collection(Task).update_one(
        {
            "task_id": task_id,
            "status": TaskStatus.RUNNING,
            "lease_owner": WORKER_ID,
            "published_at": None,
        },
        {
            "$set": {
                "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                "updated_at": now,
            }
        },
    )
    return result.matched_count > 0


async def _publication_committed(
    task_collection,
    application_collection,
    *,
    app_id: str,
    runtime_generation: int,
    status: ApplicationStatus,
    published_revision: int,
    completed_task_id: str,
) -> bool:
    """Resolve an ambiguous commit from immutable task-owned evidence."""
    publication = await task_collection.find_one(
        {
            "task_id": completed_task_id,
            "published_status": status.value,
            "published_lifecycle_revision": published_revision,
            "published_runtime_generation": runtime_generation,
        }
    )
    publication_get = (
        publication.get
        if isinstance(publication, dict)
        else lambda key: getattr(publication, key, None)
    )
    if not publication or publication_get("published_at") is None:
        return False

    # Read the Application too so the common case is confirmed against the
    # terminal CAS. A later lifecycle task may already have advanced or
    # deleted it; the task evidence remains conclusive because both documents
    # were written by the same transaction.
    application = await application_collection.find_one({"app_id": app_id})
    if application:
        getter = (
            application.get
            if isinstance(application, dict)
            else lambda key: getattr(application, key, None)
        )
        exact_application_publication = (
            getter("runtime_generation") == runtime_generation
            and getter("status") == status
            and getter("lifecycle_revision") == published_revision
            and getter("lifecycle_completed_task_id") == completed_task_id
        )
        if not exact_application_publication:
            logger.info(
                "Application {} advanced after committed publication for task {}",
                app_id,
                completed_task_id,
            )
    return True


async def _mark_runtime_status(
    app_id: str,
    runtime_generation: int,
    status: ApplicationStatus,
    expected_status: ApplicationStatus,
    expected_lifecycle_revision: int,
    completed_task_id: str,
    *,
    runtime_owner_task_id: str | None = None,
    runtime_owner: str | None = None,
) -> None:
    """Atomically publish Application state and immutable Task-owned evidence."""
    now = _now()
    published_revision = expected_lifecycle_revision + 1
    application_collection = mongodb_manager.get_collection(Application)
    task_collection = mongodb_manager.get_collection(Task)
    try:
        async with mongodb_manager.client.start_session() as session:
            async with await session.start_transaction():
                task_result = await task_collection.update_one(
                    {
                        "task_id": completed_task_id,
                        "status": TaskStatus.RUNNING,
                        "lease_owner": WORKER_ID,
                        "published_at": None,
                    },
                    {
                        "$set": {
                            "published_at": now,
                            "published_status": status.value,
                            "published_lifecycle_revision": published_revision,
                            "published_runtime_generation": runtime_generation,
                            "updated_at": now,
                        }
                    },
                    session=session,
                )
                if task_result.matched_count == 0:
                    raise LeaseLostError(
                        f"Task {completed_task_id} lost its lease before publication"
                    )

                application_query = {
                        "app_id": app_id,
                        "runtime_generation": runtime_generation,
                        "status": expected_status,
                        "lifecycle_revision": expected_lifecycle_revision,
                        "pending_traefik_cleanup_generation": None,
                }
                if runtime_owner is None:
                    application_query.update(
                        runtime_cleanup_task_id=None,
                        runtime_cleanup_lease_owner=None,
                    )
                else:
                    application_query.update(
                        runtime_cleanup_task_id=runtime_owner_task_id,
                        runtime_cleanup_lease_owner=runtime_owner,
                    )
                application_update_fields = {
                    "status": status,
                    "lifecycle_completed_task_id": completed_task_id,
                    "runtime_cleanup_lease_expires_at": None,
                    "updated_at": now,
                }
                if runtime_owner is not None:
                    application_update_fields.update(
                        runtime_cleanup_task_id=None,
                        runtime_cleanup_lease_owner=None,
                        runtime_cleanup_lease_expires_at=None,
                    )
                result = await application_collection.update_one(
                    application_query,
                    {
                        "$set": application_update_fields,
                        "$inc": {"lifecycle_revision": 1},
                    },
                    session=session,
                )
                if result.matched_count == 0:
                    raise RuntimeError(
                        f"Runtime generation {runtime_generation} for app {app_id} "
                        f"is no longer authoritative for status {status.value}"
                    )
    except PyMongoError as exc:
        if not exc.has_error_label("UnknownTransactionCommitResult"):
            raise
        if await _publication_committed(
            task_collection,
            application_collection,
            app_id=app_id,
            runtime_generation=runtime_generation,
            status=status,
            published_revision=published_revision,
            completed_task_id=completed_task_id,
        ):
            logger.warning(
                "Resolved unknown commit result for lifecycle task {} from "
                "immutable publication evidence",
                completed_task_id,
            )
            return
        raise


def _task_success_update() -> dict:
    return {
        "$set": {
            "status": TaskStatus.SUCCESS,
            "result": {"message": "Task completed successfully"},
            "last_error": None,
            "lease_owner": None,
            "lease_expires_at": None,
            "next_attempt_at": None,
            "updated_at": _now(),
        }
    }


async def _mark_owned_task_success(collection, task: Task) -> bool:
    result = await collection.update_one(
        {
            "task_id": task.task_id,
            "status": TaskStatus.RUNNING,
            "lease_owner": WORKER_ID,
        },
        _task_success_update(),
    )
    return result.matched_count > 0


async def _complete_already_published_lifecycle_task(
    collection,
    task: Task,
    app: Application | None,
) -> bool:
    """Finalize a reclaimed task whose application transition already committed."""
    terminal_status = _ACTION_TERMINAL_STATUS.get(task.action)
    source_revision = task.payload.get("lifecycle_revision")
    if terminal_status is None:
        return False

    published_at = getattr(task, "published_at", None)
    published_status = getattr(task, "published_status", None)
    published_revision = getattr(task, "published_lifecycle_revision", None)
    published_generation = getattr(task, "published_runtime_generation", None)
    has_task_publication = (
        published_at is not None
        and published_status == terminal_status.value
        and published_revision is not None
        and published_generation is not None
        and (
            source_revision is None
            or published_revision == source_revision + 1
        )
    )
    has_legacy_application_publication = bool(
        app
        and getattr(app, "lifecycle_completed_task_id", None) == task.task_id
        and app.status == terminal_status
        and (
            source_revision is None
            or getattr(app, "lifecycle_revision", 0) == source_revision + 1
        )
    )
    if not has_task_publication and not has_legacy_application_publication:
        return False

    if not await _mark_owned_task_success(collection, task):
        logger.warning(
            "Published lifecycle task {} was reclaimed by another worker; "
            "result was discarded",
            task.task_id,
        )
    return True


async def process_task(task: Task) -> None:
    app = None
    runtime_state = {}
    owned_runtime_generation = None
    owned_application_status = None
    owned_lifecycle_revision = None
    heartbeat = None
    action_task = None
    lease_waiter = None
    lease_lost = asyncio.Event()
    collection = mongodb_manager.get_collection(Task)
    try:
        if not await _renew_owned_task_lease(task.task_id):
            raise LeaseLostError(
                f"Task {task.task_id} lease was lost before processing"
            )
        heartbeat = asyncio.create_task(_heartbeat(task.task_id, lease_lost))
        lease_waiter = asyncio.create_task(lease_lost.wait())
        app_id = task.app_id or task.payload.get("app_id")
        if not app_id:
            raise ValueError("app_id is missing in task")
        app = await Application.find_one({"app_id": app_id})
        if app:
            owned_runtime_generation = getattr(app, "runtime_generation", None)
            owned_application_status = _ACTION_SOURCE_STATUS.get(
                task.action, getattr(app, "status", None)
            )
            owned_lifecycle_revision = task.payload.get(
                "lifecycle_revision", getattr(app, "lifecycle_revision", 0)
            )
            if owned_runtime_generation is not None:
                runtime_state["runtime_generation"] = owned_runtime_generation
            runtime_state["source_status"] = owned_application_status
            runtime_state["lifecycle_revision"] = owned_lifecycle_revision
        if await _complete_already_published_lifecycle_task(
            collection,
            task,
            app,
        ):
            return
        if lease_lost.is_set() or not await _renew_owned_task_lease(task.task_id):
            raise LeaseLostError(
                f"Task {task.task_id} lease was lost before action launch"
            )
        action_task = asyncio.create_task(
            _run_action(task, app_id, app, runtime_state)
        )
        await asyncio.wait(
            {action_task, lease_waiter}, return_when=asyncio.FIRST_COMPLETED
        )
        if lease_lost.is_set():
            if not action_task.done():
                action_task.cancel()
                await asyncio.gather(action_task, return_exceptions=True)
            raise LeaseLostError(f"Task {task.task_id} lease was lost")
        lease_waiter.cancel()
        await asyncio.gather(lease_waiter, return_exceptions=True)
        await action_task
        if not await _mark_owned_task_success(collection, task):
            logger.warning(
                "Task {} completed after its lease was lost; result was discarded",
                task.task_id,
            )
    except LeaseLostError:
        logger.warning(
            "Task {} action cancelled because this worker lost its lease",
            task.task_id,
        )
    except asyncio.CancelledError:
        if action_task is not None and not action_task.done():
            action_task.cancel()
            await asyncio.gather(action_task, return_exceptions=True)
        raise
    except Exception as exc:
        error_message = f"Task {task.task_id} failed: {exc}"
        logger.exception(error_message)
        exhausted = task.attempts >= MAX_TASK_ATTEMPTS
        backoff = min(2 ** max(task.attempts - 1, 0), MAX_BACKOFF_SECONDS)
        if exhausted:
            try:
                await _mark_exhausted_task_and_runtime_error(
                    task,
                    error_message,
                    app=app,
                    runtime_generation=runtime_state.get("runtime_generation"),
                    expected_status=owned_application_status,
                    expected_lifecycle_revision=owned_lifecycle_revision,
                )
            except LeaseLostError:
                logger.warning(
                    "Skipped exhausted failure publication for task {}; "
                    "ownership advanced",
                    task.task_id,
                )
            except Exception:
                logger.exception(
                    "Atomic exhausted failure publication failed for task {}; "
                    "the RUNNING lease remains recoverable",
                    task.task_id,
                )
        else:
            await collection.update_one(
                {
                    "task_id": task.task_id,
                    "status": TaskStatus.RUNNING,
                    "lease_owner": WORKER_ID,
                },
                {
                    "$set": {
                        "status": TaskStatus.PENDING,
                        "result": {"error": error_message},
                        "last_error": error_message,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "next_attempt_at": _now() + timedelta(seconds=backoff),
                        "updated_at": _now(),
                    }
                },
            )
    finally:
        if lease_waiter is not None:
            lease_waiter.cancel()
            await asyncio.gather(lease_waiter, return_exceptions=True)
        if heartbeat is not None:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        if action_task is not None and not action_task.done():
            action_task.cancel()
            await asyncio.gather(action_task, return_exceptions=True)


async def _mark_exhausted_task_and_runtime_error(
    task: Task,
    error_message: str,
    *,
    app: Application | None,
    runtime_generation: int | None,
    expected_status: ApplicationStatus | None,
    expected_lifecycle_revision: int | None,
) -> None:
    """Atomically terminalize an exhausted task and its owned Application."""
    now = _now()
    task_collection = mongodb_manager.get_collection(Task)
    application_collection = mongodb_manager.get_collection(Application)
    published_revision = (
        expected_lifecycle_revision + 1
        if expected_lifecycle_revision is not None
        else None
    )
    async with mongodb_manager.client.start_session() as session:
        async with await session.start_transaction():
            task_result = await task_collection.update_one(
                {
                    "task_id": task.task_id,
                    "status": TaskStatus.RUNNING,
                    "lease_owner": WORKER_ID,
                },
                {
                    "$set": {
                        "status": TaskStatus.FAILED,
                        "result": {"error": error_message},
                        "last_error": error_message,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "next_attempt_at": None,
                        "published_at": now,
                        "published_status": ApplicationStatus.ERROR.value,
                        "published_lifecycle_revision": published_revision,
                        "published_runtime_generation": runtime_generation,
                        "updated_at": now,
                    }
                },
                session=session,
            )
            if task_result.matched_count == 0:
                raise LeaseLostError(
                    f"Task {task.task_id} lost its lease before failure publication"
                )

            if (
                app is None
                or runtime_generation is None
                or expected_status is None
                or expected_lifecycle_revision is None
            ):
                return
            app_result = await application_collection.update_one(
                {
                    "app_id": app.app_id,
                    "runtime_generation": runtime_generation,
                    "status": expected_status,
                    "lifecycle_revision": expected_lifecycle_revision,
                    "runtime_cleanup_task_id": None,
                    "runtime_cleanup_lease_owner": None,
                },
                {
                    "$set": {
                        "status": ApplicationStatus.ERROR,
                        "lifecycle_completed_task_id": task.task_id,
                        "updated_at": now,
                    },
                    "$inc": {"lifecycle_revision": 1},
                },
                session=session,
            )
            if app_result.matched_count == 0:
                raise LeaseLostError(
                    f"Application {app.app_id} advanced before failure publication"
                )


async def _enqueue_start(
    app: Application,
    *,
    session=None,
    task: Task | None = None,
) -> None:
    """Insert a START task, optionally using a caller-owned transaction."""
    if task is None:
        existing = await Task.find_one(
            {
                "app_id": app.app_id,
                "status": {"$in": [TaskStatus.PENDING, TaskStatus.RUNNING]},
            }
        )
        if existing:
            return
        task = Task(
            app_id=app.app_id,
            action=TaskAction.START_APP,
            payload={
                "app_id": app.app_id,
                "lifecycle_revision": getattr(app, "lifecycle_revision", 0),
            },
            status=TaskStatus.PENDING,
        )
    await task.insert(session=session)


def _new_reconcile_start_task(app_id: str, lifecycle_revision: int) -> Task:
    return Task(
        app_id=app_id,
        action=TaskAction.START_APP,
        payload={
            "app_id": app_id,
            "lifecycle_revision": lifecycle_revision,
        },
        status=TaskStatus.PENDING,
    )


async def _transition_reconcile_to_starting(
    app: Application,
    *,
    revoke_runtime_token: bool,
) -> bool:
    """Atomically advance the lifecycle fence and publish one stable START task."""
    expected_runtime_generation = app.runtime_generation
    expected_status = app.status
    expected_lifecycle_revision = getattr(app, "lifecycle_revision", 0)
    next_lifecycle_revision = expected_lifecycle_revision + 1
    updated_at = _now()
    task = None
    update_fields = {
        "status": ApplicationStatus.STARTING,
        "lifecycle_completed_task_id": None,
        "runtime_cleanup_lease_expires_at": None,
        "updated_at": updated_at,
    }
    if revoke_runtime_token:
        update_fields["runtime_token_hash"] = None

    async def persist_reconcile(session):
        nonlocal task
        result = await mongodb_manager.get_collection(Application).update_one(
            {
                "app_id": app.app_id,
                "runtime_generation": expected_runtime_generation,
                "status": expected_status,
                "lifecycle_revision": expected_lifecycle_revision,
                "runtime_cleanup_task_id": None,
                "runtime_cleanup_lease_owner": None,
                "pending_traefik_cleanup_generation": None,
            },
            {
                "$set": update_fields,
                "$inc": {"lifecycle_revision": 1},
            },
            session=session,
        )
        if result.matched_count == 0:
            raise ReconcileFenceLostError(
                f"Application {app.app_id} advanced during reconciliation"
            )
        if task is None:
            task = _new_reconcile_start_task(
                app.app_id,
                next_lifecycle_revision,
            )
        await _enqueue_start(app, session=session, task=task)

    try:
        async with mongodb_manager.client.start_session() as session:
            # The task is cached after the winning CAS so a transaction retry
            # cannot create a second durable task identity.
            await session.with_transaction(persist_reconcile)
    except ReconcileFenceLostError:
        logger.info(
            "Skipped reconcile transition for app {} generation {}; "
            "lifecycle authority advanced",
            app.app_id,
            expected_runtime_generation,
        )
        return False

    app.status = ApplicationStatus.STARTING
    app.lifecycle_revision = next_lifecycle_revision
    app.lifecycle_completed_task_id = None
    app.updated_at = updated_at
    if revoke_runtime_token:
        app.runtime_token_hash = None
    return True


async def _active_lifecycle_app_ids() -> set[str]:
    """Read database-backed lifecycle ownership across workers and restarts."""
    active_tasks = await Task.find(
        {
            "$or": [
                {
                    "status": TaskStatus.PENDING,
                    "attempts": {"$lt": MAX_TASK_ATTEMPTS},
                },
                {
                    "status": TaskStatus.RUNNING,
                },
            ],
            "action": {
                "$in": [
                    TaskAction.START_APP,
                    TaskAction.RESTART_APP,
                    TaskAction.STOP_APP,
                    TaskAction.DELETE_APP,
                ]
            },
        }
    ).to_list()
    return {
        app_id
        for task in active_tasks
        if (app_id := task.app_id or task.payload.get("app_id"))
    }


async def _replace_reconciled_runtime(
    app: Application,
    container: dict,
) -> None:
    """Remove a confirmed stale runtime before scheduling its replacement."""
    expected_runtime_generation = app.runtime_generation
    container_id = container["id"]
    container_name = container["name"]
    cleaned = await _cleanup_runtime_generation(
        app.app_id,
        container_name,
        expected_runtime_generation,
        container_id,
        app.runtime_token_hash,
    )
    if not cleaned:
        return

    if not await _transition_reconcile_to_starting(
        app,
        revoke_runtime_token=True,
    ):
        return

    registry_entry = running_apps.get(app.app_id)
    if (
        registry_entry
        and registry_entry.get("generation") == expected_runtime_generation
        and registry_entry.get("id") == container_id
    ):
        running_apps.pop(app.app_id, None)


async def _replace_missing_runtime(app: Application) -> None:
    """Schedule a missing runtime only if this generation is still current."""
    expected_runtime_generation = app.runtime_generation
    if not await _transition_reconcile_to_starting(
        app,
        revoke_runtime_token=True,
    ):
        return

    registry_entry = running_apps.get(app.app_id)
    if (
        registry_entry
        and registry_entry.get("generation") == expected_runtime_generation
    ):
        running_apps.pop(app.app_id, None)


async def reconcile_running_apps() -> None:
    expected = await Application.find(
        {
            "status": {
                "$in": [
                    ApplicationStatus.RUNNING,
                    ApplicationStatus.STARTING,
                ]
            }
        }
    ).to_list()
    if not expected:
        return
    active_lifecycle_app_ids = await _active_lifecycle_app_ids()
    containers = await asyncio.to_thread(docker_manager.list_containers, all=True)
    containers_by_name = {
        item["name"]: item
        for item in containers
        if item["name"].startswith("hyac-app-runtime-")
    }
    for app in expected:
        if app.app_id in active_lifecycle_app_ids:
            continue
        container_name = f"hyac-app-runtime-{app.app_id.lower()}"
        container = containers_by_name.get(container_name)
        generic_owner_expired = generic_runtime_owner_is_expired(app)
        pending_cleanup_generation = getattr(
            app, "pending_traefik_cleanup_generation", None
        )
        cleanup_task_id = getattr(app, "runtime_cleanup_task_id", None)
        cleanup_owner = getattr(app, "runtime_cleanup_lease_owner", None)
        recoverable_generic_cleanup = bool(
            pending_cleanup_generation == app.runtime_generation
            and cleanup_task_id is None
            and (
                cleanup_owner is None
                or generic_owner_expired
            )
        )
        if recoverable_generic_cleanup:
            cleaned = await _cleanup_runtime_generation(
                app.app_id,
                container_name,
                app.runtime_generation,
                container.get("id") if container else None,
                app.runtime_token_hash,
            )
            if not cleaned:
                continue
            app.runtime_token_hash = None
            app.pending_traefik_cleanup_generation = None
            app.runtime_cleanup_lease_owner = None
            app.runtime_cleanup_lease_expires_at = None
            containers_by_name.pop(container_name, None)
            container = None
        elif generic_owner_expired:
            if not await clear_expired_generic_runtime_owner(app):
                continue
        if container_name not in containers_by_name:
            await _replace_missing_runtime(app)
            continue
        container = containers_by_name[container_name]
        try:
            environment = (
                await asyncio.to_thread(
                    docker_manager.get_container_environment, container["id"]
                )
                or {}
            )
        except docker_errors.NotFound:
            await _replace_missing_runtime(app)
            continue
        if (
            container.get("status") != "running"
            or container.get("health_status") != "healthy"
            or not runtime_container_matches_ingress(container, app.app_id)
        ):
            await _replace_reconciled_runtime(app, container)
            continue
        runtime_token = environment.get("RUNTIME_TOKEN", "")
        runtime_token_hash = hashlib.sha256(runtime_token.encode("utf-8")).hexdigest()
        credentials_match = bool(
            runtime_token
            and app.runtime_token_hash
            and hmac.compare_digest(runtime_token_hash, app.runtime_token_hash)
            and environment.get("RUNTIME_GENERATION")
            == str(app.runtime_generation)
        )
        if (
            not credentials_match
            or LEGACY_PLATFORM_ENV_KEYS.intersection(environment)
        ):
            await _replace_reconciled_runtime(app, container)
            continue
        running_apps[app.app_id] = {
            "id": container["id"],
            "name": container_name,
            "generation": app.runtime_generation,
        }


def _task_app_id(task: Task) -> str | None:
    return task.app_id or task.payload.get("app_id")


async def _reconcile_loop() -> None:
    """Reconcile runtimes independently from task execution."""
    while True:
        try:
            await reconcile_running_apps()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Application reconciliation failed; retrying")
        await asyncio.sleep(RECONCILE_SECONDS)


async def _run_claimed_task(task: Task, active_app_ids: set[str]) -> None:
    app_id = _task_app_id(task)
    try:
        await process_task(task)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Unhandled task processing failure for {}", task.task_id)
    finally:
        if app_id:
            active_app_ids.discard(app_id)


async def watch_for_tasks() -> None:
    """Claim tasks concurrently while serializing work for each application."""
    active_app_ids: set[str] = set()
    in_flight: set[asyncio.Task] = set()
    reconcile_task = asyncio.create_task(_reconcile_loop())
    try:
        while True:
            try:
                completed = {task for task in in_flight if task.done()}
                if completed:
                    in_flight.difference_update(completed)
                    await asyncio.gather(*completed, return_exceptions=True)

                if len(in_flight) >= MAX_CONCURRENT_TASKS:
                    completed, _ = await asyncio.wait(
                        in_flight, return_when=asyncio.FIRST_COMPLETED
                    )
                    in_flight.difference_update(completed)
                    await asyncio.gather(*completed, return_exceptions=True)
                    continue

                task = await claim_next_task(active_app_ids)
                if task is None:
                    if in_flight:
                        completed, _ = await asyncio.wait(
                            in_flight,
                            timeout=TASK_POLL_SECONDS,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        in_flight.difference_update(completed)
                        if completed:
                            await asyncio.gather(
                                *completed, return_exceptions=True
                            )
                    else:
                        await asyncio.sleep(TASK_POLL_SECONDS)
                    continue

                app_id = _task_app_id(task)
                if app_id:
                    active_app_ids.add(app_id)
                in_flight.add(
                    asyncio.create_task(_run_claimed_task(task, active_app_ids))
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Task worker loop failed; reconnecting")
                await asyncio.sleep(5)
    finally:
        reconcile_task.cancel()
        for task in in_flight:
            task.cancel()
        await asyncio.gather(
            reconcile_task, *in_flight, return_exceptions=True
        )
