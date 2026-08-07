import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, call, patch


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from core import app_storage, docker_manager
from core.app_storage import AppStorageService
from core.s3_manager import S3Manager, s3_manager
from models.storage_model import StorageStatus


class _Field:
    def __eq__(self, other):
        return other


class _StorageRecord:
    def __init__(self, app_id: str):
        self.app_id = app_id
        self.access_key = app_id.lower()
        self.status = StorageStatus.READY
        self.last_error = None
        self.save = AsyncMock()
        self.delete = AsyncMock()

    def mark_error(self, error: str):
        self.status = StorageStatus.ERROR
        self.last_error = error


class _BucketRecord:
    def __init__(self, app_id: str, bucket_name: str):
        self.app_id = app_id
        self.bucket_name = bucket_name
        self.status = StorageStatus.READY
        self.last_error = None
        self.save = AsyncMock()
        self.delete = AsyncMock()

    def mark_error(self, error: str):
        self.status = StorageStatus.ERROR
        self.last_error = error


class AppStorageDeletionTests(IsolatedAsyncioTestCase):
    async def test_user_removal_failure_keeps_metadata_for_successful_retry(self):
        service = AppStorageService()
        storage = _StorageRecord("APP12345")
        bucket = _BucketRecord("APP12345", "custom-bucket")
        bucket_query = SimpleNamespace(
            to_list=AsyncMock(return_value=[bucket])
        )

        class FakeStorageBucket:
            app_id = _Field()
            find = MagicMock()

        FakeStorageBucket.find = MagicMock(return_value=bucket_query)
        remove_user = AsyncMock(
            side_effect=[
                (False, "object-storage API unavailable"),
                (True, "user removed"),
            ]
        )

        with (
            patch.object(
                service,
                "get_storage",
                new=AsyncMock(return_value=storage),
            ),
            patch.object(app_storage, "StorageBucket", FakeStorageBucket),
            patch.object(
                service,
                "_delete_bucket_if_exists",
                new=AsyncMock(),
            ) as delete_bucket,
            patch.object(s3_manager, "remove_user", new=remove_user),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "object-storage API unavailable"
            ):
                await service.delete_resources(storage.app_id)

            storage.delete.assert_not_awaited()
            bucket.delete.assert_not_awaited()
            self.assertEqual(storage.status, StorageStatus.ERROR)
            self.assertIn("object-storage API unavailable", storage.last_error)
            self.assertEqual(bucket.status, StorageStatus.ERROR)
            self.assertIn("object-storage API unavailable", bucket.last_error)

            await service.delete_resources(storage.app_id)

        self.assertEqual(
            remove_user.await_args_list,
            [call(storage.access_key), call(storage.access_key)],
        )
        storage.delete.assert_awaited_once()
        bucket.delete.assert_awaited_once()
        expected_bucket_names = {
            "app12345",
            "web-app12345",
            "custom-bucket",
        }
        self.assertEqual(
            [args.args[0] for args in delete_bucket.await_args_list],
            sorted(expected_bucket_names) * 2,
        )

    async def test_delete_application_stays_retryable_when_user_removal_fails(self):
        service = AppStorageService()
        storage = _StorageRecord("APP12345")
        bucket = _BucketRecord("APP12345", "app12345")
        bucket_query = SimpleNamespace(
            to_list=AsyncMock(return_value=[bucket])
        )
        empty_query = SimpleNamespace(to_list=AsyncMock(return_value=[]))
        application = SimpleNamespace(
            app_id=storage.app_id,
            app_name="Example",
            delete=AsyncMock(),
        )

        class FakeStorageBucket:
            app_id = _Field()
            find = MagicMock(return_value=bucket_query)

        class FakeOwnedRecord:
            app_id = _Field()
            find = MagicMock(return_value=empty_query)

        docker_manager._app_start_locks.clear()
        self.addCleanup(docker_manager._app_start_locks.clear)
        with (
            patch.object(
                service,
                "get_storage",
                new=AsyncMock(return_value=storage),
            ),
            patch.object(app_storage, "StorageBucket", FakeStorageBucket),
            patch.object(
                service,
                "_delete_bucket_if_exists",
                new=AsyncMock(),
            ),
            patch.object(
                s3_manager,
                "remove_user",
                new=AsyncMock(return_value=(False, "identity API timeout")),
            ),
            patch.object(
                docker_manager,
                "app_storage_service",
                service,
            ),
            patch.object(
                docker_manager,
                "_stop_app_container_locked",
                new=AsyncMock(return_value=True),
            ),
            patch.object(docker_manager, "Function", FakeOwnedRecord),
            patch.object(docker_manager, "FunctionTemplate", FakeOwnedRecord),
            patch(
                "models.tasks_model.Task.find",
                return_value=empty_query,
            ),
            patch.object(
                docker_manager.dynamic_db.db_client,
                "drop_database",
                new=AsyncMock(),
            ) as drop_database,
            patch.object(
                docker_manager, "remove_traefik_web_config"
            ) as remove_config,
        ):
            with self.assertRaisesRegex(RuntimeError, "identity API timeout"):
                await docker_manager.delete_application_background(application)

        application.delete.assert_not_awaited()
        drop_database.assert_not_awaited()
        remove_config.assert_not_called()
        storage.delete.assert_not_awaited()
        bucket.delete.assert_not_awaited()


class S3UserRemovalContractTests(IsolatedAsyncioTestCase):
    async def test_only_explicit_missing_user_is_treated_as_already_removed(self):
        manager = object.__new__(S3Manager)
        manager._ensure_mc_alias = AsyncMock(return_value=(True, ""))

        for output, expected in (
            ("The specified user does not exist", True),
            ("connection refused by object-storage API", False),
            ("user service endpoint not found", False),
        ):
            with self.subTest(output=output):
                manager._run_mc = AsyncMock(return_value=(False, output))

                result = await manager.remove_user("app12345")

                self.assertEqual(result, (expected, output))
                manager._run_mc.assert_awaited_once_with(
                    "admin", "user", "info", manager._mc_target(), "app12345"
                )
