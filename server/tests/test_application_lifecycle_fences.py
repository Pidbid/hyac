import asyncio
import os
from copy import deepcopy
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from models.applications_model import ApplicationStatus
from models.tasks_model import TaskAction
from routers import applications as applications_router


class _Field:
    def __eq__(self, other):
        return other


class _ApplicationModel:
    app_id = _Field()
    users = _Field()
    find_one = None


class _TransactionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.snapshot = deepcopy(self.session.collection.state)
        return self.session

    async def __aexit__(self, exc_type, _exc, _traceback):
        if exc_type is not None and self.session.did_write:
            self.session.collection.state.clear()
            self.session.collection.state.update(self.session.snapshot)


class _Session:
    def __init__(self, collection):
        self.collection = collection
        self.snapshot = None
        self.did_write = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return None

    async def start_transaction(self):
        return _TransactionContext(self)

    async def with_transaction(self, callback):
        async with await self.start_transaction():
            return await callback(self)


class _Client:
    def __init__(self, collection):
        self.collection = collection

    def start_session(self):
        return _Session(self.collection)


class _LifecycleCollection:
    def __init__(self, state):
        self.state = state
        self.lock = asyncio.Lock()
        self.update_calls = []

    async def update_one(self, query, update, session=None):
        self.update_calls.append((query, update, session))
        async with self.lock:
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
            if session is not None:
                session.did_write = True
            return SimpleNamespace(matched_count=1)

    async def find_one(self, _query, session=None):
        return None


def _manager_for(collection):
    return SimpleNamespace(
        client=_Client(collection),
        get_collection=MagicMock(return_value=collection),
    )


