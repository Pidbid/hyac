import secrets
import string

from loguru import logger
from pymongo.errors import DuplicateKeyError

from core.s3_manager import s3_manager
from models.storage_model import (
    ApplicationStorage,
    StorageBucket,
    StorageBucketPolicy,
    StorageStatus,
)


class AppStorageService:
    """Coordinates per-application storage identity and default buckets."""

    def default_bucket_name(self, app_id: str) -> str:
        return app_id.lower()

    def web_bucket_name(self, app_id: str) -> str:
        return f"web-{app_id.lower()}"

    async def get_storage(self, app_id: str) -> ApplicationStorage | None:
        return await ApplicationStorage.find_one(ApplicationStorage.app_id == app_id)

    async def get_default_bucket(self, app_id: str) -> StorageBucket | None:
        return await StorageBucket.find_one(
            StorageBucket.app_id == app_id,
            StorageBucket.is_default == True,  # noqa: E712
        )

    async def get_default_bucket_name(self, app_id: str) -> str:
        bucket = await self.get_default_bucket(app_id)
        return bucket.bucket_name if bucket else self.default_bucket_name(app_id)

    async def ensure_records(self, app_id: str) -> tuple[ApplicationStorage, StorageBucket]:
        storage = await self.get_storage(app_id)
        if not storage:
            storage = ApplicationStorage(
                app_id=app_id,
                access_key=app_id.lower(),
                secret_key=self._generate_secret_key(),
                status=StorageStatus.CREATING,
            )
            try:
                await storage.insert()
            except DuplicateKeyError:
                storage = await self.get_storage(app_id)
                if not storage:
                    raise

        bucket = await self.get_default_bucket(app_id)
        if not bucket:
            bucket = StorageBucket(
                app_id=app_id,
                bucket_name=self.default_bucket_name(app_id),
                display_name="default",
                policy=StorageBucketPolicy.PRIVATE,
                is_default=True,
                status=StorageStatus.CREATING,
            )
            try:
                await bucket.insert()
            except DuplicateKeyError:
                bucket = await self.get_default_bucket(app_id)
                if not bucket:
                    raise

        return storage, bucket

    async def ensure_ready(self, app_id: str) -> ApplicationStorage:
        """
        Ensures default storage resources exist and returns app-scoped credentials.
        """
        storage, bucket = await self.ensure_records(app_id)

        try:
            await self._ensure_bucket(bucket)
            await self._ensure_web_bucket(app_id)
            await self._ensure_app_user(storage, [bucket.bucket_name])
        except Exception as exc:
            error = str(exc)
            logger.error(f"Failed to provision storage for app '{app_id}': {error}")
            storage.mark_error(error)
            bucket.mark_error(error)
            await storage.save()
            await bucket.save()
            raise

        storage.mark_ready()
        bucket.mark_ready()
        await storage.save()
        await bucket.save()
        return storage

    async def delete_resources(self, app_id: str):
        """Deletes app storage buckets, app storage user, and metadata records."""
        storage = await self.get_storage(app_id)
        buckets = await StorageBucket.find(StorageBucket.app_id == app_id).to_list()

        if storage:
            storage.status = StorageStatus.DELETING
            await storage.save()

        for bucket in buckets:
            bucket.status = StorageStatus.DELETING
            await bucket.save()

        bucket_names = {bucket.bucket_name for bucket in buckets}
        bucket_names.add(self.default_bucket_name(app_id))
        bucket_names.add(self.web_bucket_name(app_id))

        for bucket_name in sorted(bucket_names):
            await self._delete_bucket_if_exists(bucket_name)

        if storage:
            ok, output = await s3_manager.remove_user(storage.access_key)
            if not ok:
                error = (
                    f"failed to remove storage user '{storage.access_key}': "
                    f"{output}"
                )
                logger.error(error)
                storage.mark_error(error)
                await storage.save()
                for bucket in buckets:
                    bucket.mark_error(error)
                    await bucket.save()
                raise RuntimeError(error)
            await storage.delete()

        for bucket in buckets:
            await bucket.delete()

    async def _ensure_bucket(self, bucket: StorageBucket):
        if not await s3_manager.bucket_exists(bucket.bucket_name):
            if not await s3_manager.make_bucket(bucket.bucket_name):
                raise RuntimeError(f"failed to create bucket '{bucket.bucket_name}'")

        if bucket.policy == StorageBucketPolicy.PUBLIC_READ:
            await s3_manager.set_bucket_to_public_read(bucket.bucket_name)
        else:
            current_policy = await s3_manager.get_bucket_policy(bucket.bucket_name)
            if current_policy:
                await s3_manager.delete_bucket_policy(bucket.bucket_name)

    async def _ensure_web_bucket(self, app_id: str):
        bucket_name = self.web_bucket_name(app_id)
        if not await s3_manager.bucket_exists(bucket_name):
            if not await s3_manager.make_bucket(bucket_name):
                raise RuntimeError(f"failed to create web bucket '{bucket_name}'")
        await s3_manager.set_bucket_to_public_read(bucket_name)

    async def _ensure_app_user(
        self, storage: ApplicationStorage, bucket_names: list[str]
    ):
        ok, output = await s3_manager.ensure_user(
            storage.access_key, storage.secret_key
        )
        if not ok:
            raise RuntimeError(f"failed to ensure storage user: {output}")

        policy_name = f"hyac-{storage.app_id.lower()}-storage"
        ok, output = await s3_manager.attach_bucket_policy_to_user(
            storage.access_key, policy_name, bucket_names
        )
        if not ok:
            raise RuntimeError(f"failed to attach storage policy: {output}")

    async def _delete_bucket_if_exists(self, bucket_name: str):
        if not await s3_manager.bucket_exists(bucket_name):
            return

        objects = await s3_manager.list_objects(bucket_name, recursive=True)
        if objects:
            for obj in objects:
                await s3_manager.delete_object(bucket_name, obj["name"])

        if not await s3_manager.remove_bucket(bucket_name):
            raise RuntimeError(f"failed to remove bucket '{bucket_name}'")

    def _generate_secret_key(self, length: int = 64) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))


app_storage_service = AppStorageService()
