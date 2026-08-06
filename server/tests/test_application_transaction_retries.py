import asyncio
import os
from copy import deepcopy
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError, OperationFailure


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from models.applications_model import ApplicationStatus
from models.tasks_model import TaskAction
from routers import applications as applications_router


def _labeled_error(label):
    return OperationFailure(
        f"simulated {label}",
        code=251,
        details={"errorLabels": [label]},
    )


class _Field:
    def __eq__(self, other):
        return other


class _TransactionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, _exc, _traceback):
        if exc_type is not None:
            await self.session.abort_transaction()
            return False
        await self.session.commit_transaction()
        return False


class _RetrySession:
    def __init__(self, collection=None, document_types=(), unknown_commits=0):
        self.collection = collection
        self.document_types = tuple(document_types)
        self.unknown_commits = unknown_commits
        self.commit_attempts = 0
        self.transaction_attempts = 0
        self.in_transaction = False
        self._state_snapshot = None
        self._insert_lengths = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return None

    async def start_transaction(self, *_args, **_kwargs):
        self.transaction_attempts += 1
        self.in_transaction = True
        self._state_snapshot = (
            deepcopy(self.collection.state) if self.collection is not None else None
        )
        self._insert_lengths = {
            document_type: len(document_type.inserted)
            for document_type in self.document_types
        }
        return _TransactionContext(self)

    async def abort_transaction(self):
        if self.collection is not None and self._state_snapshot is not None:
            self.collection.state.clear()
            self.collection.state.update(self._state_snapshot)
        for document_type, length in (self._insert_lengths or {}).items():
            transaction_writes = document_type.inserted[length:]
            document_type.inserted[:] = document_type.inserted[:length] + [
                record for record in transaction_writes if record[-1] is not self
            ]
        self.in_transaction = False

    async def commit_transaction(self):
        self.commit_attempts += 1
        if self.unknown_commits:
            self.unknown_commits -= 1
            raise _labeled_error("UnknownTransactionCommitResult")
        self.in_transaction = False

    async def with_transaction(self, callback):
        return await AsyncClientSession.with_transaction(self, callback)


class _Client:
    def __init__(self, session):
        self.session = session

    def start_session(self):
        return self.session


class _LifecycleCollection:
    def __init__(self, state):
        self.state = state
        self.update_calls = []

    async def update_one(self, query, update, session=None):
        self.update_calls.append((query, update, session))
        matches = all(
            value in self.state.get(key, [])
            if key == "users"
            else self.state.get(key) == value
            for key, value in query.items()
        )
        if not matches:
            return SimpleNamespace(matched_count=0)
        for key, value in update.get("$set", {}).items():
            self.state[key] = value
        for key, value in update.get("$inc", {}).items():
            self.state[key] += value
        return SimpleNamespace(matched_count=1)


def _manager_for(session, collection=None):
    return SimpleNamespace(
        client=_Client(session),
        get_collection=MagicMock(return_value=collection),
    )


class _CreateApplication:
    app_name = _Field()
    inserted = []
    insert_attempt_sessions = []
    insert_error = None

    @classmethod
    async def find_one(cls, *_conditions):
        return None

    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)
        self.app_id = "APP-TXN"

    async def insert(self, session=None):
        type(self).insert_attempt_sessions.append(session)
        if type(self).insert_error is not None:
            raise type(self).insert_error
        type(self).inserted.append((self.app_id, session))


class _RetryTask:
    inserted = []
    insert_attempt_ids = []
    insert_attempt_sessions = []
    constructed_ids = []
    transient_failures = 0

    def __init__(self, **values):
        self.task_id = f"task-{len(type(self).constructed_ids) + 1}"
        self.values = values
        type(self).constructed_ids.append(self.task_id)

    async def insert(self, session=None):
        type(self).insert_attempt_ids.append(self.task_id)
        type(self).insert_attempt_sessions.append(session)
        type(self).inserted.append((self.task_id, session))
        if type(self).transient_failures:
            type(self).transient_failures -= 1
            raise _labeled_error("TransientTransactionError")


class _LifecycleApplication:
    app_id = _Field()
    users = _Field()
    find_one = None


