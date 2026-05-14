import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

fake_loguru = types.ModuleType("loguru")
fake_loguru.logger = object()
sys.modules.setdefault("loguru", fake_loguru)

fake_pymongo = types.ModuleType("pymongo")
fake_pymongo.MongoClient = object
sys.modules.setdefault("pymongo", fake_pymongo)

fake_async_database_module = types.ModuleType("pymongo.asynchronous.database")
fake_async_database_module.AsyncDatabase = object
sys.modules.setdefault("pymongo.asynchronous.database", fake_async_database_module)

fake_database_module = types.ModuleType("pymongo.database")
fake_database_module.Database = object
sys.modules.setdefault("pymongo.database", fake_database_module)

fake_s3_context = types.ModuleType("core.s3_context")


class FakeS3Context:
    def __init__(self, bucket_name):
        self.bucket_name = bucket_name


fake_s3_context.S3Context = FakeS3Context
sys.modules.setdefault("core.s3_context", fake_s3_context)

fake_code_loader = types.ModuleType("code_loader")
fake_code_loader.CodeLoader = object
sys.modules.setdefault("code_loader", fake_code_loader)

fake_env_manager = types.ModuleType("core.env_manager")


async def fake_set_dynamic_env(key, value):
    return None


fake_env_manager.set_dynamic_env = fake_set_dynamic_env
sys.modules.setdefault("core.env_manager", fake_env_manager)

fake_notification_manager = types.ModuleType("core.notification_manager")


class FakeNotificationManager:
    def __init__(self, config):
        self.config = config


fake_notification_manager.NotificationManager = FakeNotificationManager
sys.modules.setdefault("core.notification_manager", fake_notification_manager)

fake_applications_model = types.ModuleType("models.applications_model")
fake_applications_model.NotificationConfig = object
sys.modules.setdefault("models.applications_model", fake_applications_model)

from cloud import CloudFacade  # noqa: E402
from context import EnvContext, FunctionContext  # noqa: E402


class CloudFacadeTest(TestCase):
    def test_function_context_exposes_stable_cloud_facade(self):
        async_db = object()
        sync_db = object()
        env = EnvContext()
        common = SimpleNamespace(math=object())
        config = object()

        ctx = FunctionContext(
            app_id="DemoApp",
            func_id="func123",
            pymongo_db=sync_db,
            async_db=async_db,
            code_loader=object(),
            env=env,
            common=common,
            notification_config=config,
        )

        self.assertIsInstance(ctx.cloud, CloudFacade)
        self.assertIs(ctx.cloud.database(), async_db)
        self.assertIs(ctx.cloud.database(sync=True), sync_db)
        self.assertIs(ctx.cloud.storage(), ctx.s3)
        self.assertIs(ctx.cloud.env(), env)
        self.assertIs(ctx.cloud.logger(), ctx.logger)
        self.assertIs(ctx.cloud.notification(), ctx.notification)
        self.assertIs(ctx.cloud.common(), common)

    def test_cloud_facade_preserves_legacy_context_resources(self):
        context = SimpleNamespace(
            async_db=object(),
            pymongo_db=object(),
            s3=object(),
            env=object(),
            logger=object(),
            notification=object(),
            common=SimpleNamespace(),
        )

        cloud = CloudFacade(context)

        self.assertIs(cloud.database(), context.async_db)
        self.assertIs(cloud.database(sync=True), context.pymongo_db)
        self.assertIs(cloud.storage(), context.s3)
        self.assertIs(cloud.env(), context.env)
        self.assertIs(cloud.logger(), context.logger)
        self.assertIs(cloud.notification(), context.notification)
        self.assertIs(cloud.common(), context.common)
