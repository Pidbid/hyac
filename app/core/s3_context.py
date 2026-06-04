# app/core/s3_context.py
import asyncio
import io
from typing import Any, List, Dict, Optional
from loguru import logger
from minio import Minio
from minio.error import S3Error
from core.config import settings


class S3Context:
    """
    Provides a simplified interface for interacting with an S3-compatible bucket
    associated with the application.
    """

    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name.lower()
        self.client = None
        endpoint = settings.object_storage_internal_endpoint
        access_key = settings.object_storage_access_key
        secret_key = settings.object_storage_secret_key

        if not all([endpoint, access_key, secret_key]):
            logger.warning(
                "S3 environment variables not fully set; client not initialized."
            )
            return

        try:
            self.client = Minio(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=bool(settings.S3_SECURE_INTERNAL),
                region=settings.S3_REGION,
            )
            logger.info(
                f"S3-compatible object storage client initialized for bucket '{self.bucket_name}'."
            )
        except Exception as e:
            logger.error(
                f"Failed to initialize S3 client for bucket '{self.bucket_name}': {e}"
            )
            self.client = None

    def _check_client(self) -> bool:
        if not self.client:
            logger.error("S3 client is not initialized.")
            return False
        return True

    async def put(self, object_name: str, data: bytes) -> bool:
        """Uploads data to an object."""
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            await asyncio.to_thread(
                self.client.put_object,
                self.bucket_name,
                object_name,
                io.BytesIO(data),
                len(data),
            )
            return True
        except S3Error as e:
            logger.error(f"Failed to put object '{object_name}': {e}")
            return False

    async def get(self, object_name: str) -> Optional[bytes]:
        """Gets an object's data."""
        if not self._check_client():
            return None
        assert self.client is not None
        try:
            response = await asyncio.to_thread(
                self.client.get_object, self.bucket_name, object_name
            )
            return response.read()
        except S3Error as e:
            logger.error(f"Failed to get object '{object_name}': {e}")
            return None
        finally:
            if "response" in locals() and response:
                response.close()
                response.release_conn()

    async def delete(self, object_name: str) -> bool:
        """Deletes an object."""
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            await asyncio.to_thread(
                self.client.remove_object, self.bucket_name, object_name
            )
            return True
        except S3Error as e:
            logger.error(f"Failed to delete object '{object_name}': {e}")
            return False

    async def list(self, prefix: str = "") -> List[Dict[str, Any]]:
        """Lists objects in the bucket."""
        if not self._check_client():
            return []
        assert self.client is not None
        try:
            objects = await asyncio.to_thread(
                self.client.list_objects,
                self.bucket_name,
                prefix=prefix,
                recursive=True,
            )
            return [
                {
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                }
                for obj in objects
            ]
        except S3Error as e:
            logger.error(f"Failed to list objects with prefix '{prefix}': {e}")
            return []