class ApplicationTransactionRetryTests(IsolatedAsyncioTestCase):
    def setUp(self):
        _CreateApplication.inserted = []
        _CreateApplication.insert_attempt_sessions = []
        _CreateApplication.insert_error = None
        _RetryTask.inserted = []
        _RetryTask.insert_attempt_ids = []
        _RetryTask.insert_attempt_sessions = []
        _RetryTask.constructed_ids = []
        _RetryTask.transient_failures = 0

    async def test_create_retries_transient_callback_with_stable_task_id(self):
        _RetryTask.transient_failures = 1
        session = _RetrySession(
            document_types=(_CreateApplication, _RetryTask),
        )

        with (
            patch.object(applications_router, "Application", _CreateApplication),
            patch.object(applications_router, "Task", _RetryTask),
            patch.object(
                applications_router,
                "mongodb_manager",
                _manager_for(session),
            ),
            patch.object(applications_router, "generate_short_id", return_value="secret"),
        ):
            response = await applications_router.create_application(
                applications_router.CreateApplicationRequest(appName="demo"),
                SimpleNamespace(username="owner"),
            )

        self.assertEqual(response.code, 0)
        self.assertEqual(response.data["task_id"], "task-1")
        self.assertEqual(_RetryTask.constructed_ids, ["task-1"])
        self.assertEqual(_RetryTask.insert_attempt_ids, ["task-1", "task-1"])
        self.assertEqual(_CreateApplication.insert_attempt_sessions, [session, session])
        self.assertEqual(_RetryTask.insert_attempt_sessions, [session, session])
        self.assertTrue(
            all(attempt_session is session for attempt_session in _CreateApplication.insert_attempt_sessions)
        )
        self.assertTrue(
            all(attempt_session is session for attempt_session in _RetryTask.insert_attempt_sessions)
        )
        self.assertEqual([task_id for task_id, _ in _RetryTask.inserted], ["task-1"])
        self.assertEqual(len(_CreateApplication.inserted), 1)
        self.assertEqual(session.transaction_attempts, 2)

    async def test_lifecycle_resolves_ambiguous_commit_without_duplicate_task(self):
        state = {
            "app_id": "APP12345",
            "app_name": "demo",
            "users": ["owner"],
            "status": ApplicationStatus.RUNNING,
            "lifecycle_revision": 4,
        }
        collection = _LifecycleCollection(state)
        application = SimpleNamespace(**deepcopy(state))

        async def find_application(*_conditions):
            return application

        _LifecycleApplication.find_one = find_application
        session = _RetrySession(
            collection=collection,
            document_types=(_RetryTask,),
            unknown_commits=1,
        )

        with (
            patch.object(applications_router, "Application", _LifecycleApplication),
            patch.object(applications_router, "Task", _RetryTask),
            patch.object(
                applications_router,
                "mongodb_manager",
                _manager_for(session, collection),
            ),
        ):
            response = await applications_router.restart_application(
                applications_router.ApplicationOperationRequest(appId="APP12345"),
                SimpleNamespace(username="owner"),
            )

        self.assertEqual(response.code, 0)
        self.assertEqual(response.data["task_id"], "task-1")
        self.assertEqual(_RetryTask.constructed_ids, ["task-1"])
        self.assertEqual(_RetryTask.insert_attempt_ids, ["task-1"])
        self.assertEqual(_RetryTask.insert_attempt_sessions, [session])
        self.assertIs(_RetryTask.insert_attempt_sessions[0], session)
        self.assertEqual([task_id for task_id, _ in _RetryTask.inserted], ["task-1"])
        self.assertEqual(session.transaction_attempts, 1)
        self.assertEqual(session.commit_attempts, 2)
        self.assertEqual(state["lifecycle_revision"], 5)
        self.assertEqual(state["status"], ApplicationStatus.STARTING)

    async def test_create_unique_index_loser_returns_conflict(self):
        _CreateApplication.insert_error = DuplicateKeyError(
            "duplicate app name",
            code=11000,
        )
        session = _RetrySession(
            document_types=(_CreateApplication, _RetryTask),
        )

        with (
            patch.object(applications_router, "Application", _CreateApplication),
            patch.object(applications_router, "Task", _RetryTask),
            patch.object(
                applications_router,
                "mongodb_manager",
                _manager_for(session),
            ),
        ):
            result = (
                await asyncio.gather(
                    applications_router.create_application(
                        applications_router.CreateApplicationRequest(appName="demo"),
                        SimpleNamespace(username="owner"),
                    ),
                    return_exceptions=True,
                )
            )[0]

        self.assertIsInstance(result, applications_router.HTTPException)
        self.assertEqual(result.status_code, 409)
        self.assertIn("already exists", result.detail)
        self.assertEqual(_RetryTask.insert_attempt_ids, [])

    async def test_repeated_delete_while_deleting_is_side_effect_free(self):
        application = SimpleNamespace(
            app_id="APP12345",
            app_name="demo",
            status=ApplicationStatus.DELETING,
            lifecycle_revision=7,
        )
        authoritative_tasks = ["task-original"]

        async def find_application(*_conditions):
            return application

        async def transition(*_args, **_kwargs):
            application.lifecycle_revision += 1
            authoritative_tasks.append("task-duplicate")
            return SimpleNamespace(task_id="task-duplicate")

        _LifecycleApplication.find_one = find_application
        with (
            patch.object(applications_router, "Application", _LifecycleApplication),
            patch.object(
                applications_router,
                "_transition_and_enqueue",
                side_effect=transition,
            ) as transition_mock,
        ):
            result = (
                await asyncio.gather(
                    applications_router.delete_application(
                        applications_router.DeleteApplicationRequest(appId="APP12345"),
                        SimpleNamespace(username="owner"),
                    ),
                    return_exceptions=True,
                )
            )[0]

        self.assertIsInstance(result, applications_router.HTTPException)
        self.assertEqual(result.status_code, 409)
        self.assertIn("already in progress", result.detail)
        self.assertEqual(application.lifecycle_revision, 7)
        self.assertEqual(authoritative_tasks, ["task-original"])
        transition_mock.assert_not_awaited()

    async def test_delete_rejects_durable_active_start_task(self):
        state = {
            "app_id": "APP12345",
            "app_name": "demo",
            "users": ["owner"],
            "status": ApplicationStatus.STARTING,
            "lifecycle_revision": 1,
        }
        application = SimpleNamespace(**deepcopy(state))
        application_collection = _LifecycleCollection(state)

        class ActiveTaskCollection:
            def __init__(self):
                self.find_calls = []

            async def find_one(self, query, session=None):
                self.find_calls.append((query, session))
                return {
                    "task_id": "active-start",
                    "app_id": state["app_id"],
                    "action": TaskAction.START_APP,
                    "status": "running",
                }

        task_collection = ActiveTaskCollection()

        async def find_application(*_conditions):
            return application

        _LifecycleApplication.find_one = find_application
        session = _RetrySession(
            collection=application_collection,
            document_types=(_RetryTask,),
        )

        def get_collection(model):
            if model is _RetryTask:
                return task_collection
            return application_collection

        manager = SimpleNamespace(
            client=_Client(session),
            get_collection=MagicMock(side_effect=get_collection),
        )
        with (
            patch.object(applications_router, "Application", _LifecycleApplication),
            patch.object(applications_router, "Task", _RetryTask),
            patch.object(applications_router, "mongodb_manager", manager),
        ):
            result = (
                await asyncio.gather(
                    applications_router.delete_application(
                        applications_router.DeleteApplicationRequest(
                            appId=state["app_id"]
                        ),
                        SimpleNamespace(username="owner"),
                    ),
                    return_exceptions=True,
                )
            )[0]

        self.assertIsInstance(result, applications_router.HTTPException)
        self.assertEqual(result.status_code, 409)
        self.assertIn("lifecycle task", result.detail)
        self.assertEqual(state["status"], ApplicationStatus.STARTING)
        self.assertEqual(state["lifecycle_revision"], 1)
        self.assertEqual(_RetryTask.insert_attempt_ids, [])
        self.assertEqual(len(task_collection.find_calls), 1)
        self.assertIs(task_collection.find_calls[0][1], session)


if __name__ == "__main__":
    import unittest

    unittest.main()