class ApplicationLifecycleFenceTests(IsolatedAsyncioTestCase):
    async def test_concurrent_lifecycle_transitions_have_one_winner(self):
        state = {
            "app_id": "APP12345",
            "app_name": "demo",
            "users": ["owner"],
            "status": ApplicationStatus.RUNNING,
            "lifecycle_revision": 4,
        }
        collection = _LifecycleCollection(state)
        both_loaded = asyncio.Event()
        load_count = 0

        async def find_application(*_conditions):
            nonlocal load_count
            snapshot = SimpleNamespace(**deepcopy(state))

            async def save_snapshot():
                state.update(vars(snapshot))

            snapshot.save = AsyncMock(side_effect=save_snapshot)
            snapshot.update_timestamp = MagicMock()
            load_count += 1
            if load_count == 2:
                both_loaded.set()
            await both_loaded.wait()
            return snapshot

        inserted_tasks = []

        class FakeTask:
            def __init__(self, **kwargs):
                self.task_id = f"task-{len(inserted_tasks) + 1}"
                self.kwargs = kwargs

            async def insert(self, session=None):
                inserted_tasks.append((self.kwargs, session))

        _ApplicationModel.find_one = find_application
        with (
            patch.object(applications_router, "Application", _ApplicationModel),
            patch.object(applications_router, "Task", new=FakeTask),
            patch.object(
                applications_router,
                "mongodb_manager",
                _manager_for(collection),
            ),
        ):
            results = await asyncio.gather(
                applications_router.stop_application(
                    applications_router.ApplicationOperationRequest(
                        appId="APP12345"
                    ),
                    SimpleNamespace(username="owner"),
                ),
                applications_router.delete_application(
                    applications_router.DeleteApplicationRequest(appId="APP12345"),
                    SimpleNamespace(username="owner"),
                ),
                return_exceptions=True,
            )

        self.assertEqual(
            sum(isinstance(result, applications_router.BaseResponse) for result in results),
            1,
        )
        conflicts = [
            result
            for result in results
            if isinstance(result, applications_router.HTTPException)
        ]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].status_code, 409)
        self.assertEqual(len(inserted_tasks), 1)
        self.assertEqual(state["lifecycle_revision"], 5)
        self.assertIn(
            state["status"],
            {ApplicationStatus.STOPPING, ApplicationStatus.DELETING},
        )

    async def test_task_insert_failure_rolls_back_lifecycle_transition(self):
        state = {
            "app_id": "APP12345",
            "app_name": "demo",
            "users": ["owner"],
            "status": ApplicationStatus.RUNNING,
            "lifecycle_revision": 4,
        }
        collection = _LifecycleCollection(state)
        application = SimpleNamespace(**deepcopy(state))
        application.update_timestamp = MagicMock()

        async def save_snapshot():
            state.update(vars(application))

        application.save = AsyncMock(side_effect=save_snapshot)

        class FailingTask:
            def __init__(self, **_kwargs):
                self.task_id = "task-fails"

            async def insert(self, session=None):
                raise RuntimeError("task insert failed")

        async def find_application(*_conditions):
            return application

        _ApplicationModel.find_one = find_application
        with (
            patch.object(applications_router, "Application", _ApplicationModel),
            patch.object(applications_router, "Task", new=FailingTask),
            patch.object(
                applications_router,
                "mongodb_manager",
                _manager_for(collection),
            ),
            self.assertRaisesRegex(RuntimeError, "task insert failed"),
        ):
            await applications_router.restart_application(
                applications_router.ApplicationOperationRequest(appId="APP12345"),
                SimpleNamespace(username="owner"),
            )

        self.assertEqual(state["status"], ApplicationStatus.RUNNING)
        self.assertEqual(state["lifecycle_revision"], 4)

    async def test_start_rejects_deleting_application_without_creating_task(self):
        application = SimpleNamespace(
            app_id="APP12345",
            status=ApplicationStatus.DELETING,
            lifecycle_revision=4,
            save=AsyncMock(),
        )
        task_factory = MagicMock()

        async def find_application(*_conditions):
            return application

        _ApplicationModel.find_one = find_application
        with (
            patch.object(applications_router, "Application", _ApplicationModel),
            patch.object(applications_router, "Task", new=task_factory),
        ):
            response = await applications_router.start_application(
                applications_router.ApplicationOperationRequest(appId="APP12345"),
                SimpleNamespace(username="owner"),
            )

        self.assertEqual(response.code, 400)
        self.assertEqual(application.status, ApplicationStatus.DELETING)
        self.assertEqual(application.lifecycle_revision, 4)
        application.save.assert_not_awaited()
        task_factory.assert_not_called()

    async def test_restart_commits_revision_before_task_is_visible(self):
        events = []
        created_tasks = []
        state = {
            "app_id": "APP12345",
            "users": ["owner"],
            "status": ApplicationStatus.RUNNING,
            "lifecycle_revision": 4,
        }
        application = SimpleNamespace(
            app_id="APP12345",
            status=ApplicationStatus.RUNNING,
            lifecycle_revision=4,
        )
        collection = _LifecycleCollection(state)
        original_update_one = collection.update_one

        async def update_application(*args, **kwargs):
            events.append("application_updated")
            return await original_update_one(*args, **kwargs)

        collection.update_one = update_application

        class FakeTask:
            def __init__(self, **kwargs):
                events.append("task_constructed")
                self.task_id = "task-1"
                self.kwargs = kwargs
                created_tasks.append(self)

            async def insert(self, session=None):
                self.session = session
                events.append("task_inserted")

        async def find_application(*_conditions):
            return application

        _ApplicationModel.find_one = find_application
        with (
            patch.object(applications_router, "Application", _ApplicationModel),
            patch.object(applications_router, "Task", new=FakeTask),
            patch.object(
                applications_router,
                "mongodb_manager",
                _manager_for(collection),
            ),
        ):
            response = await applications_router.restart_application(
                applications_router.ApplicationOperationRequest(appId="APP12345"),
                SimpleNamespace(username="owner"),
            )

        self.assertEqual(
            events,
            ["task_constructed", "application_updated", "task_inserted"],
        )
        self.assertEqual(application.status, ApplicationStatus.STARTING)
        self.assertEqual(application.lifecycle_revision, 5)
        self.assertEqual(response.data["task_id"], "task-1")
        self.assertEqual(created_tasks[0].kwargs["action"], TaskAction.RESTART_APP)
        self.assertIsNotNone(created_tasks[0].session)
        self.assertEqual(
            created_tasks[0].kwargs["payload"],
            {"app_id": "APP12345", "lifecycle_revision": 5},
        )
