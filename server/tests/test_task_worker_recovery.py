import asyncio
import hashlib
import hmac
import os
import threading
from datetime import timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from pymongo.errors import OperationFailure


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from core import docker_manager, task_worker
from models.applications_model import ApplicationStatus
from models import StorageStatus
from models.tasks_model import TaskAction, TaskStatus


class _FakeTask:
    def __init__(
        self,
        *,
        app_id=None,
        payload=None,
        attempts=1,
        action=TaskAction.START_APP,
        task_id="task-1",
        published_at=None,
        published_status=None,
        published_lifecycle_revision=None,
        published_runtime_generation=None,
    ):
        self.task_id = task_id
        self.app_id = app_id
        self.payload = payload or {}
        self.attempts = attempts
        self.action = action
        self.published_at = published_at
        self.published_status = published_status
        self.published_lifecycle_revision = published_lifecycle_revision
        self.published_runtime_generation = published_runtime_generation
        self.update_document = None

    async def update(self, document):
        self.update_document = document


class _FakeReconcileStartTask:
    def __init__(self, app_id, lifecycle_revision):
        self.task_id = "reconcile-task"
        self.app_id = app_id
        self.action = TaskAction.START_APP
        self.payload = {
            "app_id": app_id,
            "lifecycle_revision": lifecycle_revision,
        }
        self.status = TaskStatus.PENDING

    async def insert(self, session=None):
        return self


class _ApplicationQuery:
    def __init__(self, applications):
        self.applications = applications

    async def to_list(self):
        return self.applications


class _TaskCollection:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count
        self.update_calls = []
        self.update_sessions = []

    async def update_one(self, query, update, session=None):
        self.update_calls.append((query, update))
        self.update_sessions.append(session)
        return SimpleNamespace(matched_count=self.matched_count)


def _task_update_for_status(collection, status):
    return next(
        (query, update)
        for query, update in collection.update_calls
        if update.get("$set", {}).get("status") == status
    )


class _ApplicationCollection:
    def __init__(self, application):
        self.application = application
        self.update_calls = []
        self.update_sessions = []
        self.task_update_calls = []
        self.task_update_sessions = []

    async def update_one(self, query, update, session=None):
        if "task_id" in query:
            self.task_update_calls.append((query, update))
            self.task_update_sessions.append(session)
            return SimpleNamespace(matched_count=1)
        self.update_calls.append((query, update))
        self.update_sessions.append(session)
        if (
            query.get("app_id") != self.application.app_id
            or query.get("runtime_generation")
            != self.application.runtime_generation
            or (
                "status" in query
                and query["status"]
                != getattr(self.application, "status", ApplicationStatus.STARTING)
            )
            or (
                "lifecycle_revision" in query
                and query["lifecycle_revision"]
                != getattr(self.application, "lifecycle_revision", 0)
            )
            or (
                "runtime_token_hash" in query
                and query["runtime_token_hash"]
                != self.application.runtime_token_hash
            )
            or any(
                field in query
                and query[field] != getattr(self.application, field, None)
                for field in (
                    "runtime_cleanup_task_id",
                    "runtime_cleanup_lease_owner",
                    "pending_traefik_cleanup_generation",
                )
            )
        ):
            return SimpleNamespace(matched_count=0)
        for field, value in update["$set"].items():
            setattr(self.application, field, value)
        for field, value in update.get("$inc", {}).items():
            setattr(
                self.application,
                field,
                getattr(self.application, field, 0) + value,
            )
        return SimpleNamespace(matched_count=1)


class _MatchedApplicationCollection:
    async def update_one(self, _query, _update, session=None):
        return SimpleNamespace(matched_count=1)


class _NoOpTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _NoOpSession(_NoOpTransaction):
    async def start_transaction(self):
        return _NoOpTransaction()

    async def with_transaction(self, callback):
        return await callback(self)


class _NoOpTransactionClient:
    def start_session(self):
        return _NoOpSession()


class _AmbiguousCommittedTransaction(_NoOpTransaction):
    async def __aexit__(self, exc_type, exc, traceback):
        if exc_type is None:
            raise OperationFailure(
                "commit result is unknown",
                91,
                {"errorLabels": ["UnknownTransactionCommitResult"]},
            )
        return False


class _AmbiguousCommittedSession(_NoOpSession):
    async def start_transaction(self):
        return _AmbiguousCommittedTransaction()


class _AmbiguousCommittedClient:
    def start_session(self):
        return _AmbiguousCommittedSession()


async def _run_in_fresh_thread(function, *args, **kwargs):
    result = {}

    def invoke():
        try:
            result["value"] = function(*args, **kwargs)
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=invoke)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


async def _run_in_managed_thread(function, *args, **kwargs):
    result = {}

    def invoke():
        try:
            result["value"] = function(*args, **kwargs)
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=invoke)
    thread.start()
    while thread.is_alive():
        await asyncio.sleep(0.001)
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


class TaskWorkerRecoveryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.to_thread_patch = patch.object(
            task_worker.asyncio,
            "to_thread",
            side_effect=_run_in_fresh_thread,
        )
        self.to_thread_patch.start()
        self.addCleanup(self.to_thread_patch.stop)
        self.mongo_client_patch = patch.object(
            task_worker.mongodb_manager,
            "client",
            _NoOpTransactionClient(),
        )
        self.mongo_client_patch.start()
        self.addCleanup(self.mongo_client_patch.stop)
        self.reconcile_task_patch = patch.object(
            task_worker,
            "_new_reconcile_start_task",
            side_effect=_FakeReconcileStartTask,
        )
        self.reconcile_task_patch.start()
        self.addCleanup(self.reconcile_task_patch.stop)

    async def test_claim_recovers_expired_task_at_attempt_limit_without_increment(self):
        expired = task_worker._now()
        task_document = {
            "task_id": "task-max",
            "app_id": "APP12345",
            "action": TaskAction.START_APP,
            "status": TaskStatus.RUNNING,
            "payload": {"app_id": "APP12345"},
            "attempts": task_worker.MAX_TASK_ATTEMPTS,
            "lease_owner": task_worker.WORKER_ID,
            "lease_expires_at": expired,
        }

        with (
            patch.object(
                task_worker,
                "find_one_and_update",
                new=AsyncMock(return_value=task_document),
            ) as claim,
            patch.object(
                task_worker.Task,
                "model_validate",
                side_effect=lambda document: SimpleNamespace(**document),
            ),
        ):
            recovered = await task_worker.claim_next_task()

        query, update = claim.await_args.args
        self.assertEqual(query["status"], TaskStatus.RUNNING)
        self.assertEqual(
            query["attempts"], {"$gte": task_worker.MAX_TASK_ATTEMPTS}
        )
        self.assertIn("$lte", query["lease_expires_at"])
        self.assertNotIn("$inc", update)
        self.assertEqual(recovered.attempts, task_worker.MAX_TASK_ATTEMPTS)

    async def test_malformed_task_is_released_for_retry(self):
        task = _FakeTask()
        collection = _TaskCollection()

        with patch.object(
            task_worker.mongodb_manager,
            "get_collection",
            return_value=collection,
        ):
            await task_worker.process_task(task)

        query, document = _task_update_for_status(collection, TaskStatus.PENDING)
        self.assertEqual(query["lease_owner"], task_worker.WORKER_ID)
        update = document["$set"]
        self.assertEqual(update["status"], TaskStatus.PENDING)
        self.assertIsNone(update["lease_owner"])
        self.assertIsNotNone(update["next_attempt_at"])

    async def _assert_reclaimed_published_lifecycle_task_completes(
        self,
        action,
        terminal_status,
    ):
        task = _FakeTask(
            app_id="APP12345",
            action=action,
            attempts=2,
            task_id=f"published-{action.value}",
            payload={
                "app_id": "APP12345",
                "lifecycle_revision": 20,
            },
        )
        application = SimpleNamespace(
            app_id=task.app_id,
            status=terminal_status,
            runtime_generation=9,
            lifecycle_revision=21,
            lifecycle_completed_task_id=task.task_id,
        )
        collection = _TaskCollection()
        action_runner = AsyncMock()

        with (
            patch.object(
                task_worker.Application,
                "find_one",
                new=AsyncMock(return_value=application),
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(task_worker, "_run_action", new=action_runner),
        ):
            await task_worker.process_task(task)

        action_runner.assert_not_awaited()
        query, document = _task_update_for_status(collection, TaskStatus.SUCCESS)
        self.assertEqual(
            query,
            {
                "task_id": task.task_id,
                "status": TaskStatus.RUNNING,
                "lease_owner": task_worker.WORKER_ID,
            },
        )
        self.assertEqual(document["$set"]["status"], TaskStatus.SUCCESS)
        self.assertEqual(application.lifecycle_revision, 21)

    async def test_reclaimed_start_after_final_publish_completes_without_replay(self):
        await self._assert_reclaimed_published_lifecycle_task_completes(
            TaskAction.START_APP,
            ApplicationStatus.RUNNING,
        )

    async def test_reclaimed_restart_after_final_publish_completes_without_replay(self):
        await self._assert_reclaimed_published_lifecycle_task_completes(
            TaskAction.RESTART_APP,
            ApplicationStatus.RUNNING,
        )

    async def test_reclaimed_stop_after_final_publish_completes_without_replay(self):
        await self._assert_reclaimed_published_lifecycle_task_completes(
            TaskAction.STOP_APP,
            ApplicationStatus.STOPPED,
        )

    async def test_reclaimed_task_uses_immutable_publication_after_later_task(self):
        published_at = task_worker._now()
        task = _FakeTask(
            app_id="APP12345",
            action=TaskAction.START_APP,
            attempts=2,
            task_id="task-a",
            payload={"app_id": "APP12345", "lifecycle_revision": 20},
            published_at=published_at,
            published_status=ApplicationStatus.RUNNING.value,
            published_lifecycle_revision=21,
            published_runtime_generation=9,
        )
        # Task B completed after A and overwrote the application's single
        # last-completed marker. A's own publication evidence must survive.
        application = SimpleNamespace(
            app_id=task.app_id,
            status=ApplicationStatus.STOPPED,
            runtime_generation=9,
            lifecycle_revision=23,
            lifecycle_completed_task_id="task-b",
        )
        collection = _TaskCollection()
        action_runner = AsyncMock()

        with (
            patch.object(
                task_worker.Application,
                "find_one",
                new=AsyncMock(return_value=application),
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(task_worker, "_run_action", new=action_runner),
        ):
            await task_worker.process_task(task)

        action_runner.assert_not_awaited()
        _task_update_for_status(collection, TaskStatus.SUCCESS)
        self.assertEqual(application.lifecycle_revision, 23)

    async def test_revisionless_reclaimed_task_uses_owned_publication(self):
        task = _FakeTask(
            app_id="APP12345",
            action=TaskAction.STOP_APP,
            attempts=2,
            task_id="legacy-task",
            payload={"app_id": "APP12345"},
            published_at=task_worker._now(),
            published_status=ApplicationStatus.STOPPED.value,
            published_lifecycle_revision=8,
            published_runtime_generation=7,
        )
        collection = _TaskCollection()
        action_runner = AsyncMock()

        with (
            patch.object(
                task_worker.Application,
                "find_one",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(task_worker, "_run_action", new=action_runner),
        ):
            await task_worker.process_task(task)

        action_runner.assert_not_awaited()
        _task_update_for_status(collection, TaskStatus.SUCCESS)

    async def test_revisionless_legacy_application_marker_completes_safely(self):
        task = _FakeTask(
            app_id="APP12345",
            action=TaskAction.START_APP,
            attempts=2,
            task_id="legacy-app-marker",
            payload={"app_id": "APP12345"},
        )
        application = SimpleNamespace(
            app_id=task.app_id,
            status=ApplicationStatus.RUNNING,
            runtime_generation=4,
            lifecycle_revision=9,
            lifecycle_completed_task_id=task.task_id,
        )
        collection = _TaskCollection()
        action_runner = AsyncMock()

        with (
            patch.object(
                task_worker.Application,
                "find_one",
                new=AsyncMock(return_value=application),
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(task_worker, "_run_action", new=action_runner),
        ):
            await task_worker.process_task(task)

        action_runner.assert_not_awaited()
        _task_update_for_status(collection, TaskStatus.SUCCESS)

    async def test_revisionless_task_without_owned_publication_is_not_completed(self):
        task = _FakeTask(
            app_id="APP12345",
            action=TaskAction.START_APP,
            payload={"app_id": "APP12345"},
        )
        app = SimpleNamespace(
            app_id=task.app_id,
            status=ApplicationStatus.RUNNING,
            runtime_generation=4,
            lifecycle_revision=9,
            lifecycle_completed_task_id="different-task",
        )

        completed = await task_worker._complete_already_published_lifecycle_task(
            _TaskCollection(),
            task,
            app,
        )

        self.assertFalse(completed)

    async def test_future_pending_lifecycle_backoff_blocks_reconcile(self):
        application = SimpleNamespace(
            app_id="APP12345",
            status=ApplicationStatus.STARTING,
            runtime_generation=7,
            runtime_token_hash=None,
            lifecycle_revision=12,
        )
        future_task = _FakeTask(
            app_id=application.app_id,
            action=TaskAction.START_APP,
            attempts=2,
            payload={
                "app_id": application.app_id,
                "lifecycle_revision": application.lifecycle_revision,
            },
        )
        future_task.status = TaskStatus.PENDING
        future_task.next_attempt_at = task_worker._now() + timedelta(minutes=5)
        captured_query = {}

        class BackoffAwareTask:
            @classmethod
            def find(cls, query):
                captured_query.update(query)
                pending_clause = next(
                    clause
                    for clause in query["$or"]
                    if clause.get("status") == TaskStatus.PENDING
                )
                has_due_filter = any(
                    "next_attempt_at" in condition
                    for condition in pending_clause.get("$or", [])
                )
                return _ApplicationQuery([] if has_due_filter else [future_task])

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([application])

        application_collection = _ApplicationCollection(application)
        with (
            patch.object(task_worker, "Task", BackoffAwareTask),
            patch.object(task_worker, "Application", FakeApplication),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=application_collection,
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                return_value=[],
            ),
            patch.object(task_worker, "_enqueue_start", new=AsyncMock()) as enqueue,
        ):
            await task_worker.reconcile_running_apps()

        pending_clause = next(
            clause
            for clause in captured_query["$or"]
            if clause.get("status") == TaskStatus.PENDING
        )
        self.assertNotIn("$or", pending_clause)
        self.assertEqual(application.lifecycle_revision, 12)
        self.assertEqual(application_collection.update_calls, [])
        enqueue.assert_not_awaited()

    async def test_claim_still_respects_pending_backoff(self):
        with patch.object(
            task_worker,
            "find_one_and_update",
            new=AsyncMock(side_effect=[None, None]),
        ) as claim:
            self.assertIsNone(await task_worker.claim_next_task())

        claim_query = claim.await_args_list[1].args[0]
        pending_clause = next(
            clause
            for clause in claim_query["$or"]
            if clause.get("status") == TaskStatus.PENDING
        )
        self.assertIn("$or", pending_clause)
        self.assertTrue(
            any(
                isinstance(condition.get("next_attempt_at"), dict)
                and condition["next_attempt_at"].get("$lte")
                for condition in pending_clause["$or"]
            )
        )

    async def test_publication_requires_current_task_lease_before_app_write(self):
        application = SimpleNamespace(
            app_id="APP12345",
            status=ApplicationStatus.STARTING,
            runtime_generation=8,
            lifecycle_revision=20,
        )
        application_collection = _ApplicationCollection(application)
        task_collection = _TaskCollection(matched_count=0)

        def get_collection(model):
            if model is task_worker.Task:
                return task_collection
            return application_collection

        with patch.object(
            task_worker.mongodb_manager,
            "get_collection",
            side_effect=get_collection,
        ):
            with self.assertRaises(task_worker.LeaseLostError):
                await task_worker._mark_runtime_status(
                    application.app_id,
                    application.runtime_generation,
                    ApplicationStatus.RUNNING,
                    ApplicationStatus.STARTING,
                    application.lifecycle_revision,
                    "task-lost",
                )

        self.assertEqual(application_collection.update_calls, [])
        query, update = task_collection.update_calls[0]
        self.assertEqual(query["lease_owner"], task_worker.WORKER_ID)
        self.assertEqual(query["status"], TaskStatus.RUNNING)
        self.assertEqual(query["published_at"], None)
        self.assertEqual(
            update["$set"]["published_lifecycle_revision"],
            21,
        )

    async def test_start_publish_lease_loss_never_cleans_runtime_generation(self):
        application = SimpleNamespace(
            app_id="APP12345",
            db_password="db-secret",
            status=ApplicationStatus.STARTING,
            runtime_generation=7,
            lifecycle_revision=20,
        )
        runtime_state = {
            "runtime_generation": 7,
            "runtime_token_hash": hashlib.sha256(b"runtime-token").hexdigest(),
            "source_status": ApplicationStatus.STARTING,
            "lifecycle_revision": 20,
        }
        container_info = {
            "id": "successor-owned-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 8,
        }

        with (
            patch.object(
                task_worker,
                "check_mongodb_user_exists",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                task_worker.app_storage_service,
                "ensure_ready",
                new=AsyncMock(),
            ),
            patch.object(
                task_worker,
                "start_app_container",
                new=AsyncMock(return_value=container_info),
            ),
            patch.object(
                task_worker,
                "_mark_runtime_running",
                new=AsyncMock(
                    side_effect=task_worker.LeaseLostError("lease transferred")
                ),
            ),
            patch.object(
                task_worker,
                "_cleanup_runtime_generation",
                new=AsyncMock(),
            ) as cleanup,
        ):
            with self.assertRaises(task_worker.LeaseLostError):
                await task_worker._run_action(
                    _FakeTask(
                        app_id=application.app_id,
                        action=TaskAction.START_APP,
                    ),
                    application.app_id,
                    application,
                    runtime_state,
                )

        cleanup.assert_not_awaited()

    async def test_ambiguous_committed_publish_reloads_evidence_without_cleanup(self):
        application = SimpleNamespace(
            app_id="APP12345",
            db_password="db-secret",
            status=ApplicationStatus.STARTING,
            runtime_generation=8,
            runtime_token_hash=hashlib.sha256(b"runtime-token").hexdigest(),
            lifecycle_revision=20,
            lifecycle_completed_task_id=None,
        )
        task_document = {
            "task_id": "task-ambiguous",
            "status": TaskStatus.RUNNING,
            "lease_owner": task_worker.WORKER_ID,
            "published_at": None,
            "published_status": None,
            "published_lifecycle_revision": None,
            "published_runtime_generation": None,
        }

        class StatefulTaskCollection:
            async def update_one(self, query, update, session=None):
                if any(task_document.get(key) != value for key, value in query.items()):
                    return SimpleNamespace(matched_count=0)
                task_document.update(update["$set"])
                return SimpleNamespace(matched_count=1)

            async def find_one(self, query):
                for key, value in query.items():
                    current = task_document.get(key)
                    if isinstance(value, dict) and "$ne" in value:
                        if current == value["$ne"]:
                            return None
                    elif current != value:
                        return None
                return dict(task_document)

        class StatefulApplicationCollection(_ApplicationCollection):
            async def find_one(self, query):
                if any(
                    getattr(self.application, key, None) != value
                    for key, value in query.items()
                ):
                    return None
                return {
                    key: getattr(self.application, key, None)
                    for key in (
                        "app_id",
                        "status",
                        "runtime_generation",
                        "lifecycle_revision",
                        "lifecycle_completed_task_id",
                    )
                }

        task_collection = StatefulTaskCollection()
        application_collection = StatefulApplicationCollection(application)

        def get_collection(model):
            if model is task_worker.Task:
                return task_collection
            return application_collection

        container_info = {
            "id": "committed-container",
            "name": "hyac-app-runtime-app12345",
            "generation": application.runtime_generation,
        }
        runtime_state = {
            "runtime_generation": application.runtime_generation,
            "runtime_token_hash": application.runtime_token_hash,
            "source_status": ApplicationStatus.STARTING,
            "lifecycle_revision": application.lifecycle_revision,
        }

        with (
            patch.object(
                task_worker.mongodb_manager,
                "client",
                _AmbiguousCommittedClient(),
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                side_effect=get_collection,
            ),
            patch.object(
                task_worker,
                "check_mongodb_user_exists",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                task_worker.app_storage_service,
                "ensure_ready",
                new=AsyncMock(),
            ),
            patch.object(
                task_worker,
                "start_app_container",
                new=AsyncMock(return_value=container_info),
            ),
            patch.object(
                task_worker,
                "_cleanup_runtime_generation",
                new=AsyncMock(),
            ) as cleanup,
        ):
            await task_worker._run_action(
                _FakeTask(
                    app_id=application.app_id,
                    task_id=task_document["task_id"],
                    action=TaskAction.START_APP,
                ),
                application.app_id,
                application,
                runtime_state,
            )

        cleanup.assert_not_awaited()
        self.assertEqual(task_document["published_status"], "running")
        self.assertEqual(task_document["published_lifecycle_revision"], 21)
        self.assertEqual(application.status, ApplicationStatus.RUNNING)
        self.assertEqual(application.lifecycle_revision, 21)
        self.assertEqual(
            application.lifecycle_completed_task_id,
            task_document["task_id"],
        )

    async def test_unresolved_ambiguous_publish_never_attempts_cleanup(self):
        application = SimpleNamespace(
            app_id="APP12345",
            db_password="db-secret",
            status=ApplicationStatus.STARTING,
            runtime_generation=7,
            lifecycle_revision=20,
        )
        ambiguous_error = OperationFailure(
            "commit result remains unknown",
            91,
            {"errorLabels": ["UnknownTransactionCommitResult"]},
        )

        with (
            patch.object(
                task_worker,
                "check_mongodb_user_exists",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                task_worker.app_storage_service,
                "ensure_ready",
                new=AsyncMock(),
            ),
            patch.object(
                task_worker,
                "start_app_container",
                new=AsyncMock(
                    return_value={
                        "id": "possibly-committed-container",
                        "name": "hyac-app-runtime-app12345",
                        "generation": 8,
                    }
                ),
            ),
            patch.object(
                task_worker,
                "_mark_runtime_running",
                new=AsyncMock(side_effect=ambiguous_error),
            ),
            patch.object(
                task_worker,
                "_reserve_unpublished_runtime_cleanup",
                new=AsyncMock(),
            ) as reserve_cleanup,
            patch.object(
                task_worker,
                "_cleanup_runtime_generation",
                new=AsyncMock(),
            ) as cleanup,
        ):
            with self.assertRaises(OperationFailure) as raised:
                await task_worker._run_action(
                    _FakeTask(
                        app_id=application.app_id,
                        action=TaskAction.START_APP,
                    ),
                    application.app_id,
                    application,
                    {
                        "runtime_generation": 7,
                        "source_status": ApplicationStatus.STARTING,
                        "lifecycle_revision": 20,
                    },
                )

        self.assertIs(raised.exception, ambiguous_error)
        reserve_cleanup.assert_not_awaited()
        cleanup.assert_not_awaited()

    async def test_publish_failure_skips_cleanup_after_lease_owner_changes(self):
        application = SimpleNamespace(
            app_id="APP12345",
            db_password="db-secret",
            status=ApplicationStatus.STARTING,
            runtime_generation=7,
            lifecycle_revision=20,
        )
        container_info = {
            "id": "successor-owned-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 8,
        }
        successor_task = {
            "task_id": "task-1",
            "status": TaskStatus.RUNNING,
            "lease_owner": "successor-worker",
            "published_at": None,
        }

        class SuccessorOwnedTaskCollection:
            def __init__(self):
                self.query = None

            async def update_one(self, query, _update):
                self.query = query
                matches = all(successor_task.get(key) == value for key, value in query.items())
                return SimpleNamespace(matched_count=int(matches))

        task_collection = SuccessorOwnedTaskCollection()

        with (
            patch.object(
                task_worker,
                "check_mongodb_user_exists",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                task_worker.app_storage_service,
                "ensure_ready",
                new=AsyncMock(),
            ),
            patch.object(
                task_worker,
                "start_app_container",
                new=AsyncMock(return_value=container_info),
            ),
            patch.object(
                task_worker,
                "_mark_runtime_running",
                new=AsyncMock(side_effect=RuntimeError("publish failed")),
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=task_collection,
            ),
            patch.object(
                task_worker,
                "_cleanup_runtime_generation",
                new=AsyncMock(),
            ) as cleanup,
        ):
            with self.assertRaises(task_worker.LeaseLostError):
                await task_worker._run_action(
                    _FakeTask(
                        app_id=application.app_id,
                        action=TaskAction.START_APP,
                    ),
                    application.app_id,
                    application,
                    {
                        "runtime_generation": 7,
                        "source_status": ApplicationStatus.STARTING,
                        "lifecycle_revision": 20,
                    },
                )

        cleanup.assert_not_awaited()
        self.assertEqual(
            task_collection.query,
            {
                "task_id": "task-1",
                "status": TaskStatus.RUNNING,
                "lease_owner": task_worker.WORKER_ID,
                "published_at": None,
            },
        )

    async def test_publish_cleanup_renews_owned_unpublished_lease_first(self):
        application = SimpleNamespace(
            app_id="APP12345",
            db_password="db-secret",
            status=ApplicationStatus.STARTING,
            runtime_generation=7,
            lifecycle_revision=20,
        )
        task_document = {
            "task_id": "task-1",
            "status": TaskStatus.RUNNING,
            "lease_owner": task_worker.WORKER_ID,
            "published_at": None,
            "lease_expires_at": task_worker._now() - timedelta(seconds=1),
        }
        call_order = []

        class OwnedTaskCollection:
            def __init__(self):
                self.query = None

            async def update_one(self, query, update, session=None):
                self.query = query
                matches = all(task_document.get(key) == value for key, value in query.items())
                if matches:
                    task_document.update(update["$set"])
                    call_order.append("reserve")
                return SimpleNamespace(matched_count=int(matches))

        async def record_cleanup(*_args, **_kwargs):
            call_order.append("cleanup")

        task_collection = OwnedTaskCollection()
        with (
            patch.object(
                task_worker,
                "check_mongodb_user_exists",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                task_worker.app_storage_service,
                "ensure_ready",
                new=AsyncMock(),
            ),
            patch.object(
                task_worker,
                "start_app_container",
                new=AsyncMock(
                    return_value={
                        "id": "owned-container",
                        "name": "hyac-app-runtime-app12345",
                        "generation": 8,
                    }
                ),
            ),
            patch.object(
                task_worker,
                "_mark_runtime_running",
                new=AsyncMock(side_effect=RuntimeError("publish rejected")),
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=task_collection,
            ),
            patch.object(
                task_worker,
                "_cleanup_runtime_generation",
                new=AsyncMock(side_effect=record_cleanup),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "publish rejected"):
                await task_worker._run_action(
                    _FakeTask(
                        app_id=application.app_id,
                        action=TaskAction.START_APP,
                    ),
                    application.app_id,
                    application,
                    {
                        "runtime_generation": 7,
                        "source_status": ApplicationStatus.STARTING,
                        "lifecycle_revision": 20,
                    },
                )

        self.assertEqual(call_order, ["reserve", "cleanup"])
        self.assertEqual(
            task_collection.query,
            {
                "task_id": "task-1",
                "status": TaskStatus.RUNNING,
                "lease_owner": task_worker.WORKER_ID,
                "published_at": None,
            },
        )
        self.assertGreater(task_document["lease_expires_at"], task_worker._now())

    async def test_cleanup_handoff_cannot_delete_successor_same_generation(self):
        task_document = {
            "task_id": "task-cleanup",
            "status": TaskStatus.RUNNING,
            "lease_owner": task_worker.WORKER_ID,
            "lease_expires_at": task_worker._now() + timedelta(seconds=60),
        }
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=8,
            runtime_token_hash="generation-token",
            runtime_cleanup_task_id=None,
            runtime_cleanup_lease_owner=None,
            pending_traefik_cleanup_generation=None,
            status=ApplicationStatus.STARTING,
            lifecycle_revision=20,
        )
        ownership_check_started = asyncio.Event()
        release_ownership_check = asyncio.Event()

        class CleanupTaskCollection:
            async def find_one(self, query, session=None):
                ownership_check_started.set()
                await release_ownership_check.wait()
                for key, value in query.items():
                    current = task_document.get(key)
                    if isinstance(value, dict) and "$gt" in value:
                        if current is None or current <= value["$gt"]:
                            return None
                    elif current != value:
                        return None
                return dict(task_document)

        class CleanupApplicationCollection(_ApplicationCollection):
            pass

        task_collection = CleanupTaskCollection()
        application_collection = CleanupApplicationCollection(application)

        def get_collection(model):
            if model is docker_manager.Task:
                return task_collection
            return application_collection

        stop = AsyncMock(return_value=True)
        remove = AsyncMock(return_value=True)
        with (
            patch.object(
                docker_manager.mongodb_manager,
                "client",
                _NoOpTransactionClient(),
            ),
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                side_effect=get_collection,
            ),
            patch.object(
                docker_manager.docker_manager,
                "stop_container",
                new=stop,
            ),
            patch.object(
                docker_manager.docker_manager,
                "remove_container",
                new=remove,
            ),
            patch.object(docker_manager, "remove_traefik_web_config_for_generation"),
        ):
            cleanup = asyncio.create_task(
                docker_manager._cleanup_runtime_generation(
                    application.app_id,
                    "hyac-app-runtime-app12345",
                    application.runtime_generation,
                    "successor-container",
                    application.runtime_token_hash,
                    cleanup_task_id=task_document["task_id"],
                    cleanup_lease_owner=task_worker.WORKER_ID,
                )
            )
            await asyncio.wait_for(ownership_check_started.wait(), timeout=0.2)
            task_document["lease_owner"] = "successor-worker"
            application.status = ApplicationStatus.RUNNING
            application.lifecycle_revision = 21
            application.lifecycle_completed_task_id = task_document["task_id"]
            release_ownership_check.set()
            self.assertFalse(await asyncio.wait_for(cleanup, timeout=0.2))

        stop.assert_not_awaited()
        remove.assert_not_awaited()
        self.assertEqual(application.status, ApplicationStatus.RUNNING)
        self.assertIsNone(application.runtime_cleanup_task_id)

    async def test_cleanup_revalidates_lease_after_acquisition_before_docker(self):
        task_document = {
            "task_id": "task-cleanup",
            "status": TaskStatus.RUNNING,
            "lease_owner": "worker-a",
            "lease_expires_at": task_worker._now() + timedelta(seconds=60),
            "published_at": None,
        }
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=8,
            runtime_token_hash="generation-token",
            runtime_cleanup_task_id=None,
            runtime_cleanup_lease_owner=None,
            pending_traefik_cleanup_generation=None,
        )

        class CleanupTaskCollection:
            async def find_one(self, query, session=None):
                for key, value in query.items():
                    current = task_document.get(key)
                    if isinstance(value, dict) and "$gt" in value:
                        if current is None or current <= value["$gt"]:
                            return None
                    elif current != value:
                        return None
                return dict(task_document)

        class CleanupApplicationCollection(_ApplicationCollection):
            async def update_one(self, query, update, session=None):
                result = await super().update_one(query, update, session=session)
                if update.get("$set", {}).get(
                    "pending_traefik_cleanup_generation"
                ) == 8:
                    task_document["lease_owner"] = "worker-b"
                return result

        task_collection = CleanupTaskCollection()
        application_collection = CleanupApplicationCollection(application)

        def get_collection(model):
            if model is docker_manager.Task:
                return task_collection
            return application_collection

        stop = AsyncMock(return_value=True)
        remove = AsyncMock(return_value=True)
        with (
            patch.object(
                docker_manager.mongodb_manager,
                "client",
                _NoOpTransactionClient(),
            ),
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                side_effect=get_collection,
            ),
            patch.object(
                docker_manager.docker_manager,
                "stop_container",
                new=stop,
            ),
            patch.object(
                docker_manager.docker_manager,
                "remove_container",
                new=remove,
            ),
        ):
            cleaned = await docker_manager._cleanup_runtime_generation(
                application.app_id,
                "hyac-app-runtime-app12345",
                8,
                "container-a",
                application.runtime_token_hash,
                cleanup_task_id=task_document["task_id"],
                cleanup_lease_owner="worker-a",
            )

        self.assertFalse(cleaned)
        stop.assert_not_awaited()
        remove.assert_not_awaited()

    async def test_reconciliation_registers_existing_secure_container(self):
        runtime_token = "runtime-secret"
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_token_hash=hashlib.sha256(runtime_token.encode()).hexdigest(),
            runtime_generation=7,
            status=ApplicationStatus.RUNNING,
            save=AsyncMock(),
        )

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([application])

        containers = [
            {
                "id": "container-1",
                "name": "hyac-app-runtime-app12345",
                "status": "running",
                "health_status": "healthy",
            }
        ]
        task_worker.running_apps.clear()
        try:
            with (
                patch.object(task_worker, "Application", FakeApplication),
                patch.object(
                    task_worker.docker_manager,
                    "list_containers",
                    return_value=containers,
                ),
                patch.object(
                    task_worker.docker_manager,
                    "get_container_environment",
                    return_value={
                        "RUNTIME_TOKEN": runtime_token,
                        "RUNTIME_GENERATION": "7",
                    },
                ),
                patch.object(
                    task_worker,
                    "_active_lifecycle_app_ids",
                    new=AsyncMock(return_value=set()),
                    create=True,
                ),
                patch.object(task_worker, "_enqueue_start", new=AsyncMock()),
                patch("hmac.compare_digest", wraps=hmac.compare_digest) as compare,
            ):
                await task_worker.reconcile_running_apps()

            self.assertEqual(
                task_worker.running_apps[application.app_id],
                {
                    "id": "container-1",
                    "name": "hyac-app-runtime-app12345",
                    "generation": 7,
                },
            )
            compare.assert_called_once()
        finally:
            task_worker.running_apps.clear()

    async def test_task_completion_is_guarded_by_lease_ownership(self):
        task = _FakeTask(app_id="APP12345")
        app = SimpleNamespace(app_id="APP12345")
        collection = _TaskCollection()

        with (
            patch.object(
                task_worker.Application, "find_one", new=AsyncMock(return_value=app)
            ),
            patch.object(task_worker, "_run_action", new=AsyncMock()),
            patch.object(task_worker, "_heartbeat", new=AsyncMock()),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
        ):
            await task_worker.process_task(task)

        query, update = collection.update_calls[-1]
        self.assertEqual(
            query,
            {
                "task_id": task.task_id,
                "status": TaskStatus.RUNNING,
                "lease_owner": task_worker.WORKER_ID,
            },
        )
        self.assertEqual(update["$set"]["status"], TaskStatus.SUCCESS)

    async def test_task_failure_is_guarded_by_lease_ownership(self):
        task = _FakeTask(
            app_id="APP12345", action=TaskAction.STOP_APP, attempts=2
        )
        app = SimpleNamespace(app_id="APP12345")
        collection = _TaskCollection()

        with (
            patch.object(
                task_worker.Application, "find_one", new=AsyncMock(return_value=app)
            ),
            patch.object(
                task_worker,
                "_run_action",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch.object(task_worker, "_heartbeat", new=AsyncMock()),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
        ):
            await task_worker.process_task(task)

        query, update = collection.update_calls[-1]
        self.assertEqual(query["task_id"], task.task_id)
        self.assertEqual(query["status"], TaskStatus.RUNNING)
        self.assertEqual(query["lease_owner"], task_worker.WORKER_ID)
        self.assertEqual(update["$set"]["status"], TaskStatus.PENDING)

    async def test_start_and_restart_preserve_authoritative_runtime_identity(self):
        for action in (TaskAction.START_APP, TaskAction.RESTART_APP):
            with self.subTest(action=action):
                old_token_hash = hashlib.sha256(b"old-token").hexdigest()
                new_token_hash = hashlib.sha256(b"new-token").hexdigest()
                persisted = SimpleNamespace(
                    app_id="APP12345",
                    runtime_generation=7,
                    runtime_token_hash=old_token_hash,
                    status=ApplicationStatus.STARTING,
                )
                stale_snapshot = SimpleNamespace(
                    app_id=persisted.app_id,
                    db_password="db-secret",
                    runtime_generation=7,
                    runtime_token_hash=old_token_hash,
                    status=ApplicationStatus.STARTING,
                    save=AsyncMock(),
                )

                async def save_stale_snapshot():
                    persisted.runtime_generation = stale_snapshot.runtime_generation
                    persisted.runtime_token_hash = stale_snapshot.runtime_token_hash
                    persisted.status = stale_snapshot.status

                stale_snapshot.save.side_effect = save_stale_snapshot
                collection = _ApplicationCollection(persisted)

                async def start_runtime(_application, **kwargs):
                    persisted.runtime_generation = 8
                    persisted.runtime_token_hash = new_token_hash
                    runtime_state = kwargs["runtime_state"]
                    runtime_state["runtime_generation"] = 8
                    runtime_state["runtime_token_hash"] = new_token_hash
                    return {
                        "id": "new-container",
                        "name": "hyac-app-runtime-app12345",
                        "generation": 8,
                    }

                with (
                    patch.object(
                        task_worker,
                        "check_mongodb_user_exists",
                        new=AsyncMock(return_value=True),
                    ),
                    patch.object(
                        task_worker.app_storage_service,
                        "ensure_ready",
                        new=AsyncMock(),
                    ),
                    patch.object(
                        task_worker,
                        "stop_app_container",
                        new=AsyncMock(),
                    ),
                    patch.object(
                        task_worker,
                        "start_app_container",
                        side_effect=start_runtime,
                    ),
                    patch.object(
                        task_worker.mongodb_manager,
                        "get_collection",
                        return_value=collection,
                    ),
                ):
                    await task_worker._run_action(
                        _FakeTask(app_id=persisted.app_id, action=action),
                        persisted.app_id,
                        stale_snapshot,
                    )

                self.assertEqual(persisted.runtime_generation, 8)
                self.assertEqual(persisted.runtime_token_hash, new_token_hash)
                self.assertEqual(persisted.status, ApplicationStatus.RUNNING)
                stale_snapshot.save.assert_not_awaited()
                query, update = collection.update_calls[-1]
                self.assertEqual(
                    query,
                    {
                        "app_id": persisted.app_id,
                        "runtime_generation": 8,
                        "status": ApplicationStatus.STARTING,
                        "lifecycle_revision": 0,
                        "runtime_cleanup_task_id": None,
                        "runtime_cleanup_lease_owner": None,
                        "pending_traefik_cleanup_generation": None,
                    },
                )
                self.assertEqual(
                    update["$set"]["status"], ApplicationStatus.RUNNING
                )
                self.assertEqual(
                    update["$set"]["lifecycle_completed_task_id"],
                    "task-1",
                )
                task_query, task_update = collection.task_update_calls[-1]
                self.assertEqual(
                    task_query,
                    {
                        "task_id": "task-1",
                        "status": TaskStatus.RUNNING,
                        "lease_owner": task_worker.WORKER_ID,
                        "published_at": None,
                    },
                )
                self.assertEqual(
                    task_update["$set"]["published_status"],
                    ApplicationStatus.RUNNING.value,
                )
                self.assertEqual(
                    task_update["$set"]["published_lifecycle_revision"],
                    1,
                )
                self.assertEqual(
                    task_update["$set"]["published_runtime_generation"],
                    8,
                )
                self.assertIs(
                    collection.task_update_sessions[-1],
                    collection.update_sessions[-1],
                )
                self.assertIsNotNone(collection.update_sessions[-1])

    async def test_stop_preserves_authoritative_revoked_token(self):
        token_hash = hashlib.sha256(b"runtime-token").hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=token_hash,
            status=ApplicationStatus.STOPPING,
        )
        stale_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            runtime_generation=7,
            runtime_token_hash=token_hash,
            status=ApplicationStatus.STOPPING,
            save=AsyncMock(),
        )

        async def save_stale_snapshot():
            persisted.runtime_generation = stale_snapshot.runtime_generation
            persisted.runtime_token_hash = stale_snapshot.runtime_token_hash
            persisted.status = stale_snapshot.status

        async def stop_runtime(_app_id, *_args, **_kwargs):
            persisted.runtime_token_hash = None
            return True

        stale_snapshot.save.side_effect = save_stale_snapshot
        collection = _ApplicationCollection(persisted)
        with (
            patch.object(
                task_worker,
                "stop_app_container",
                side_effect=stop_runtime,
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
        ):
            await task_worker._run_action(
                _FakeTask(app_id=persisted.app_id, action=TaskAction.STOP_APP),
                persisted.app_id,
                stale_snapshot,
            )

        self.assertEqual(persisted.runtime_generation, 7)
        self.assertIsNone(persisted.runtime_token_hash)
        self.assertEqual(persisted.status, ApplicationStatus.STOPPED)
        stale_snapshot.save.assert_not_awaited()
        query, update = collection.update_calls[-1]
        self.assertEqual(
            query,
            {
                "app_id": persisted.app_id,
                "runtime_generation": 7,
                "status": ApplicationStatus.STOPPING,
                "lifecycle_revision": 0,
                "runtime_cleanup_task_id": None,
                "runtime_cleanup_lease_owner": None,
                "pending_traefik_cleanup_generation": None,
            },
        )
        self.assertEqual(update["$set"]["status"], ApplicationStatus.STOPPED)
        self.assertEqual(
            update["$set"]["lifecycle_completed_task_id"],
            "task-1",
        )
        task_query, task_update = collection.task_update_calls[-1]
        self.assertEqual(
            task_query,
            {
                "task_id": "task-1",
                "status": TaskStatus.RUNNING,
                "lease_owner": task_worker.WORKER_ID,
                "published_at": None,
            },
        )
        self.assertEqual(
            task_update["$set"]["published_status"],
            ApplicationStatus.STOPPED.value,
        )
        self.assertEqual(
            task_update["$set"]["published_lifecycle_revision"],
            1,
        )
        self.assertEqual(
            task_update["$set"]["published_runtime_generation"],
            7,
        )
        self.assertIs(
            collection.task_update_sessions[-1],
            collection.update_sessions[-1],
        )
        self.assertIsNotNone(collection.update_sessions[-1])

    async def test_lost_lease_cancels_an_in_flight_action(self):
        task = _FakeTask(app_id="APP12345")
        app = SimpleNamespace(app_id="APP12345")
        action_started = asyncio.Event()
        action_cancelled = asyncio.Event()

        async def blocking_action(*_args):
            action_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                action_cancelled.set()
                raise

        async def lose_lease(_task_id, *args):
            await action_started.wait()
            if args:
                args[0].set()

        with (
            patch.object(
                task_worker.Application, "find_one", new=AsyncMock(return_value=app)
            ),
            patch.object(task_worker, "_run_action", side_effect=blocking_action),
            patch.object(task_worker, "_heartbeat", side_effect=lose_lease),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=_TaskCollection(),
            ),
        ):
            await asyncio.wait_for(task_worker.process_task(task), timeout=0.2)

        self.assertTrue(action_cancelled.is_set())

    async def test_heartbeat_failure_notifies_lease_loss(self):
        for failure_point in ("collection", "update"):
            with self.subTest(failure_point=failure_point):
                lease_lost = asyncio.Event()
                collection = _TaskCollection()
                collection.update_one = AsyncMock(
                    side_effect=RuntimeError("database down")
                )
                collection_result = (
                    RuntimeError("database down")
                    if failure_point == "collection"
                    else collection
                )

                with (
                    patch.object(
                        task_worker.mongodb_manager,
                        "get_collection",
                        side_effect=(
                            collection_result
                            if isinstance(collection_result, Exception)
                            else None
                        ),
                        return_value=(
                            None
                            if isinstance(collection_result, Exception)
                            else collection_result
                        ),
                    ),
                    patch.object(task_worker.asyncio, "sleep", new=AsyncMock()),
                ):
                    await task_worker._heartbeat("task-1", lease_lost)

        self.assertTrue(lease_lost.is_set())

    async def test_lookup_handoff_revalidates_before_any_start_side_effect(self):
        task = _FakeTask(
            app_id="APP12345",
            task_id="slow-lookup-task",
            action=TaskAction.START_APP,
            payload={"app_id": "APP12345", "lifecycle_revision": 20},
        )
        application = SimpleNamespace(
            app_id=task.app_id,
            db_password="db-secret",
            status=ApplicationStatus.STARTING,
            runtime_generation=7,
            lifecycle_revision=20,
        )
        task_document = {
            "task_id": task.task_id,
            "status": TaskStatus.RUNNING,
            "lease_owner": task_worker.WORKER_ID,
            "lease_expires_at": task_worker._now() + timedelta(seconds=60),
        }
        lookup_started = asyncio.Event()
        release_lookup = asyncio.Event()
        maintenance_started = asyncio.Event()
        maintenance_was_active_at_lookup = []

        class LeaseCollection:
            def __init__(self):
                self.update_calls = []

            async def update_one(self, query, update, session=None):
                self.update_calls.append((query, update))
                matches = all(task_document.get(key) == value for key, value in query.items())
                if matches:
                    task_document.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=int(matches))

        async def blocked_lookup(*_args, **_kwargs):
            await asyncio.sleep(0)
            maintenance_was_active_at_lookup.append(maintenance_started.is_set())
            lookup_started.set()
            await release_lookup.wait()
            return application

        async def maintain_lease(_task_id, _lease_lost):
            maintenance_started.set()
            await asyncio.Event().wait()

        collection = LeaseCollection()
        mongo_user = AsyncMock(return_value=True)
        storage_ready = AsyncMock()
        start_container = AsyncMock()

        with (
            patch.object(
                task_worker.Application,
                "find_one",
                side_effect=blocked_lookup,
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(task_worker, "_heartbeat", side_effect=maintain_lease),
            patch.object(
                task_worker,
                "check_mongodb_user_exists",
                new=mongo_user,
            ),
            patch.object(
                task_worker.app_storage_service,
                "ensure_ready",
                new=storage_ready,
            ),
            patch.object(
                task_worker,
                "start_app_container",
                new=start_container,
            ),
        ):
            processing = asyncio.create_task(task_worker.process_task(task))
            await asyncio.wait_for(lookup_started.wait(), timeout=0.2)
            task_document["lease_owner"] = "successor-worker"
            task_document["lease_expires_at"] = task_worker._now() + timedelta(
                seconds=60
            )
            release_lookup.set()
            await asyncio.wait_for(processing, timeout=0.2)

        self.assertEqual(maintenance_was_active_at_lookup, [True])
        self.assertGreaterEqual(len(collection.update_calls), 2)
        for query, _update in collection.update_calls[:2]:
            self.assertEqual(
                query,
                {
                    "task_id": task.task_id,
                    "status": TaskStatus.RUNNING,
                    "lease_owner": task_worker.WORKER_ID,
                },
            )
        mongo_user.assert_not_awaited()
        storage_ready.assert_not_awaited()
        start_container.assert_not_awaited()

    async def test_reconciliation_does_not_restart_terminal_error_apps(self):
        captured_query = None

        class FakeApplication:
            @classmethod
            def find(cls, query):
                nonlocal captured_query
                captured_query = query
                return _ApplicationQuery([])

        with (
            patch.object(task_worker, "Application", FakeApplication),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
                create=True,
            ),
        ):
            await task_worker.reconcile_running_apps()

        statuses = captured_query["status"]["$in"]
        self.assertNotIn(ApplicationStatus.ERROR, statuses)

    async def test_worker_reconciles_periodically_while_idle(self):
        reconciliations = 0
        reconciled_twice = asyncio.Event()

        async def reconcile():
            nonlocal reconciliations
            reconciliations += 1
            if reconciliations >= 2:
                reconciled_twice.set()

        with (
            patch.object(task_worker, "RECONCILE_SECONDS", 0.005, create=True),
            patch.object(task_worker, "TASK_POLL_SECONDS", 0.005, create=True),
            patch.object(task_worker, "reconcile_running_apps", side_effect=reconcile),
            patch.object(task_worker, "claim_next_task", new=AsyncMock(return_value=None)),
        ):
            watcher = asyncio.create_task(task_worker.watch_for_tasks())
            try:
                await asyncio.wait_for(reconciled_twice.wait(), timeout=0.2)
            finally:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)

        self.assertGreaterEqual(reconciliations, 2)

    async def test_slow_app_does_not_block_reconciliation_or_another_app(self):
        slow = _FakeTask(app_id="APP-SLOW", task_id="task-slow")
        fast = _FakeTask(app_id="APP-FAST", task_id="task-fast")
        queued = [slow, fast]
        slow_started = asyncio.Event()
        release_slow = asyncio.Event()
        fast_processed = asyncio.Event()
        reconciled_twice = asyncio.Event()
        reconciliation_count = 0

        async def claim(excluded_app_ids=None):
            excluded_app_ids = excluded_app_ids or set()
            for candidate in list(queued):
                if candidate.app_id not in excluded_app_ids:
                    queued.remove(candidate)
                    return candidate
            return None

        async def process(task):
            if task.app_id == "APP-SLOW":
                slow_started.set()
                await release_slow.wait()
            else:
                fast_processed.set()

        async def reconcile():
            nonlocal reconciliation_count
            reconciliation_count += 1
            if reconciliation_count >= 2:
                reconciled_twice.set()

        with (
            patch.object(task_worker, "RECONCILE_SECONDS", 0.01),
            patch.object(task_worker, "TASK_POLL_SECONDS", 0.005, create=True),
            patch.object(task_worker, "MAX_CONCURRENT_TASKS", 2, create=True),
            patch.object(task_worker, "claim_next_task", side_effect=claim),
            patch.object(task_worker, "process_task", side_effect=process),
            patch.object(task_worker, "reconcile_running_apps", side_effect=reconcile),
        ):
            watcher = asyncio.create_task(task_worker.watch_for_tasks())
            try:
                await asyncio.wait_for(slow_started.wait(), timeout=0.2)
                await asyncio.wait_for(
                    asyncio.gather(
                        fast_processed.wait(), reconciled_twice.wait()
                    ),
                    timeout=0.2,
                )
            finally:
                release_slow.set()
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)

    async def test_same_app_tasks_are_serialized(self):
        first = _FakeTask(app_id="APP-ONE", task_id="task-first")
        second = _FakeTask(app_id="APP-ONE", task_id="task-second")
        queued = [first, second]
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_started = asyncio.Event()

        async def claim(excluded_app_ids=None):
            excluded_app_ids = excluded_app_ids or set()
            for candidate in list(queued):
                if candidate.app_id not in excluded_app_ids:
                    queued.remove(candidate)
                    return candidate
            return None

        async def process(task):
            if task.task_id == "task-first":
                first_started.set()
                await release_first.wait()
            else:
                second_started.set()

        with (
            patch.object(task_worker, "RECONCILE_SECONDS", 60),
            patch.object(task_worker, "TASK_POLL_SECONDS", 0.005, create=True),
            patch.object(task_worker, "MAX_CONCURRENT_TASKS", 2, create=True),
            patch.object(task_worker, "claim_next_task", side_effect=claim),
            patch.object(task_worker, "process_task", side_effect=process),
            patch.object(task_worker, "reconcile_running_apps", new=AsyncMock()),
        ):
            watcher = asyncio.create_task(task_worker.watch_for_tasks())
            try:
                await asyncio.wait_for(first_started.wait(), timeout=0.2)
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(second_started.wait(), timeout=0.03)
                release_first.set()
                await asyncio.wait_for(second_started.wait(), timeout=0.2)
            finally:
                release_first.set()
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)

    async def test_task_dispatch_concurrency_is_bounded(self):
        queued = [
            _FakeTask(app_id=f"APP-{index}", task_id=f"task-{index}")
            for index in range(3)
        ]
        started = {task.app_id: asyncio.Event() for task in queued}
        releases = {task.app_id: asyncio.Event() for task in queued}

        async def claim(excluded_app_ids=None):
            excluded_app_ids = excluded_app_ids or set()
            for candidate in list(queued):
                if candidate.app_id not in excluded_app_ids:
                    queued.remove(candidate)
                    return candidate
            return None

        async def process(task):
            started[task.app_id].set()
            await releases[task.app_id].wait()

        with (
            patch.object(task_worker, "RECONCILE_SECONDS", 60),
            patch.object(task_worker, "TASK_POLL_SECONDS", 0.005, create=True),
            patch.object(task_worker, "MAX_CONCURRENT_TASKS", 2, create=True),
            patch.object(task_worker, "claim_next_task", side_effect=claim),
            patch.object(task_worker, "process_task", side_effect=process),
            patch.object(task_worker, "reconcile_running_apps", new=AsyncMock()),
        ):
            watcher = asyncio.create_task(task_worker.watch_for_tasks())
            try:
                await asyncio.wait_for(started["APP-0"].wait(), timeout=0.2)
                await asyncio.wait_for(started["APP-1"].wait(), timeout=0.2)
                self.assertFalse(started["APP-2"].is_set())
                releases["APP-0"].set()
                await asyncio.wait_for(started["APP-2"].wait(), timeout=0.2)
            finally:
                for release in releases.values():
                    release.set()
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)

    async def test_exhausted_runtime_actions_leave_non_transitional_status(self):
        for action, initial_status in (
            (TaskAction.START_APP, ApplicationStatus.STARTING),
            (TaskAction.RESTART_APP, ApplicationStatus.STARTING),
            (TaskAction.STOP_APP, ApplicationStatus.STOPPING),
        ):
            with self.subTest(action=action):
                task = _FakeTask(
                    app_id="APP12345",
                    action=action,
                    attempts=task_worker.MAX_TASK_ATTEMPTS,
                )
                app = SimpleNamespace(
                    app_id="APP12345",
                    runtime_generation=7,
                    pending_traefik_cleanup_generation=7,
                    status=initial_status,
                    save=AsyncMock(),
                )
                task_collection = _TaskCollection()
                app_collection = _ApplicationCollection(app)

                def get_collection(model):
                    if model is task_worker.Application:
                        return app_collection
                    return task_collection

                with (
                    patch.object(
                        task_worker.Application,
                        "find_one",
                        new=AsyncMock(return_value=app),
                    ),
                    patch.object(
                        task_worker,
                        "_run_action",
                        new=AsyncMock(side_effect=RuntimeError("exhausted")),
                    ),
                    patch.object(task_worker, "_heartbeat", new=AsyncMock()),
                    patch.object(
                        task_worker.mongodb_manager,
                        "get_collection",
                        side_effect=get_collection,
                    ),
                ):
                    await task_worker.process_task(task)

                self.assertEqual(
                    task_collection.update_calls[-1][1]["$set"]["status"],
                    TaskStatus.FAILED,
                )
                self.assertEqual(app.status, ApplicationStatus.ERROR)
                app.save.assert_not_awaited()
                query, update = app_collection.update_calls[-1]
                self.assertEqual(
                    query,
                    {
                        "app_id": app.app_id,
                        "runtime_generation": 7,
                        "status": initial_status,
                        "lifecycle_revision": 0,
                        "runtime_cleanup_task_id": None,
                        "runtime_cleanup_lease_owner": None,
                    },
                )
                self.assertEqual(update["$set"]["status"], ApplicationStatus.ERROR)
                self.assertEqual(update["$inc"], {"lifecycle_revision": 1})
                failed_call_index = next(
                    index
                    for index, (_query, task_update) in enumerate(
                        task_collection.update_calls
                    )
                    if task_update.get("$set", {}).get("status")
                    == TaskStatus.FAILED
                )
                self.assertIsNotNone(
                    task_collection.update_sessions[failed_call_index]
                )
                self.assertIs(
                    task_collection.update_sessions[failed_call_index],
                    app_collection.update_sessions[-1],
                )

                class FakeApplication:
                    @classmethod
                    def find(cls, query):
                        statuses = query["status"]["$in"]
                        return _ApplicationQuery(
                            [app] if app.status in statuses else []
                        )

                with (
                    patch.object(task_worker, "Application", FakeApplication),
                    patch.object(
                        task_worker,
                        "_active_lifecycle_app_ids",
                        new=AsyncMock(return_value=set()),
                        create=True,
                    ),
                    patch.object(
                        task_worker.docker_manager,
                        "list_containers",
                        return_value=[],
                    ),
                    patch.object(
                        task_worker, "_enqueue_start", new=AsyncMock()
                    ) as enqueue,
                ):
                    await task_worker.reconcile_running_apps()
                enqueue.assert_not_awaited()

    async def test_exhausted_stop_does_not_restore_revoked_runtime_token(self):
        token_hash = hashlib.sha256(b"runtime-token").hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=token_hash,
            status=ApplicationStatus.STOPPING,
        )
        stale_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            runtime_generation=7,
            runtime_token_hash=token_hash,
            status=ApplicationStatus.STOPPING,
            save=AsyncMock(),
        )

        async def save_stale_snapshot():
            persisted.runtime_generation = stale_snapshot.runtime_generation
            persisted.runtime_token_hash = stale_snapshot.runtime_token_hash
            persisted.status = stale_snapshot.status

        async def revoke_then_fail(_app_id, *_args, **_kwargs):
            persisted.runtime_token_hash = None
            raise RuntimeError("Docker stop failed after token revocation")

        stale_snapshot.save.side_effect = save_stale_snapshot
        task_collection = _TaskCollection()
        app_collection = _ApplicationCollection(persisted)

        def get_collection(model):
            if model is task_worker.Application:
                return app_collection
            return task_collection

        with (
            patch.object(
                task_worker.Application,
                "find_one",
                new=AsyncMock(return_value=stale_snapshot),
            ),
            patch.object(
                task_worker,
                "stop_app_container",
                side_effect=revoke_then_fail,
            ),
            patch.object(task_worker, "_heartbeat", new=AsyncMock()),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                side_effect=get_collection,
            ),
        ):
            await task_worker.process_task(
                _FakeTask(
                    app_id=persisted.app_id,
                    action=TaskAction.STOP_APP,
                    attempts=task_worker.MAX_TASK_ATTEMPTS,
                )
            )

        self.assertEqual(
            task_collection.update_calls[-1][1]["$set"]["status"],
            TaskStatus.FAILED,
        )
        self.assertEqual(persisted.status, ApplicationStatus.ERROR)
        self.assertIsNone(persisted.runtime_token_hash)
        stale_snapshot.save.assert_not_awaited()
        query, update = app_collection.update_calls[-1]
        self.assertEqual(
            query,
            {
                "app_id": persisted.app_id,
                "runtime_generation": 7,
                "status": ApplicationStatus.STOPPING,
                "lifecycle_revision": 0,
                "runtime_cleanup_task_id": None,
                "runtime_cleanup_lease_owner": None,
            },
        )
        self.assertEqual(update["$set"]["status"], ApplicationStatus.ERROR)
        self.assertEqual(update["$inc"], {"lifecycle_revision": 1})

    async def test_exhausted_start_and_restart_preserve_advanced_runtime(self):
        for action in (TaskAction.START_APP, TaskAction.RESTART_APP):
            with self.subTest(action=action):
                old_token_hash = hashlib.sha256(b"old-token").hexdigest()
                new_token_hash = hashlib.sha256(b"new-token").hexdigest()
                old_environment = [
                    SimpleNamespace(key="VERSION", value="old")
                ]
                new_environment = [
                    SimpleNamespace(key="VERSION", value="new")
                ]
                persisted = SimpleNamespace(
                    app_id="APP12345",
                    runtime_generation=7,
                    runtime_token_hash=old_token_hash,
                    runtime_memory_mb=512,
                    environment_variables=old_environment,
                    status=ApplicationStatus.STARTING,
                )
                stale_snapshot = SimpleNamespace(
                    app_id=persisted.app_id,
                    runtime_generation=7,
                    runtime_token_hash=old_token_hash,
                    runtime_memory_mb=512,
                    environment_variables=old_environment,
                    status=ApplicationStatus.STARTING,
                    save=AsyncMock(),
                )

                async def save_stale_snapshot():
                    persisted.runtime_generation = stale_snapshot.runtime_generation
                    persisted.runtime_token_hash = stale_snapshot.runtime_token_hash
                    persisted.runtime_memory_mb = stale_snapshot.runtime_memory_mb
                    persisted.environment_variables = (
                        stale_snapshot.environment_variables
                    )
                    persisted.status = stale_snapshot.status

                async def advance_then_fail(*_args, **kwargs):
                    persisted.runtime_generation = 8
                    persisted.runtime_token_hash = new_token_hash
                    persisted.runtime_memory_mb = 1024
                    persisted.environment_variables = new_environment
                    runtime_state = kwargs.get("runtime_state")
                    if runtime_state is None and len(_args) > 3:
                        runtime_state = _args[3]
                    if runtime_state is not None:
                        runtime_state["runtime_generation"] = 8
                    raise RuntimeError("startup failed after runtime advance")

                stale_snapshot.save.side_effect = save_stale_snapshot
                task_collection = _TaskCollection()
                app_collection = _ApplicationCollection(persisted)

                def get_collection(model):
                    if model is task_worker.Application:
                        return app_collection
                    return task_collection

                with (
                    patch.object(
                        task_worker.Application,
                        "find_one",
                        new=AsyncMock(return_value=stale_snapshot),
                    ),
                    patch.object(
                        task_worker,
                        "_run_action",
                        side_effect=advance_then_fail,
                    ),
                    patch.object(task_worker, "_heartbeat", new=AsyncMock()),
                    patch.object(
                        task_worker.mongodb_manager,
                        "get_collection",
                        side_effect=get_collection,
                    ),
                ):
                    await task_worker.process_task(
                        _FakeTask(
                            app_id=persisted.app_id,
                            action=action,
                            attempts=task_worker.MAX_TASK_ATTEMPTS,
                        )
                    )

                self.assertEqual(
                    task_collection.update_calls[-1][1]["$set"]["status"],
                    TaskStatus.FAILED,
                )
                self.assertEqual(persisted.runtime_generation, 8)
                self.assertEqual(persisted.runtime_token_hash, new_token_hash)
                self.assertEqual(persisted.runtime_memory_mb, 1024)
                self.assertIs(persisted.environment_variables, new_environment)
                self.assertEqual(persisted.status, ApplicationStatus.ERROR)
                stale_snapshot.save.assert_not_awaited()
                query, update = app_collection.update_calls[-1]
                self.assertEqual(
                    query,
                    {
                        "app_id": persisted.app_id,
                        "runtime_generation": 8,
                        "status": ApplicationStatus.STARTING,
                        "lifecycle_revision": 0,
                        "runtime_cleanup_task_id": None,
                        "runtime_cleanup_lease_owner": None,
                    },
                )
                self.assertEqual(update["$set"]["status"], ApplicationStatus.ERROR)
                self.assertEqual(update["$inc"], {"lifecycle_revision": 1})

    async def test_exhausted_start_does_not_error_concurrently_advanced_runtime(self):
        old_token_hash = hashlib.sha256(b"old-token").hexdigest()
        new_token_hash = hashlib.sha256(b"new-token").hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=old_token_hash,
            runtime_memory_mb=512,
            status=ApplicationStatus.STARTING,
        )
        stale_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            runtime_generation=7,
            runtime_token_hash=old_token_hash,
            runtime_memory_mb=512,
            status=ApplicationStatus.STARTING,
            save=AsyncMock(),
        )

        async def concurrent_advance_then_fail(*_args, **_kwargs):
            persisted.runtime_generation = 8
            persisted.runtime_token_hash = new_token_hash
            persisted.runtime_memory_mb = 1024
            raise RuntimeError("startup failed after concurrent advance")

        task_collection = _TaskCollection()
        app_collection = _ApplicationCollection(persisted)

        def get_collection(model):
            if model is task_worker.Application:
                return app_collection
            return task_collection

        with (
            patch.object(
                task_worker.Application,
                "find_one",
                new=AsyncMock(return_value=stale_snapshot),
            ),
            patch.object(
                task_worker,
                "_run_action",
                side_effect=concurrent_advance_then_fail,
            ),
            patch.object(task_worker, "_heartbeat", new=AsyncMock()),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                side_effect=get_collection,
            ),
        ):
            await task_worker.process_task(
                _FakeTask(
                    app_id=persisted.app_id,
                    action=TaskAction.START_APP,
                    attempts=task_worker.MAX_TASK_ATTEMPTS,
                )
            )

        self.assertEqual(persisted.runtime_generation, 8)
        self.assertEqual(persisted.runtime_token_hash, new_token_hash)
        self.assertEqual(persisted.runtime_memory_mb, 1024)
        self.assertEqual(persisted.status, ApplicationStatus.STARTING)
        stale_snapshot.save.assert_not_awaited()
        query, update = app_collection.update_calls[-1]
        self.assertEqual(
            query,
            {
                "app_id": persisted.app_id,
                "runtime_generation": 7,
                "status": ApplicationStatus.STARTING,
                "lifecycle_revision": 0,
                "runtime_cleanup_task_id": None,
                "runtime_cleanup_lease_owner": None,
            },
        )
        self.assertEqual(update["$set"]["status"], ApplicationStatus.ERROR)
        self.assertEqual(update["$inc"], {"lifecycle_revision": 1})

    async def test_start_publish_cleans_generation_when_delete_wins_fence(self):
        token_hash = hashlib.sha256(b"new-token").hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=None,
            lifecycle_revision=4,
            status=ApplicationStatus.STARTING,
            save=AsyncMock(),
        )
        task_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            db_password="db-secret",
            runtime_generation=7,
            runtime_token_hash=None,
            lifecycle_revision=4,
            status=ApplicationStatus.STARTING,
        )
        collection = _ApplicationCollection(persisted)
        task_collection = _TaskCollection()
        task_collection.find_one = AsyncMock(
            return_value={
                "task_id": "task-1",
                "status": TaskStatus.RUNNING,
                "lease_owner": task_worker.WORKER_ID,
                "lease_expires_at": task_worker._now() + timedelta(seconds=60),
                "published_at": None,
            }
        )

        def get_collection(model):
            if model is task_worker.Task:
                return task_collection
            return collection

        runtime_state = {
            "runtime_generation": 7,
            "lifecycle_revision": 4,
            "source_status": ApplicationStatus.STARTING,
        }

        async def start_then_lose_authority(_app, **kwargs):
            state = kwargs["runtime_state"]
            persisted.runtime_generation = 8
            persisted.runtime_token_hash = token_hash
            state["runtime_generation"] = 8
            state["runtime_token_hash"] = token_hash
            task_worker.running_apps[persisted.app_id] = {
                "id": "new-container",
                "name": "hyac-app-runtime-app12345",
                "generation": 8,
            }
            persisted.status = ApplicationStatus.DELETING
            persisted.lifecycle_revision = 5
            return {
                "id": "new-container",
                "name": "hyac-app-runtime-app12345",
                "generation": 8,
            }

        cleanup = AsyncMock(
            side_effect=docker_manager._cleanup_runtime_generation
        )
        try:
            with (
                patch.object(
                    task_worker,
                    "check_mongodb_user_exists",
                    new=AsyncMock(return_value=True),
                ),
                patch.object(
                    task_worker.app_storage_service,
                    "ensure_ready",
                    new=AsyncMock(),
                ),
                patch.object(
                    task_worker,
                    "start_app_container",
                    side_effect=start_then_lose_authority,
                ),
                patch.object(
                    task_worker.mongodb_manager,
                    "get_collection",
                    side_effect=get_collection,
                ),
                patch.object(
                    docker_manager.mongodb_manager,
                    "get_collection",
                    side_effect=get_collection,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "stop_container",
                    new=AsyncMock(return_value=True),
                ) as stop,
                patch.object(
                    docker_manager.docker_manager,
                    "remove_container",
                    new=AsyncMock(return_value=True),
                ) as remove,
                patch.object(
                    docker_manager.Application,
                    "find_one",
                    new=AsyncMock(return_value=persisted),
                ),
                patch.object(
                    task_worker,
                    "_cleanup_runtime_generation",
                    new=cleanup,
                    create=True,
                ),
                patch.object(docker_manager, "remove_traefik_web_config"),
            ):
                with self.assertRaises(RuntimeError):
                    await task_worker._run_action(
                        _FakeTask(
                            app_id=persisted.app_id,
                            action=TaskAction.START_APP,
                        ),
                        persisted.app_id,
                        task_snapshot,
                        runtime_state,
                    )

            self.assertEqual(persisted.status, ApplicationStatus.DELETING)
            self.assertEqual(persisted.lifecycle_revision, 5)
            self.assertNotIn(persisted.app_id, task_worker.running_apps)
            cleanup.assert_awaited_once()
            stop.assert_awaited_once_with("new-container")
            remove.assert_awaited_once_with("new-container")
        finally:
            task_worker.running_apps.clear()

    async def test_exhausted_delete_keeps_application_for_a_later_request(self):
        task = _FakeTask(
            app_id="APP12345",
            action=TaskAction.DELETE_APP,
            attempts=task_worker.MAX_TASK_ATTEMPTS,
        )
        app = SimpleNamespace(
            app_id="APP12345",
            status=ApplicationStatus.DELETING,
            runtime_generation=7,
            pending_traefik_cleanup_generation=7,
            lifecycle_revision=4,
            save=AsyncMock(),
        )
        task_collection = _TaskCollection()
        app_collection = _ApplicationCollection(app)

        def get_collection(model):
            if model is task_worker.Application:
                return app_collection
            return task_collection

        with (
            patch.object(
                task_worker.Application,
                "find_one",
                new=AsyncMock(return_value=app),
            ),
            patch.object(
                task_worker,
                "_run_action",
                new=AsyncMock(side_effect=RuntimeError("cleanup failed")),
            ),
            patch.object(task_worker, "_heartbeat", new=AsyncMock()),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                side_effect=get_collection,
            ),
        ):
            await task_worker.process_task(task)

        self.assertEqual(app.status, ApplicationStatus.ERROR)
        self.assertEqual(app.lifecycle_revision, 5)
        failed_call_index = next(
            index
            for index, (_query, update) in enumerate(task_collection.update_calls)
            if update.get("$set", {}).get("status") == TaskStatus.FAILED
        )
        self.assertIsNotNone(task_collection.update_sessions[failed_call_index])
        self.assertIs(
            task_collection.update_sessions[failed_call_index],
            app_collection.update_sessions[-1],
        )
        app.save.assert_not_awaited()

    async def test_stop_task_recovers_expired_generic_cleanup_before_stopping(self):
        task = _FakeTask(
            app_id="APP12345",
            task_id="task-stop",
            action=TaskAction.STOP_APP,
        )
        app = SimpleNamespace(
            app_id=task.app_id,
            runtime_generation=7,
            runtime_token_hash="generation-token",
            pending_traefik_cleanup_generation=7,
            runtime_cleanup_task_id=None,
            runtime_cleanup_lease_owner="cleanup:crashed-proxy",
            runtime_cleanup_lease_expires_at=(
                task_worker._now() - timedelta(seconds=1)
            ),
            status=ApplicationStatus.STOPPING,
            lifecycle_revision=4,
        )
        runtime_state = {
            "runtime_generation": 7,
            "runtime_token_hash": app.runtime_token_hash,
            "source_status": app.status,
            "lifecycle_revision": app.lifecycle_revision,
        }
        cleanup = AsyncMock(return_value=True)
        stop = AsyncMock(return_value=True)
        publish = AsyncMock()

        with (
            patch.object(task_worker, "_cleanup_runtime_generation", new=cleanup),
            patch.object(task_worker, "stop_app_container", new=stop),
            patch.object(task_worker, "_mark_runtime_status", new=publish),
        ):
            await task_worker._run_action(
                task,
                app.app_id,
                app,
                runtime_state,
            )

        cleanup.assert_awaited_once_with(
            app.app_id,
            "hyac-app-runtime-app12345",
            7,
            None,
            "generation-token",
            cleanup_task_id=task.task_id,
            cleanup_lease_owner=task_worker.WORKER_ID,
        )
        stop.assert_awaited_once()
        publish.assert_awaited_once()

    async def test_stop_task_does_not_steal_unexpired_generic_cleanup(self):
        task = _FakeTask(
            app_id="APP12345",
            task_id="task-stop",
            action=TaskAction.STOP_APP,
        )
        app = SimpleNamespace(
            app_id=task.app_id,
            runtime_generation=7,
            runtime_token_hash="generation-token",
            pending_traefik_cleanup_generation=7,
            runtime_cleanup_task_id=None,
            runtime_cleanup_lease_owner="cleanup:active-proxy",
            runtime_cleanup_lease_expires_at=(
                task_worker._now() + timedelta(minutes=1)
            ),
            status=ApplicationStatus.STOPPING,
            lifecycle_revision=4,
        )
        stop = AsyncMock(return_value=True)

        with patch.object(task_worker, "stop_app_container", new=stop):
            with self.assertRaisesRegex(RuntimeError, "cleanup ownership"):
                await task_worker._run_action(
                    task,
                    app.app_id,
                    app,
                    {
                        "runtime_generation": 7,
                        "runtime_token_hash": app.runtime_token_hash,
                        "source_status": app.status,
                        "lifecycle_revision": app.lifecycle_revision,
                    },
                )

        stop.assert_not_awaited()

    async def test_reconciliation_offloads_blocking_docker_inspection(self):
        loop_thread = threading.get_ident()
        docker_threads = []
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash="stored-digest",
            status=ApplicationStatus.RUNNING,
            lifecycle_revision=4,
            pending_traefik_cleanup_generation=None,
            runtime_cleanup_task_id=None,
            runtime_cleanup_lease_owner=None,
            runtime_cleanup_lease_expires_at=None,
        )

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([application])

        def list_containers(*_args, **_kwargs):
            docker_threads.append(threading.get_ident())
            return []

        with (
            patch.object(task_worker, "Application", FakeApplication),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
                create=True,
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                side_effect=list_containers,
            ),
            patch.object(
                task_worker,
                "_replace_missing_runtime",
                new=AsyncMock(),
            ),
        ):
            await task_worker.reconcile_running_apps()

        self.assertTrue(docker_threads)
        self.assertTrue(all(thread_id != loop_thread for thread_id in docker_threads))

    async def test_reconciliation_replaces_runtime_with_wrong_credentials(self):
        token = "runtime-secret"
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            runtime_generation=7,
            status=ApplicationStatus.RUNNING,
            save=AsyncMock(),
        )

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([application])

        containers = [
            {
                "id": "container-1",
                "name": "hyac-app-runtime-app12345",
                "status": "running",
                "health_status": "healthy",
            }
        ]
        for environment in (
            {"RUNTIME_TOKEN": "wrong", "RUNTIME_GENERATION": "7"},
            {"RUNTIME_TOKEN": token, "RUNTIME_GENERATION": "8"},
        ):
            with self.subTest(environment=environment):
                application.runtime_token_hash = hashlib.sha256(token.encode()).hexdigest()
                application.status = ApplicationStatus.RUNNING
                application.save.reset_mock()
                task_worker.running_apps.clear()
                with (
                    patch.object(task_worker, "Application", FakeApplication),
                    patch.object(
                        task_worker.mongodb_manager,
                        "get_collection",
                        return_value=_ApplicationCollection(application),
                    ),
                    patch.object(
                        task_worker,
                        "_active_lifecycle_app_ids",
                        new=AsyncMock(return_value=set()),
                        create=True,
                    ),
                    patch.object(
                        task_worker.docker_manager,
                        "list_containers",
                        return_value=containers,
                    ),
                    patch.object(
                        task_worker.docker_manager,
                        "get_container_environment",
                        return_value=environment,
                    ),
                    patch.object(
                        task_worker.docker_manager,
                        "stop_container",
                        new=AsyncMock(return_value=True),
                    ) as stop,
                    patch.object(
                        task_worker.docker_manager,
                        "remove_container",
                        new=AsyncMock(return_value=True),
                    ) as remove,
                    patch.object(task_worker, "_enqueue_start", new=AsyncMock()) as enqueue,
                ):
                    await task_worker.reconcile_running_apps()

                stop.assert_awaited_once_with("container-1")
                remove.assert_awaited_once_with("container-1")
                enqueue.assert_awaited_once()
                self.assertIs(enqueue.await_args.args[0], application)
                self.assertIsNotNone(enqueue.await_args.kwargs["session"])
                self.assertIsNone(application.runtime_token_hash)

    async def test_stale_reconcile_acquires_generation_cleanup_before_touching_container(
        self,
    ):
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_token_hash=hashlib.sha256(b"old-runtime-token").hexdigest(),
            runtime_generation=7,
            lifecycle_revision=3,
            status=ApplicationStatus.RUNNING,
        )
        container = {
            "id": "successor-container",
            "name": "hyac-app-runtime-app12345",
        }
        cleanup = AsyncMock(return_value=False)
        transition = AsyncMock(return_value=True)
        stop = AsyncMock(return_value=True)
        remove = AsyncMock(return_value=True)

        with (
            patch.object(task_worker, "_cleanup_runtime_generation", new=cleanup),
            patch.object(
                task_worker,
                "_transition_reconcile_to_starting",
                new=transition,
            ),
            patch.object(task_worker.docker_manager, "stop_container", new=stop),
            patch.object(task_worker.docker_manager, "remove_container", new=remove),
        ):
            await task_worker._replace_reconciled_runtime(application, container)

        cleanup.assert_awaited_once_with(
            application.app_id,
            container["name"],
            application.runtime_generation,
            container["id"],
            application.runtime_token_hash,
        )
        transition.assert_not_awaited()
        stop.assert_not_awaited()
        remove.assert_not_awaited()

    async def test_reconciliation_skips_apps_with_database_lifecycle_tasks(self):
        runtime_token = "runtime-secret"
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_token_hash=hashlib.sha256(runtime_token.encode()).hexdigest(),
            runtime_generation=1,
            status=ApplicationStatus.STARTING,
            save=AsyncMock(),
        )
        lifecycle_task = SimpleNamespace(
            app_id=None,
            payload={"app_id": application.app_id},
        )
        captured_task_query = None

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([application])

        class FakeTaskModel:
            @classmethod
            def find(cls, query):
                nonlocal captured_task_query
                captured_task_query = query
                return _ApplicationQuery([lifecycle_task])

        task_worker.running_apps[application.app_id] = {
            "id": "starting-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 1,
        }
        try:
            with (
                patch.object(task_worker, "Application", FakeApplication),
                patch.object(task_worker, "Task", FakeTaskModel),
                patch.object(
                    task_worker.docker_manager,
                    "list_containers",
                    return_value=[],
                ),
                patch.object(task_worker, "_enqueue_start", new=AsyncMock()) as enqueue,
            ):
                await task_worker.reconcile_running_apps()

            lifecycle_branches = captured_task_query["$or"]
            pending = next(
                branch
                for branch in lifecycle_branches
                if branch["status"] == TaskStatus.PENDING
            )
            running = next(
                branch
                for branch in lifecycle_branches
                if branch["status"] == TaskStatus.RUNNING
            )
            self.assertEqual(
                pending["attempts"], {"$lt": task_worker.MAX_TASK_ATTEMPTS}
            )
            self.assertNotIn("$or", pending)
            self.assertEqual(running, {"status": TaskStatus.RUNNING})
            self.assertEqual(
                set(captured_task_query["action"]["$in"]),
                {
                    TaskAction.START_APP,
                    TaskAction.RESTART_APP,
                    TaskAction.STOP_APP,
                    TaskAction.DELETE_APP,
                },
            )
            self.assertIsNotNone(application.runtime_token_hash)
            application.save.assert_not_awaited()
            enqueue.assert_not_awaited()
            self.assertIn(application.app_id, task_worker.running_apps)
        finally:
            task_worker.running_apps.clear()

    async def test_reconciliation_does_not_register_unhealthy_containers(self):
        runtime_token = "runtime-secret"
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_token_hash=hashlib.sha256(runtime_token.encode()).hexdigest(),
            runtime_generation=7,
            status=ApplicationStatus.RUNNING,
            save=AsyncMock(),
        )

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([application])

        for container_status, health_status in (
            ("exited", "healthy"),
            ("running", "starting"),
            ("running", "unhealthy"),
            ("running", None),
        ):
            with self.subTest(
                container_status=container_status,
                health_status=health_status,
            ):
                application.runtime_token_hash = hashlib.sha256(
                    runtime_token.encode()
                ).hexdigest()
                application.status = ApplicationStatus.RUNNING
                application.save.reset_mock()
                task_worker.running_apps.clear()
                containers = [
                    {
                        "id": "container-1",
                        "name": "hyac-app-runtime-app12345",
                        "status": container_status,
                        "health_status": health_status,
                    }
                ]
                with (
                    patch.object(task_worker, "Application", FakeApplication),
                    patch.object(
                        task_worker.mongodb_manager,
                        "get_collection",
                        return_value=_ApplicationCollection(application),
                    ),
                    patch.object(
                        task_worker,
                        "_active_lifecycle_app_ids",
                        new=AsyncMock(return_value=set()),
                        create=True,
                    ),
                    patch.object(
                        task_worker.docker_manager,
                        "list_containers",
                        return_value=containers,
                    ),
                    patch.object(
                        task_worker.docker_manager,
                        "get_container_environment",
                        return_value={
                            "RUNTIME_TOKEN": runtime_token,
                            "RUNTIME_GENERATION": "7",
                        },
                    ),
                    patch.object(
                        task_worker.docker_manager,
                        "stop_container",
                        new=AsyncMock(return_value=True),
                    ) as stop,
                    patch.object(
                        task_worker.docker_manager,
                        "remove_container",
                        new=AsyncMock(return_value=True),
                    ) as remove,
                    patch.object(
                        task_worker, "_enqueue_start", new=AsyncMock()
                    ) as enqueue,
                ):
                    await task_worker.reconcile_running_apps()

                self.assertNotIn(application.app_id, task_worker.running_apps)
                stop.assert_awaited_once_with("container-1")
                remove.assert_awaited_once_with("container-1")
                self.assertIsNone(application.runtime_token_hash)
                self.assertEqual(application.status, ApplicationStatus.STARTING)
                application.save.assert_not_awaited()
                enqueue.assert_awaited_once()
                self.assertIs(enqueue.await_args.args[0], application)
                self.assertIsNotNone(enqueue.await_args.kwargs["session"])

    async def test_unstable_runtime_cleanup_failure_remains_retryable(self):
        runtime_token = "runtime-secret"
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_token_hash=hashlib.sha256(runtime_token.encode()).hexdigest(),
            runtime_generation=7,
            status=ApplicationStatus.RUNNING,
            save=AsyncMock(),
        )

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([application])

        containers = [
            {
                "id": "container-1",
                "name": "hyac-app-runtime-app12345",
                "status": "running",
                "health_status": "unhealthy",
            }
        ]
        cleanup = AsyncMock(side_effect=RuntimeError("docker remove failed"))
        with (
            patch.object(task_worker, "Application", FakeApplication),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
                create=True,
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                return_value=containers,
            ),
            patch.object(
                task_worker.docker_manager,
                "get_container_environment",
                return_value={
                    "RUNTIME_TOKEN": runtime_token,
                    "RUNTIME_GENERATION": "7",
                },
            ),
            patch.object(task_worker, "_cleanup_runtime_generation", new=cleanup),
            patch.object(task_worker, "_enqueue_start", new=AsyncMock()) as enqueue,
        ):
            with self.assertRaises(RuntimeError):
                await task_worker.reconcile_running_apps()

        self.assertIsNotNone(application.runtime_token_hash)
        self.assertEqual(application.status, ApplicationStatus.RUNNING)
        application.save.assert_not_awaited()
        enqueue.assert_not_awaited()
        cleanup.assert_awaited_once_with(
            application.app_id,
            containers[0]["name"],
            application.runtime_generation,
            containers[0]["id"],
            application.runtime_token_hash,
        )

    async def test_stale_reconcile_cannot_overwrite_reclaimed_runtime_generation(self):
        old_token = "old-runtime-token"
        new_token_hash = hashlib.sha256(b"new-runtime-token").hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=hashlib.sha256(old_token.encode()).hexdigest(),
            status=ApplicationStatus.RUNNING,
        )
        stale_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            runtime_generation=persisted.runtime_generation,
            runtime_token_hash=persisted.runtime_token_hash,
            status=persisted.status,
            save=AsyncMock(),
        )

        async def save_stale_snapshot():
            persisted.runtime_generation = stale_snapshot.runtime_generation
            persisted.runtime_token_hash = stale_snapshot.runtime_token_hash
            persisted.status = stale_snapshot.status

        stale_snapshot.save.side_effect = save_stale_snapshot
        collection = _ApplicationCollection(persisted)
        cleanup_started = asyncio.Event()
        release_cleanup = asyncio.Event()

        async def stop_old_container(_container_id):
            cleanup_started.set()
            await release_cleanup.wait()
            return True

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([stale_snapshot])

        task_worker.running_apps[persisted.app_id] = {
            "id": "old-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 7,
        }
        enqueue = AsyncMock()
        try:
            with (
                patch.object(task_worker, "Application", FakeApplication),
                patch.object(
                    task_worker.mongodb_manager,
                    "get_collection",
                    return_value=collection,
                ),
                patch.object(
                    task_worker,
                    "_active_lifecycle_app_ids",
                    new=AsyncMock(return_value=set()),
                ),
                patch.object(
                    task_worker.docker_manager,
                    "list_containers",
                    return_value=[
                        {
                            "id": "old-container",
                            "name": "hyac-app-runtime-app12345",
                            "status": "running",
                            "health_status": "unhealthy",
                        }
                    ],
                ),
                patch.object(
                    task_worker.docker_manager,
                    "get_container_environment",
                    return_value={
                        "RUNTIME_TOKEN": old_token,
                        "RUNTIME_GENERATION": "7",
                    },
                ),
                patch.object(
                    task_worker.docker_manager,
                    "stop_container",
                    side_effect=stop_old_container,
                ),
                patch.object(
                    task_worker.docker_manager,
                    "remove_container",
                    new=AsyncMock(return_value=True),
                ) as remove,
                patch.object(task_worker, "_enqueue_start", new=enqueue),
            ):
                reconciliation = asyncio.create_task(
                    task_worker.reconcile_running_apps()
                )
                await asyncio.wait_for(cleanup_started.wait(), timeout=0.2)

                # An expired RUNNING task is reclaimed and persists generation N+1
                # while the old reconcile pass is blocked in Docker cleanup.
                persisted.runtime_generation = 8
                persisted.runtime_token_hash = new_token_hash
                persisted.status = ApplicationStatus.RUNNING
                task_worker.running_apps[persisted.app_id] = {
                    "id": "new-container",
                    "name": "hyac-app-runtime-app12345",
                    "generation": 8,
                }
                release_cleanup.set()
                await reconciliation

            self.assertEqual(persisted.runtime_generation, 8)
            self.assertEqual(persisted.runtime_token_hash, new_token_hash)
            self.assertEqual(persisted.status, ApplicationStatus.RUNNING)
            self.assertEqual(
                task_worker.running_apps[persisted.app_id]["id"],
                "new-container",
            )
            stale_snapshot.save.assert_not_awaited()
            enqueue.assert_not_awaited()
            remove.assert_not_awaited()
            self.assertTrue(collection.update_calls)
            self.assertTrue(
                all(
                    query["app_id"] == persisted.app_id
                    and query["runtime_generation"] == 7
                    for query, _update in collection.update_calls
                )
            )
        finally:
            release_cleanup.set()
            task_worker.running_apps.clear()

    async def test_missing_runtime_cannot_overwrite_new_proxy_generation(self):
        old_token_hash = hashlib.sha256(b"old-runtime-token").hexdigest()
        new_token_hash = hashlib.sha256(b"new-runtime-token").hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=old_token_hash,
            status=ApplicationStatus.RUNNING,
        )
        stale_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            runtime_generation=7,
            runtime_token_hash=old_token_hash,
            status=ApplicationStatus.RUNNING,
            save=AsyncMock(),
        )

        async def save_stale_snapshot():
            persisted.runtime_generation = stale_snapshot.runtime_generation
            persisted.runtime_token_hash = stale_snapshot.runtime_token_hash
            persisted.status = stale_snapshot.status

        stale_snapshot.save.side_effect = save_stale_snapshot
        collection = _ApplicationCollection(persisted)
        listing_started = asyncio.Event()
        release_listing = asyncio.Event()

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([stale_snapshot])

        async def controlled_to_thread(function, *args, **kwargs):
            if kwargs.get("all"):
                listing_started.set()
                await release_listing.wait()
                return []
            return function(*args, **kwargs)

        enqueue = AsyncMock()
        task_worker.running_apps[persisted.app_id] = {
            "id": "old-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 7,
        }
        try:
            with (
                patch.object(task_worker, "Application", FakeApplication),
                patch.object(
                    task_worker.mongodb_manager,
                    "get_collection",
                    return_value=collection,
                ),
                patch.object(
                    task_worker,
                    "_active_lifecycle_app_ids",
                    new=AsyncMock(return_value=set()),
                ),
                patch.object(
                    task_worker.docker_manager,
                    "list_containers",
                    return_value=[],
                ),
                patch.object(
                    task_worker.asyncio,
                    "to_thread",
                    side_effect=controlled_to_thread,
                ),
                patch.object(task_worker, "_enqueue_start", new=enqueue),
            ):
                reconciliation = asyncio.create_task(
                    task_worker.reconcile_running_apps()
                )
                await asyncio.wait_for(listing_started.wait(), timeout=0.2)

                # A proxy start persists and registers generation N+1 after the
                # reconcile pass read its generation N application snapshot.
                persisted.runtime_generation = 8
                persisted.runtime_token_hash = new_token_hash
                persisted.status = ApplicationStatus.RUNNING
                task_worker.running_apps[persisted.app_id] = {
                    "id": "new-container",
                    "name": "hyac-app-runtime-app12345",
                    "generation": 8,
                }
                release_listing.set()
                await reconciliation

            self.assertEqual(persisted.runtime_generation, 8)
            self.assertEqual(persisted.runtime_token_hash, new_token_hash)
            self.assertEqual(persisted.status, ApplicationStatus.RUNNING)
            self.assertEqual(
                task_worker.running_apps[persisted.app_id]["id"],
                "new-container",
            )
            stale_snapshot.save.assert_not_awaited()
            enqueue.assert_not_awaited()
            query, update = collection.update_calls[-1]
            self.assertEqual(query["app_id"], persisted.app_id)
            self.assertEqual(query["runtime_generation"], 7)
            self.assertIsNone(update["$set"]["runtime_token_hash"])
        finally:
            release_listing.set()
            task_worker.running_apps.clear()

    async def test_missing_runtime_transition_and_start_task_share_transaction(self):
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=hashlib.sha256(b"runtime-token").hexdigest(),
            runtime_cleanup_task_id=None,
            runtime_cleanup_lease_owner=None,
            pending_traefik_cleanup_generation=None,
            status=ApplicationStatus.RUNNING,
            lifecycle_revision=4,
        )
        collection = _ApplicationCollection(application)
        inserted = []

        class StableTask:
            def __init__(self, app_id, lifecycle_revision):
                self.task_id = "stable-reconcile-task"
                self.app_id = app_id
                self.action = TaskAction.START_APP
                self.payload = {
                    "app_id": app_id,
                    "lifecycle_revision": lifecycle_revision,
                }
                self.status = TaskStatus.PENDING

            async def insert(self, session=None):
                inserted.append((self, session))

        with (
            patch.object(
                task_worker,
                "_new_reconcile_start_task",
                side_effect=StableTask,
            ),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
        ):
            await task_worker._replace_missing_runtime(application)

        self.assertEqual(len(inserted), 1)
        task, task_session = inserted[0]
        self.assertEqual(task.task_id, "stable-reconcile-task")
        self.assertEqual(task.payload["lifecycle_revision"], 5)
        self.assertIsNotNone(task_session)
        self.assertIs(task_session, collection.update_sessions[-1])
        self.assertEqual(application.status, ApplicationStatus.STARTING)
        self.assertEqual(application.lifecycle_revision, 5)

    async def test_missing_runtime_does_not_reverse_stopping_transition(self):
        token_hash = hashlib.sha256(b"runtime-token").hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=token_hash,
            status=ApplicationStatus.RUNNING,
        )
        stale_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            runtime_generation=7,
            runtime_token_hash=token_hash,
            status=ApplicationStatus.RUNNING,
        )
        collection = _ApplicationCollection(persisted)
        listing_started = asyncio.Event()
        release_listing = asyncio.Event()

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([stale_snapshot])

        async def controlled_to_thread(function, *args, **kwargs):
            if kwargs.get("all"):
                listing_started.set()
                await release_listing.wait()
                return []
            return function(*args, **kwargs)

        enqueue = AsyncMock()
        old_registry = {
            "id": "old-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 7,
        }
        task_worker.running_apps[persisted.app_id] = old_registry
        try:
            with (
                patch.object(task_worker, "Application", FakeApplication),
                patch.object(
                    task_worker.mongodb_manager,
                    "get_collection",
                    return_value=collection,
                ),
                patch.object(
                    task_worker,
                    "_active_lifecycle_app_ids",
                    new=AsyncMock(return_value=set()),
                ),
                patch.object(
                    task_worker.docker_manager,
                    "list_containers",
                    return_value=[],
                ),
                patch.object(
                    task_worker.asyncio,
                    "to_thread",
                    side_effect=controlled_to_thread,
                ),
                patch.object(task_worker, "_enqueue_start", new=enqueue),
            ):
                reconciliation = asyncio.create_task(
                    task_worker.reconcile_running_apps()
                )
                await asyncio.wait_for(listing_started.wait(), timeout=0.2)

                # The stop endpoint persists STOPPING before its task insert.
                persisted.status = ApplicationStatus.STOPPING
                release_listing.set()
                await reconciliation

            self.assertEqual(persisted.status, ApplicationStatus.STOPPING)
            self.assertEqual(persisted.runtime_token_hash, token_hash)
            self.assertIs(task_worker.running_apps[persisted.app_id], old_registry)
            enqueue.assert_not_awaited()
            query, _update = collection.update_calls[-1]
            self.assertEqual(query["status"], ApplicationStatus.RUNNING)
        finally:
            release_listing.set()
            task_worker.running_apps.clear()

    async def test_unhealthy_runtime_does_not_reverse_deleting_transition(self):
        token = "runtime-token"
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=token_hash,
            status=ApplicationStatus.STARTING,
        )
        stale_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            runtime_generation=7,
            runtime_token_hash=token_hash,
            status=ApplicationStatus.STARTING,
        )
        collection = _ApplicationCollection(persisted)
        cleanup_started = asyncio.Event()
        release_cleanup = asyncio.Event()

        async def stop_old_container(_container_id):
            cleanup_started.set()
            await release_cleanup.wait()
            return True

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([stale_snapshot])

        enqueue = AsyncMock()
        old_registry = {
            "id": "old-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 7,
        }
        task_worker.running_apps[persisted.app_id] = old_registry
        try:
            with (
                patch.object(task_worker, "Application", FakeApplication),
                patch.object(
                    task_worker.mongodb_manager,
                    "get_collection",
                    return_value=collection,
                ),
                patch.object(
                    task_worker,
                    "_active_lifecycle_app_ids",
                    new=AsyncMock(return_value=set()),
                ),
                patch.object(
                    task_worker.docker_manager,
                    "list_containers",
                    return_value=[
                        {
                            "id": "old-container",
                            "name": "hyac-app-runtime-app12345",
                            "status": "running",
                            "health_status": "unhealthy",
                        }
                    ],
                ),
                patch.object(
                    task_worker.docker_manager,
                    "get_container_environment",
                    return_value={
                        "RUNTIME_TOKEN": token,
                        "RUNTIME_GENERATION": "7",
                    },
                ),
                patch.object(
                    task_worker.docker_manager,
                    "stop_container",
                    side_effect=stop_old_container,
                ),
                patch.object(
                    task_worker.docker_manager,
                    "remove_container",
                    new=AsyncMock(return_value=True),
                ),
                patch.object(task_worker, "_enqueue_start", new=enqueue),
            ):
                reconciliation = asyncio.create_task(
                    task_worker.reconcile_running_apps()
                )
                await asyncio.wait_for(cleanup_started.wait(), timeout=0.2)

                # The delete endpoint persists DELETING before its task insert.
                persisted.status = ApplicationStatus.DELETING
                release_cleanup.set()
                await reconciliation

            self.assertEqual(persisted.status, ApplicationStatus.DELETING)
            self.assertIsNone(persisted.runtime_token_hash)
            self.assertNotIn(persisted.app_id, task_worker.running_apps)
            enqueue.assert_not_awaited()
            query, _update = collection.update_calls[-1]
            self.assertEqual(query["status"], ApplicationStatus.STARTING)
        finally:
            release_cleanup.set()
            task_worker.running_apps.clear()


class DockerManagerSafetyTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.application_collection_patch = patch.object(
            docker_manager,
            "mongodb_manager",
            SimpleNamespace(
                get_collection=MagicMock(
                    return_value=_MatchedApplicationCollection()
                ),
                client=_NoOpTransactionClient(),
            ),
            create=True,
        )
        self.application_collection_patch.start()
        self.addCleanup(self.application_collection_patch.stop)

    async def test_healthy_adoption_loses_when_cleanup_acquires_during_inspection(self):
        token = "runtime-token"
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            runtime_cleanup_task_id=None,
            runtime_cleanup_lease_owner=None,
            pending_traefik_cleanup_generation=None,
            status=ApplicationStatus.STARTING,
            lifecycle_revision=4,
        )
        collection = _ApplicationCollection(application)

        def inspect_environment(_container_id):
            application.runtime_cleanup_task_id = "cleanup-task"
            application.runtime_cleanup_lease_owner = "cleanup-worker"
            return {
                "RUNTIME_TOKEN": token,
                "RUNTIME_GENERATION": "7",
            }

        with (
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(
                docker_manager.Application,
                "find_one",
                new=AsyncMock(return_value=application),
            ),
            patch.object(
                docker_manager.docker_manager,
                "client",
                SimpleNamespace(),
            ),
            patch.object(
                docker_manager.docker_manager,
                "list_containers",
                return_value=[
                    {
                        "id": "container-7",
                        "name": "hyac-app-runtime-app12345",
                        "status": "running",
                        "health_status": "healthy",
                    }
                ],
            ),
            patch.object(
                docker_manager.docker_manager,
                "get_container_environment",
                side_effect=inspect_environment,
            ),
            patch.object(
                docker_manager.asyncio,
                "to_thread",
                side_effect=_run_in_fresh_thread,
            ),
        ):
            adopted = await docker_manager.start_app_container(
                application,
                expected_status=ApplicationStatus.STARTING,
                expected_lifecycle_revision=4,
            )

        self.assertIsNone(adopted)
        self.assertNotIn(application.app_id, docker_manager.running_apps)

    async def test_concurrent_stale_snapshots_adopt_first_started_runtime(self):
        persisted = SimpleNamespace(
            app_id="APP12345",
            db_password="db-secret",
            runtime_generation=0,
            runtime_token_hash=None,
            runtime_memory_mb=512,
            runtime_cpus=1.0,
            runtime_pids_limit=128,
            environment_variables=[],
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )

        def stale_snapshot():
            snapshot = SimpleNamespace(
                app_id=persisted.app_id,
                db_password=persisted.db_password,
                runtime_generation=0,
                runtime_token_hash=None,
                runtime_memory_mb=persisted.runtime_memory_mb,
                runtime_cpus=persisted.runtime_cpus,
                runtime_pids_limit=persisted.runtime_pids_limit,
                environment_variables=[],
                update_timestamp=MagicMock(),
                save=AsyncMock(),
            )

            async def save_snapshot():
                persisted.runtime_generation = snapshot.runtime_generation
                persisted.runtime_token_hash = snapshot.runtime_token_hash

            snapshot.save.side_effect = save_snapshot
            return snapshot

        first_snapshot = stale_snapshot()
        second_snapshot = stale_snapshot()
        storage = SimpleNamespace(
            status=StorageStatus.READY,
            access_key="access",
            secret_key="secret",
        )
        runtime_container = SimpleNamespace(
            id="container-1",
            attrs={"State": {"Health": {"Status": "healthy"}}},
            reload=MagicMock(),
        )
        server_container = SimpleNamespace(
            attrs={
                "NetworkSettings": {"Networks": {"hyac_network": {}}},
                "Config": {"Labels": {}},
            }
        )
        fake_client = SimpleNamespace(
            containers=SimpleNamespace(get=MagicMock(return_value=server_container))
        )
        create_started = threading.Event()
        release_create = threading.Event()
        container_visible = False
        created_environment = {}
        list_calls = 0

        def list_containers(*_args, **_kwargs):
            nonlocal list_calls
            list_calls += 1
            if not container_visible:
                return []
            return [
                {
                    "id": "container-1",
                    "name": "hyac-app-runtime-app12345",
                    "status": "running",
                    "health_status": "healthy",
                }
            ]

        def create_container(*_args, **kwargs):
            nonlocal container_visible
            created_environment.clear()
            created_environment.update(kwargs["environment"])
            if not create_started.is_set():
                create_started.set()
                release_create.wait(timeout=1)
            container_visible = True
            return runtime_container

        collection = _ApplicationCollection(persisted)
        stop = AsyncMock(return_value=True)
        remove = AsyncMock(return_value=True)
        docker_manager.running_apps.clear()
        docker_manager._app_start_locks.clear()
        try:
            with (
                patch.object(
                    docker_manager.app_storage_service,
                    "get_storage",
                    new=AsyncMock(return_value=storage),
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "list_containers",
                    side_effect=list_containers,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "get_container_environment",
                    side_effect=lambda *_args: dict(created_environment),
                ),
                patch.object(docker_manager.docker_manager, "client", fake_client),
                patch.object(
                    docker_manager.docker_manager,
                    "create_container",
                    side_effect=create_container,
                ) as create,
                patch.object(
                    docker_manager.docker_manager,
                    "start_container",
                    return_value=True,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "stop_container",
                    new=stop,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "remove_container",
                    new=remove,
                ),
                patch.object(
                    docker_manager.Application,
                    "find_one",
                    new=AsyncMock(return_value=persisted),
                ),
                patch.object(
                    docker_manager,
                    "mongodb_manager",
                    SimpleNamespace(
                        get_collection=MagicMock(return_value=collection),
                        client=_NoOpTransactionClient(),
                    ),
                    create=True,
                ),
                patch.object(
                    docker_manager.socket,
                    "gethostbyname",
                    return_value="127.0.0.1",
                ),
                patch.object(
                    docker_manager.asyncio,
                    "to_thread",
                    side_effect=_run_in_managed_thread,
                ),
                patch(
                    "core.initialization.create_function_templates_for_app",
                    new=AsyncMock(),
                ),
                patch.object(docker_manager, "create_traefik_web_config"),
            ):
                first = asyncio.create_task(
                    docker_manager.start_app_container(first_snapshot)
                )
                for _ in range(100):
                    if create_started.is_set():
                        break
                    await asyncio.sleep(0.002)
                self.assertTrue(create_started.is_set())

                second = asyncio.create_task(
                    docker_manager.start_app_container(second_snapshot)
                )
                await asyncio.sleep(0.02)
                self.assertEqual(list_calls, 1)
                release_create.set()
                first_result, second_result = await asyncio.gather(first, second)

            self.assertEqual(first_result, second_result)
            self.assertEqual(first_result["generation"], 1)
            self.assertEqual(persisted.runtime_generation, 1)
            create.assert_called_once()
            stop.assert_not_awaited()
            remove.assert_not_awaited()
        finally:
            release_create.set()
            docker_manager.running_apps.clear()
            docker_manager._app_start_locks.clear()

    async def test_start_rejects_non_startable_authoritative_statuses(self):
        docker_manager.running_apps.clear()
        docker_manager._app_start_locks.clear()
        try:
            for status in (
                ApplicationStatus.STOPPING,
                ApplicationStatus.DELETING,
                ApplicationStatus.STOPPED,
                ApplicationStatus.ERROR,
            ):
                with self.subTest(status=status):
                    application = SimpleNamespace(
                        app_id="APP12345",
                        runtime_generation=7,
                        runtime_token_hash=None,
                        lifecycle_revision=4,
                        status=status,
                    )
                    listed = MagicMock(
                        side_effect=AssertionError(
                            "non-startable authority must not inspect Docker"
                        )
                    )
                    created = MagicMock()
                    with (
                        patch.object(
                            docker_manager.Application,
                            "find_one",
                            new=AsyncMock(return_value=application),
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "client",
                            SimpleNamespace(),
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "list_containers",
                            new=listed,
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "create_container",
                            new=created,
                        ),
                        patch.object(
                            docker_manager.asyncio,
                            "to_thread",
                            side_effect=_run_in_fresh_thread,
                        ),
                        patch.object(
                            docker_manager,
                            "create_traefik_web_config",
                        ) as traefik,
                    ):
                        result = await docker_manager.start_app_container(
                            application
                        )

                    self.assertIsNone(result)
                    listed.assert_not_called()
                    created.assert_not_called()
                    traefik.assert_not_called()
                    self.assertNotIn(application.app_id, docker_manager.running_apps)
        finally:
            docker_manager.running_apps.clear()
            docker_manager._app_start_locks.clear()

    async def test_delete_holds_start_fence_until_cleanup_finishes(self):
        application = SimpleNamespace(
            app_id="APP12345",
            app_name="Example",
            runtime_generation=7,
            runtime_token_hash=None,
            lifecycle_revision=5,
            status=ApplicationStatus.DELETING,
        )
        delete_started = asyncio.Event()
        release_delete = asyncio.Event()

        async def delete_while_locked(*_args, **_kwargs):
            self.assertTrue(
                docker_manager._app_start_locks[application.app_id].locked()
            )
            delete_started.set()
            await release_delete.wait()

        listed = MagicMock(
            side_effect=AssertionError(
                "a start waiting on deletion must not inspect Docker"
            )
        )
        docker_manager.running_apps.clear()
        docker_manager._app_start_locks.clear()
        try:
            with (
                patch.object(
                    docker_manager,
                    "_delete_application_background_locked",
                    side_effect=delete_while_locked,
                ),
                patch.object(
                    docker_manager.Application,
                    "find_one",
                    new=AsyncMock(return_value=application),
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "client",
                    SimpleNamespace(),
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "list_containers",
                    new=listed,
                ),
            ):
                deletion = asyncio.create_task(
                    docker_manager.delete_application_background(
                        application,
                        expected_runtime_generation=7,
                        expected_status=ApplicationStatus.DELETING,
                        expected_lifecycle_revision=5,
                    )
                )
                await asyncio.wait_for(delete_started.wait(), timeout=0.2)
                startup = asyncio.create_task(
                    docker_manager.start_app_container(application)
                )
                await asyncio.sleep(0)
                self.assertFalse(startup.done())
                listed.assert_not_called()

                release_delete.set()
                await deletion
                self.assertIsNone(await startup)

            listed.assert_not_called()
            self.assertNotIn(application.app_id, docker_manager.running_apps)
        finally:
            release_delete.set()
            docker_manager.running_apps.clear()
            docker_manager._app_start_locks.clear()

    async def test_stop_revocation_cannot_overwrite_new_generation(self):
        old_hash = hashlib.sha256(b"old-token").hexdigest()
        new_hash = hashlib.sha256(b"new-token").hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=old_hash,
            updated_at=None,
        )
        stale_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            runtime_generation=7,
            runtime_token_hash=old_hash,
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )

        async def save_stale_snapshot():
            persisted.runtime_generation = stale_snapshot.runtime_generation
            persisted.runtime_token_hash = stale_snapshot.runtime_token_hash

        stale_snapshot.save.side_effect = save_stale_snapshot
        read_started = asyncio.Event()
        release_read = asyncio.Event()
        find_calls = 0

        async def find_application(_query):
            nonlocal find_calls
            find_calls += 1
            if find_calls == 1:
                read_started.set()
                await release_read.wait()
            return stale_snapshot

        collection = _ApplicationCollection(persisted)
        with (
            patch.object(
                docker_manager.Application,
                "find_one",
                side_effect=find_application,
            ),
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(
                docker_manager.docker_manager,
                "stop_container",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                docker_manager.docker_manager,
                "remove_container",
                new=AsyncMock(return_value=True),
            ),
            patch.object(docker_manager, "remove_traefik_web_config"),
        ):
            stopping = asyncio.create_task(
                docker_manager.stop_app_container(persisted.app_id)
            )
            await asyncio.wait_for(read_started.wait(), timeout=0.2)
            persisted.runtime_generation = 8
            persisted.runtime_token_hash = new_hash
            release_read.set()
            await stopping

        self.assertEqual(persisted.runtime_generation, 8)
        self.assertEqual(persisted.runtime_token_hash, new_hash)
        stale_snapshot.save.assert_not_awaited()

    async def test_cleanup_revocation_cannot_overwrite_new_generation(self):
        old_hash = hashlib.sha256(b"old-token").hexdigest()
        new_hash = hashlib.sha256(b"new-token").hexdigest()
        persisted = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=old_hash,
            updated_at=None,
        )
        stale_snapshot = SimpleNamespace(
            app_id=persisted.app_id,
            runtime_generation=7,
            runtime_token_hash=old_hash,
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )

        async def save_stale_snapshot():
            persisted.runtime_generation = stale_snapshot.runtime_generation
            persisted.runtime_token_hash = stale_snapshot.runtime_token_hash

        stale_snapshot.save.side_effect = save_stale_snapshot
        revoke_started = asyncio.Event()
        release_revoke = asyncio.Event()

        async def find_application(_query):
            revoke_started.set()
            await release_revoke.wait()
            return stale_snapshot

        class BarrierCollection(_ApplicationCollection):
            async def update_one(self, query, update, session=None):
                revoke_started.set()
                await release_revoke.wait()
                return await super().update_one(query, update)

        collection = BarrierCollection(persisted)
        with (
            patch.object(
                docker_manager.Application,
                "find_one",
                side_effect=find_application,
            ),
            patch.object(
                docker_manager.mongodb_manager,
                "get_collection",
                return_value=collection,
            ),
            patch.object(
                docker_manager.docker_manager,
                "stop_container",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                docker_manager.docker_manager,
                "remove_container",
                new=AsyncMock(return_value=True),
            ),
        ):
            cleanup = asyncio.create_task(
                docker_manager._cleanup_runtime_generation(
                    persisted.app_id,
                    "hyac-app-runtime-app12345",
                    7,
                    "old-container",
                )
            )
            await asyncio.wait_for(revoke_started.wait(), timeout=0.2)
            persisted.runtime_generation = 8
            persisted.runtime_token_hash = new_hash
            docker_manager.running_apps[persisted.app_id] = {
                "id": "new-container",
                "name": "hyac-app-runtime-app12345",
                "generation": 8,
            }
            release_revoke.set()
            await cleanup

        self.assertEqual(persisted.runtime_generation, 8)
        self.assertEqual(persisted.runtime_token_hash, new_hash)
        self.assertEqual(
            docker_manager.running_apps[persisted.app_id]["id"],
            "new-container",
        )
        stale_snapshot.save.assert_not_awaited()

    async def test_fast_path_rejects_wrong_runtime_credentials(self):
        expected_token = "runtime-secret"
        expected_hash = hashlib.sha256(expected_token.encode()).hexdigest()
        for environment, stored_hash in (
            (
                {"RUNTIME_TOKEN": "wrong", "RUNTIME_GENERATION": "7"},
                expected_hash,
            ),
            (
                {"RUNTIME_TOKEN": expected_token, "RUNTIME_GENERATION": "8"},
                expected_hash,
            ),
            (
                {"RUNTIME_TOKEN": expected_token, "RUNTIME_GENERATION": "7"},
                None,
            ),
            (
                {
                    "RUNTIME_TOKEN": expected_token,
                    "RUNTIME_GENERATION": "7",
                    "SECRET_KEY": "legacy-secret",
                },
                expected_hash,
            ),
        ):
            with self.subTest(environment=environment, stored_hash=stored_hash):
                application = SimpleNamespace(
                    app_id="APP12345",
                    db_password="db-secret",
                    runtime_generation=7,
                    runtime_token_hash=stored_hash,
                    runtime_memory_mb=512,
                    runtime_cpus=1.0,
                    runtime_pids_limit=128,
                    environment_variables=[],
                    update_timestamp=MagicMock(),
                    save=AsyncMock(),
                )
                storage = SimpleNamespace(
                    status=StorageStatus.READY,
                    access_key="access",
                    secret_key="secret",
                )
                old_container = {
                    "id": "old-container",
                    "name": "hyac-app-runtime-app12345",
                    "status": "running",
                    "health_status": "healthy",
                }
                runtime_container = SimpleNamespace(
                    id="new-container",
                    attrs={"State": {"Health": {"Status": "healthy"}}},
                    reload=MagicMock(),
                )
                server_container = SimpleNamespace(
                    attrs={
                        "NetworkSettings": {"Networks": {"hyac_network": {}}},
                        "Config": {"Labels": {}},
                    }
                )
                fake_client = SimpleNamespace(
                    containers=SimpleNamespace(
                        get=MagicMock(return_value=server_container)
                    )
                )
                listed = MagicMock(return_value=[old_container])
                stop = AsyncMock(return_value=True)
                remove = AsyncMock(return_value=True)
                create = MagicMock(return_value=runtime_container)
                docker_manager.running_apps[application.app_id] = {
                    "id": "old-container",
                    "name": "hyac-app-runtime-app12345",
                    "generation": 7,
                }
                try:
                    with (
                        patch.object(
                            docker_manager.app_storage_service,
                            "get_storage",
                            new=AsyncMock(return_value=storage),
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "list_containers",
                            new=listed,
                        ),
                        patch.object(
                            docker_manager.docker_manager, "client", fake_client
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "get_container_environment",
                            return_value=environment,
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "stop_container",
                            new=stop,
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "remove_container",
                            new=remove,
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "create_container",
                            new=create,
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "start_container",
                            return_value=True,
                        ),
                        patch.object(
                            docker_manager.Application,
                            "find_one",
                            new=AsyncMock(return_value=application),
                        ),
                        patch.object(
                            docker_manager.socket,
                            "gethostbyname",
                            return_value="127.0.0.1",
                        ),
                        patch.object(
                            docker_manager.asyncio,
                            "to_thread",
                            side_effect=_run_in_fresh_thread,
                        ),
                        patch(
                            "core.initialization.create_function_templates_for_app",
                            new=AsyncMock(),
                        ),
                        patch.object(
                            docker_manager, "create_traefik_web_config"
                        ),
                    ):
                        result = await docker_manager.start_app_container(application)

                    listed.assert_called_once_with(all=True)
                    stop.assert_awaited_once_with("old-container")
                    remove.assert_awaited_once_with("old-container")
                    create.assert_called_once()
                    self.assertEqual(result["id"], "new-container")
                    self.assertEqual(result["generation"], 8)
                finally:
                    docker_manager.running_apps.clear()
                    docker_manager._app_start_locks.clear()

    async def test_fast_path_accepts_matching_runtime_credentials(self):
        runtime_token = "runtime-secret"
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=hashlib.sha256(runtime_token.encode()).hexdigest(),
        )
        existing = {
            "id": "existing-container",
            "name": "hyac-app-runtime-app12345",
            "status": "running",
            "health_status": "healthy",
        }
        registry_entry = {
            "id": "existing-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 7,
        }
        docker_manager.running_apps[application.app_id] = registry_entry
        docker_manager._app_start_locks.clear()
        try:
            listed = MagicMock(return_value=[existing])
            with (
                patch.object(
                    docker_manager.docker_manager,
                    "list_containers",
                    new=listed,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "get_container_environment",
                    return_value={
                        "RUNTIME_TOKEN": runtime_token,
                        "RUNTIME_GENERATION": "7",
                    },
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "client",
                    SimpleNamespace(),
                ),
                patch.object(
                    docker_manager.Application,
                    "find_one",
                    new=AsyncMock(return_value=application),
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "stop_container",
                    new=AsyncMock(),
                ) as stop,
                patch.object(
                    docker_manager.docker_manager,
                    "remove_container",
                    new=AsyncMock(),
                ) as remove,
                patch.object(
                    docker_manager.asyncio,
                    "to_thread",
                    side_effect=_run_in_fresh_thread,
                ),
            ):
                result = await docker_manager.start_app_container(application)

            self.assertIs(result, registry_entry)
            listed.assert_called_once_with(all=True)
            stop.assert_not_awaited()
            remove.assert_not_awaited()
        finally:
            docker_manager.running_apps.clear()
            docker_manager._app_start_locks.clear()

    async def test_fast_path_rehydrates_registry_from_matching_runtime(self):
        runtime_token = "runtime-secret"
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=7,
            runtime_token_hash=hashlib.sha256(runtime_token.encode()).hexdigest(),
        )
        existing = {
            "id": "existing-container",
            "name": "hyac-app-runtime-app12345",
            "status": "running",
            "health_status": "healthy",
        }
        docker_manager.running_apps.clear()
        docker_manager._app_start_locks.clear()
        stop = AsyncMock(
            side_effect=AssertionError("matching healthy runtime must not stop")
        )
        remove = AsyncMock(
            side_effect=AssertionError("matching healthy runtime must not remove")
        )
        try:
            with (
                patch.object(
                    docker_manager.Application,
                    "find_one",
                    new=AsyncMock(return_value=application),
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "list_containers",
                    return_value=[existing],
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "get_container_environment",
                    return_value={
                        "RUNTIME_TOKEN": runtime_token,
                        "RUNTIME_GENERATION": "7",
                    },
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "client",
                    SimpleNamespace(),
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "stop_container",
                    new=stop,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "remove_container",
                    new=remove,
                ),
                patch.object(
                    docker_manager.asyncio,
                    "to_thread",
                    side_effect=_run_in_fresh_thread,
                ),
            ):
                result = await docker_manager.start_app_container(application)

            self.assertEqual(
                result,
                {
                    "id": "existing-container",
                    "name": "hyac-app-runtime-app12345",
                    "generation": 7,
                },
            )
            self.assertIs(
                docker_manager.running_apps[application.app_id], result
            )
            stop.assert_not_awaited()
            remove.assert_not_awaited()
        finally:
            docker_manager.running_apps.clear()
            docker_manager._app_start_locks.clear()

    async def test_start_discovers_and_removes_nonrunning_name_residues(self):
        for residue_status in ("created", "exited"):
            with self.subTest(residue_status=residue_status):
                application = SimpleNamespace(
                    app_id="APP12345",
                    db_password="db-secret",
                    runtime_generation=0,
                    runtime_token_hash=None,
                    runtime_memory_mb=512,
                    runtime_cpus=1.0,
                    runtime_pids_limit=128,
                    environment_variables=[],
                    update_timestamp=MagicMock(),
                    save=AsyncMock(),
                )
                storage = SimpleNamespace(
                    status=StorageStatus.READY,
                    access_key="access",
                    secret_key="secret",
                )
                residue = {
                    "id": "residue-container",
                    "name": "hyac-app-runtime-app12345",
                    "status": residue_status,
                    "health_status": None,
                }
                server_container = SimpleNamespace(
                    attrs={
                        "NetworkSettings": {"Networks": {"hyac_network": {}}},
                        "Config": {"Labels": {}},
                    }
                )
                fake_client = SimpleNamespace(
                    containers=SimpleNamespace(
                        get=MagicMock(return_value=server_container)
                    )
                )
                listed = MagicMock(return_value=[residue])
                stop = AsyncMock(return_value=True)
                remove = AsyncMock(return_value=True)
                try:
                    with (
                        patch.object(
                            docker_manager.app_storage_service,
                            "get_storage",
                            new=AsyncMock(return_value=storage),
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "list_containers",
                            new=listed,
                        ),
                        patch.object(
                            docker_manager.docker_manager, "client", fake_client
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "get_container_environment",
                            return_value={"RUNTIME_GENERATION": "0"},
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "stop_container",
                            new=stop,
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "remove_container",
                            new=remove,
                        ),
                        patch.object(
                            docker_manager.docker_manager,
                            "create_container",
                            return_value=None,
                        ),
                        patch.object(
                            docker_manager.Application,
                            "find_one",
                            new=AsyncMock(return_value=application),
                        ),
                        patch.object(
                            docker_manager.asyncio,
                            "to_thread",
                            side_effect=_run_in_fresh_thread,
                        ),
                    ):
                        result = await docker_manager.start_app_container(application)

                    self.assertIsNone(result)
                    listed.assert_called_once_with(all=True)
                    stop.assert_awaited_once_with("residue-container")
                    remove.assert_awaited_once_with("residue-container")
                    self.assertIsNone(application.runtime_token_hash)
                finally:
                    docker_manager.running_apps.clear()
                    docker_manager._app_start_locks.clear()

    async def _assert_cancelled_start_is_collected_and_cleaned(self, phase):
        application = SimpleNamespace(
            app_id="APP12345",
            db_password="db-secret",
            runtime_generation=0,
            runtime_token_hash=None,
            runtime_memory_mb=512,
            runtime_cpus=1.0,
            runtime_pids_limit=128,
            environment_variables=[],
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )
        storage = SimpleNamespace(
            status=StorageStatus.READY,
            access_key="access",
            secret_key="secret",
        )
        runtime_container = SimpleNamespace(
            id="container-1",
            attrs={"State": {"Health": {"Status": "healthy"}}},
        )
        server_container = SimpleNamespace(
            attrs={
                "NetworkSettings": {"Networks": {"hyac_network": {}}},
                "Config": {"Labels": {}},
            }
        )
        fake_client = SimpleNamespace(
            containers=SimpleNamespace(get=MagicMock(return_value=server_container))
        )
        thread_started = threading.Event()
        release_thread = threading.Event()
        thread_finished = threading.Event()
        blocked = False

        def maybe_block(current_phase, result):
            nonlocal blocked
            if current_phase == phase and not blocked:
                blocked = True
                thread_started.set()
                release_thread.wait(timeout=1)
                thread_finished.set()
            return result

        def create_container(*_args, **_kwargs):
            return maybe_block("create", runtime_container)

        def start_container(*_args, **_kwargs):
            return maybe_block("start", True)

        def reload_container():
            maybe_block("reload", None)
            runtime_container.attrs["State"]["Health"]["Status"] = "healthy"

        runtime_container.reload = reload_container
        stop = AsyncMock(return_value=True)
        remove = AsyncMock(return_value=True)
        application_collection = _ApplicationCollection(application)
        docker_manager.running_apps.clear()
        docker_manager._app_start_locks.clear()
        try:
            with (
                patch.object(
                    docker_manager.app_storage_service,
                    "get_storage",
                    new=AsyncMock(return_value=storage),
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "list_containers",
                    return_value=[],
                ),
                patch.object(docker_manager.docker_manager, "client", fake_client),
                patch.object(
                    docker_manager.docker_manager,
                    "create_container",
                    side_effect=create_container,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "start_container",
                    side_effect=start_container,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "get_container_environment",
                    return_value={"RUNTIME_GENERATION": "1"},
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "stop_container",
                    new=stop,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "remove_container",
                    new=remove,
                ),
                patch.object(
                    docker_manager.Application,
                    "find_one",
                    new=AsyncMock(return_value=application),
                ),
                patch.object(
                    docker_manager.mongodb_manager,
                    "get_collection",
                    return_value=application_collection,
                ),
                patch.object(
                    docker_manager.socket,
                    "gethostbyname",
                    return_value="127.0.0.1",
                ),
                patch.object(
                    docker_manager.asyncio,
                    "to_thread",
                    side_effect=_run_in_managed_thread,
                ),
                patch(
                    "core.initialization.create_function_templates_for_app",
                    new=AsyncMock(),
                ),
                patch.object(docker_manager, "create_traefik_web_config"),
            ):
                startup = asyncio.create_task(
                    docker_manager.start_app_container(application)
                )
                for _ in range(100):
                    if thread_started.is_set():
                        break
                    await asyncio.sleep(0.002)
                self.assertTrue(thread_started.is_set())
                docker_manager.running_apps[application.app_id] = {
                    "id": "stale-container",
                    "name": "hyac-app-runtime-app12345",
                    "generation": 1,
                }
                startup.cancel()
                await asyncio.sleep(0.02)
                cancellation_waited_for_thread = not startup.done()
                release_thread.set()
                result = await asyncio.gather(startup, return_exceptions=True)

                self.assertTrue(cancellation_waited_for_thread)
                self.assertIsInstance(result[0], asyncio.CancelledError)
                self.assertTrue(thread_finished.is_set())
                self.assertIsNone(application.runtime_token_hash)
                self.assertNotIn(application.app_id, docker_manager.running_apps)
                stop.assert_awaited_once_with("container-1")
                remove.assert_awaited_once_with("container-1")

                restarted = await docker_manager.start_app_container(application)

            self.assertEqual(application.runtime_generation, 2)
            self.assertEqual(restarted["generation"], 2)
            self.assertEqual(
                docker_manager.running_apps[application.app_id]["generation"], 2
            )
            pending_tasks = [
                repr(task)
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task() and not task.done()
            ]
            self.assertEqual(pending_tasks, [])
        finally:
            release_thread.set()
            docker_manager.running_apps.clear()
            docker_manager._app_start_locks.clear()

    async def test_cancelled_create_is_collected_and_cleaned(self):
        await self._assert_cancelled_start_is_collected_and_cleaned("create")

    async def test_cancelled_start_is_collected_and_cleaned(self):
        await self._assert_cancelled_start_is_collected_and_cleaned("start")

    async def test_cancelled_reload_is_collected_and_cleaned(self):
        await self._assert_cancelled_start_is_collected_and_cleaned("reload")

    async def test_cancelled_stop_and_remove_collect_side_effect_threads(self):
        for operation_name in ("stop_container", "remove_container"):
            with self.subTest(operation_name=operation_name):
                thread_started = threading.Event()
                release_thread = threading.Event()
                thread_finished = threading.Event()

                def blocking_side_effect(*_args, **_kwargs):
                    thread_started.set()
                    release_thread.wait(timeout=1)
                    thread_finished.set()

                container = SimpleNamespace(
                    status="running",
                    stop=blocking_side_effect,
                    remove=blocking_side_effect,
                )
                fake_client = SimpleNamespace(
                    containers=SimpleNamespace(get=MagicMock(return_value=container))
                )
                with (
                    patch.object(docker_manager.docker_manager, "client", fake_client),
                    patch.object(
                        docker_manager.asyncio,
                        "to_thread",
                        side_effect=_run_in_managed_thread,
                    ),
                ):
                    operation = asyncio.create_task(
                        getattr(docker_manager.docker_manager, operation_name)(
                            "container-1"
                        )
                    )
                    for _ in range(100):
                        if thread_started.is_set():
                            break
                        await asyncio.sleep(0.002)
                    self.assertTrue(thread_started.is_set())
                    operation.cancel()
                    await asyncio.sleep(0.02)
                    cancellation_waited_for_thread = not operation.done()
                    release_thread.set()
                    result = await asyncio.gather(
                        operation, return_exceptions=True
                    )

                self.assertTrue(cancellation_waited_for_thread)
                self.assertIsInstance(result[0], asyncio.CancelledError)
                self.assertTrue(thread_finished.is_set())

    async def test_stop_container_treats_nonrunning_and_api_304_as_success(self):
        for status, api_304 in (
            ("created", False),
            ("dead", False),
            ("running", True),
        ):
            with self.subTest(status=status, api_304=api_304):
                stop_side_effect = None
                if api_304:
                    stop_side_effect = docker_manager.errors.APIError(
                        "not modified",
                        response=SimpleNamespace(status_code=304),
                    )
                container = SimpleNamespace(
                    status=status,
                    stop=MagicMock(side_effect=stop_side_effect),
                )
                get_container = MagicMock(return_value=container)
                fake_client = SimpleNamespace(
                    containers=SimpleNamespace(get=get_container)
                )
                with (
                    patch.object(
                        docker_manager.docker_manager,
                        "client",
                        fake_client,
                    ),
                    patch.object(
                        docker_manager.asyncio,
                        "to_thread",
                        side_effect=_run_in_fresh_thread,
                    ),
                ):
                    stopped = await docker_manager.docker_manager.stop_container(
                        "container-exact-id"
                    )

                self.assertTrue(stopped)
                get_container.assert_called_once_with("container-exact-id")
                if api_304:
                    container.stop.assert_called_once()
                else:
                    container.stop.assert_not_called()

    async def test_failed_start_clears_stale_registry_and_issued_token(self):
        application = SimpleNamespace(
            app_id="APP12345",
            db_password="db-secret",
            runtime_generation=0,
            runtime_token_hash=None,
            runtime_memory_mb=512,
            runtime_cpus=1.0,
            runtime_pids_limit=128,
            environment_variables=[],
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )
        storage = SimpleNamespace(
            status=StorageStatus.READY,
            access_key="access",
            secret_key="secret",
        )
        server_container = SimpleNamespace(
            attrs={
                "NetworkSettings": {"Networks": {"hyac_network": {}}},
                "Config": {"Labels": {}},
            }
        )
        fake_client = SimpleNamespace(
            containers=SimpleNamespace(get=MagicMock(return_value=server_container))
        )
        docker_manager.running_apps[application.app_id] = {
            "id": "missing-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 0,
        }
        runtime_state = {}
        try:
            with (
                patch.object(
                    docker_manager.app_storage_service,
                    "get_storage",
                    new=AsyncMock(return_value=storage),
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "list_containers",
                    return_value=[],
                ),
                patch.object(docker_manager.docker_manager, "client", fake_client),
                patch.object(
                    docker_manager.docker_manager,
                    "create_container",
                    return_value=None,
                ) as create,
                patch.object(
                    docker_manager.docker_manager,
                    "get_container_environment",
                    return_value=None,
                    create=True,
                ),
                patch.object(
                    docker_manager.Application,
                    "find_one",
                    new=AsyncMock(return_value=application),
                ),
                patch.object(
                    docker_manager.asyncio,
                    "to_thread",
                    side_effect=_run_in_fresh_thread,
                ),
            ):
                result = await docker_manager.start_app_container(
                    application,
                    runtime_state=runtime_state,
                )

            self.assertIsNone(result)
            self.assertEqual(runtime_state["runtime_generation"], 1)
            create.assert_called_once()
            self.assertIsNone(application.runtime_token_hash)
            self.assertNotIn(application.app_id, docker_manager.running_apps)
        finally:
            docker_manager.running_apps.clear()
            docker_manager._app_start_locks.clear()

    async def test_old_generation_cleanup_preserves_new_runtime(self):
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=2,
            runtime_token_hash="new-token-hash",
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )
        docker_manager.running_apps[application.app_id] = {
            "id": "new-container",
            "name": "hyac-app-runtime-app12345",
            "generation": 2,
        }
        try:
            application_collection = _ApplicationCollection(application)
            with (
                patch.object(
                    docker_manager.Application,
                    "find_one",
                    new=AsyncMock(return_value=application),
                ),
                patch.object(
                    docker_manager.mongodb_manager,
                    "get_collection",
                    return_value=application_collection,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "stop_container",
                    new=AsyncMock(return_value=True),
                ) as stop,
                patch.object(
                    docker_manager.docker_manager,
                    "remove_container",
                    new=AsyncMock(return_value=True),
                ) as remove,
                patch.object(
                    docker_manager, "remove_traefik_web_config"
                ) as remove_config,
            ):
                cleaned = await docker_manager._cleanup_runtime_generation(
                    application.app_id,
                    "hyac-app-runtime-app12345",
                    1,
                    "old-container",
                )

            self.assertFalse(cleaned)
            stop.assert_not_awaited()
            remove.assert_not_awaited()
            self.assertEqual(application.runtime_token_hash, "new-token-hash")
            application.save.assert_not_awaited()
            remove_config.assert_not_called()
            self.assertEqual(
                docker_manager.running_apps[application.app_id]["generation"], 2
            )
        finally:
            docker_manager.running_apps.clear()

    async def test_generation_cleanup_reports_unconfirmed_container_removal(self):
        application = SimpleNamespace(
            app_id="APP12345",
            runtime_generation=1,
            runtime_token_hash="token-hash",
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )
        docker_manager.running_apps[application.app_id] = {
            "id": "container-1",
            "name": "hyac-app-runtime-app12345",
            "generation": 1,
        }
        try:
            application_collection = _ApplicationCollection(application)
            with (
                patch.object(
                    docker_manager.Application,
                    "find_one",
                    new=AsyncMock(return_value=application),
                ),
                patch.object(
                    docker_manager.mongodb_manager,
                    "get_collection",
                    return_value=application_collection,
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "stop_container",
                    new=AsyncMock(return_value=True),
                ),
                patch.object(
                    docker_manager.docker_manager,
                    "remove_container",
                    new=AsyncMock(return_value=False),
                ),
                patch.object(
                    docker_manager,
                    "remove_traefik_web_config_for_generation",
                ) as remove_config,
            ):
                with self.assertRaises(RuntimeError):
                    await docker_manager._cleanup_runtime_generation(
                        application.app_id,
                        "hyac-app-runtime-app12345",
                        1,
                        "container-1",
                    )

            self.assertIsNone(application.runtime_token_hash)
            application.save.assert_not_awaited()
            remove_config.assert_not_called()
            self.assertIn(application.app_id, docker_manager.running_apps)
        finally:
            docker_manager.running_apps.clear()

    async def test_stop_uses_deterministic_name_without_registry_entry(self):
        application = SimpleNamespace(app_id="APP12345")
        docker_manager.running_apps.clear()
        with (
            patch.object(
                docker_manager.Application,
                "find_one",
                new=AsyncMock(return_value=application),
            ),
            patch.object(
                docker_manager, "_revoke_runtime_token", new=AsyncMock()
            ),
            patch.object(
                docker_manager.docker_manager,
                "stop_container",
                new=AsyncMock(return_value=True),
            ) as stop,
            patch.object(
                docker_manager.docker_manager,
                "remove_container",
                new=AsyncMock(return_value=True),
            ) as remove,
            patch.object(docker_manager, "remove_traefik_web_config") as remove_config,
        ):
            await docker_manager.stop_app_container("APP12345")

        stop.assert_awaited_once_with("hyac-app-runtime-app12345")
        remove.assert_awaited_once_with("hyac-app-runtime-app12345")
        remove_config.assert_called_once_with("APP12345")

    async def test_stop_raises_when_container_removal_is_not_confirmed(self):
        with (
            patch.object(
                docker_manager.Application,
                "find_one",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                docker_manager.docker_manager,
                "stop_container",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                docker_manager.docker_manager,
                "remove_container",
                new=AsyncMock(return_value=False),
            ),
        ):
            with self.assertRaises(RuntimeError):
                await docker_manager.stop_app_container("APP12345")

    async def test_delete_stops_on_cleanup_failure_and_keeps_application(self):
        application = SimpleNamespace(
            app_id="APP12345",
            app_name="Example",
            delete=AsyncMock(),
        )
        with (
            patch.object(
                docker_manager,
                "_stop_app_container_locked",
                new=AsyncMock(side_effect=RuntimeError("runtime cleanup failed")),
            )
        ):
            with self.assertRaisesRegex(RuntimeError, "runtime cleanup failed"):
                await docker_manager.delete_application_background(application)

        application.delete.assert_not_awaited()

    async def test_runtime_has_separate_writable_dependency_tmpfs(self):
        loop_thread = threading.get_ident()
        docker_threads = []

        def docker_call(result):
            def invoke(*_args, **_kwargs):
                docker_threads.append(threading.get_ident())
                return result

            return invoke

        application = SimpleNamespace(
            app_id="APP12345",
            db_password="db-secret",
            runtime_generation=0,
            runtime_token_hash=None,
            runtime_memory_mb=512,
            runtime_cpus=1.0,
            runtime_pids_limit=128,
            environment_variables=[
                SimpleNamespace(key="SECRET_KEY", value="legacy-secret"),
                SimpleNamespace(key="MONGODB_PASSWORD", value="legacy-mongo"),
                SimpleNamespace(key="USER_ALLOWED", value="visible"),
            ],
            update_timestamp=MagicMock(),
            save=AsyncMock(),
        )
        storage = SimpleNamespace(
            status=StorageStatus.READY,
            access_key="access",
            secret_key="secret",
        )
        runtime_container = SimpleNamespace(
            id="container-1",
            attrs={"State": {"Health": {"Status": "healthy"}}},
            reload=MagicMock(side_effect=docker_call(None)),
        )
        server_container = SimpleNamespace(
            attrs={
                "NetworkSettings": {"Networks": {"hyac_network": {}}},
                "Config": {"Labels": {}},
            }
        )
        fake_client = SimpleNamespace(
            containers=SimpleNamespace(
                get=MagicMock(side_effect=docker_call(server_container))
            )
        )
        docker_manager.running_apps.clear()
        with (
            patch.object(
                docker_manager.app_storage_service,
                "get_storage",
                new=AsyncMock(return_value=storage),
            ),
            patch.object(
                docker_manager.docker_manager,
                "list_containers",
                side_effect=docker_call([]),
            ),
            patch.object(
                docker_manager.docker_manager,
                "client",
                fake_client,
            ),
            patch.object(
                docker_manager.Application,
                "find_one",
                new=AsyncMock(return_value=application),
            ),
            patch.object(
                docker_manager.docker_manager,
                "create_container",
                side_effect=docker_call(runtime_container),
            ) as create,
            patch.object(
                docker_manager.docker_manager,
                "start_container",
                side_effect=docker_call(True),
            ),
            patch.object(
                docker_manager.socket, "gethostbyname", return_value="127.0.0.1"
            ),
            patch.object(
                docker_manager.asyncio,
                "to_thread",
                side_effect=_run_in_fresh_thread,
            ),
            patch(
                "core.initialization.create_function_templates_for_app",
                new=AsyncMock(),
            ),
            patch.object(docker_manager, "create_traefik_web_config"),
        ):
            await docker_manager.start_app_container(application)

        tmpfs = create.call_args.kwargs["tmpfs"]
        self.assertIn("noexec", tmpfs["/tmp"])
        self.assertIn("/dependencies", tmpfs)
        self.assertNotIn("noexec", tmpfs["/dependencies"])
        self.assertIn("nodev", tmpfs["/dependencies"])
        self.assertIn("size=256m", tmpfs["/dependencies"])
        runtime_environment = create.call_args.kwargs["environment"]
        self.assertNotIn("SECRET_KEY", runtime_environment)
        self.assertNotIn("MONGODB_PASSWORD", runtime_environment)
        self.assertEqual(runtime_environment["USER_ALLOWED"], "visible")
        self.assertTrue(docker_threads)
        self.assertTrue(all(thread_id != loop_thread for thread_id in docker_threads))

        application.status = ApplicationStatus.RUNNING
        containers = [
            {
                "id": "container-1",
                "name": "hyac-app-runtime-app12345",
                "status": "running",
                "health_status": "healthy",
            }
        ]

        class FakeApplication:
            @classmethod
            def find(cls, *_args, **_kwargs):
                return _ApplicationQuery([application])

        stop = AsyncMock(return_value=True)
        remove = AsyncMock(return_value=True)
        enqueue = AsyncMock()
        with (
            patch.object(task_worker, "Application", FakeApplication),
            patch.object(
                task_worker.mongodb_manager,
                "get_collection",
                return_value=_ApplicationCollection(application),
            ),
            patch.object(
                task_worker,
                "_active_lifecycle_app_ids",
                new=AsyncMock(return_value=set()),
            ),
            patch.object(
                task_worker.docker_manager,
                "list_containers",
                return_value=containers,
            ),
            patch.object(
                task_worker.docker_manager,
                "get_container_environment",
                return_value=runtime_environment,
            ),
            patch.object(
                task_worker.asyncio,
                "to_thread",
                side_effect=_run_in_fresh_thread,
            ),
            patch.object(
                task_worker.docker_manager,
                "stop_container",
                new=stop,
            ),
            patch.object(
                task_worker.docker_manager,
                "remove_container",
                new=remove,
            ),
            patch.object(task_worker, "_enqueue_start", new=enqueue),
        ):
            await task_worker.reconcile_running_apps()
            await task_worker.reconcile_running_apps()

        stop.assert_not_awaited()
        remove.assert_not_awaited()
        enqueue.assert_not_awaited()
        docker_manager.running_apps.clear()
