# core/s3_manager.py
import asyncio
import io
import json
import os
import tempfile
from datetime import timedelta
from typing import Dict, List, Optional
from urllib.parse import quote

from loguru import logger
from minio import Minio
from minio.error import S3Error

from core.config import settings


def _download_response_headers(object_name: str) -> dict[str, str]:
    """Returns response headers that ask browsers to download the object."""
    filename = object_name.rsplit("/", 1)[-1] or "download"
    return {
        "response-content-disposition": (
            f"attachment; filename*=UTF-8''{quote(filename)}"
        )
    }


class S3Manager:
    """
    Manages interactions with an S3-compatible object storage server, including bucket and object operations.
    """

    def __init__(self):
        """
        Initializes the S3 client using settings from the application configuration.
        """
        self.client = None
        if not all(
            [
                settings.object_storage_access_key,
                settings.object_storage_secret_key,
            ]
        ):
            logger.warning("S3 configuration is incomplete; client not initialized.")
            return

        try:
            assert settings.object_storage_access_key is not None
            assert settings.object_storage_secret_key is not None
            self.client = Minio(
                endpoint=settings.object_storage_internal_endpoint,
                access_key=settings.object_storage_access_key,
                secret_key=settings.object_storage_secret_key,
                secure=bool(settings.S3_SECURE_INTERNAL),
                region=settings.S3_REGION,
            )
            logger.info("S3-compatible object storage client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize S3-compatible object storage client: {e}")
            self.client = None

    def _check_client(self) -> bool:
        """
        Checks if the S3 client is initialized.
        """
        if not self.client:
            logger.error(
                "S3 client is not initialized. Cannot perform S3 operations."
            )
            return False
        return True

    async def bucket_exists(self, bucket_name: str) -> bool:
        """
        Checks if a bucket exists.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        return await asyncio.to_thread(self.client.bucket_exists, bucket_name)

    async def make_bucket(self, bucket_name: str) -> bool:
        """
        Creates a new bucket if it does not already exist.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            found = await self.bucket_exists(bucket_name)
            if not found:
                await asyncio.to_thread(self.client.make_bucket, bucket_name)
                logger.info(f"Bucket '{bucket_name}' created.")
                return True
            else:
                logger.info(f"Bucket '{bucket_name}' already exists.")
                return True
        except S3Error as e:
            logger.error(f"Failed to create bucket '{bucket_name}': {e}")
            return False

    async def set_bucket_policy(self, bucket_name: str, policy: str):
        """
        Sets the policy for a bucket.
        """
        if not self._check_client():
            logger.error("S3 client is not initialized. Cannot set bucket policy.")
            return
        assert self.client is not None
        await asyncio.to_thread(self.client.set_bucket_policy, bucket_name, policy)

    async def get_bucket_policy(self, bucket_name: str) -> Optional[str]:
        """
        Gets the policy for a bucket. Returns None if no policy is found or an error occurs.
        """
        if not self._check_client():
            return None
        assert self.client is not None
        try:
            return await asyncio.to_thread(self.client.get_bucket_policy, bucket_name)
        except S3Error as e:
            if e.code == "NoSuchBucketPolicy":
                logger.info(f"No policy found for bucket '{bucket_name}'.")
            else:
                logger.error(
                    f"Error getting policy for bucket '{bucket_name}': {e}",
                    exc_info=True,
                )
            return None

    async def delete_bucket_policy(self, bucket_name: str):
        """
        Deletes a bucket policy if the backend supports the operation.
        """
        if not self._check_client():
            logger.error("S3 client is not initialized. Cannot delete bucket policy.")
            return
        assert self.client is not None
        await asyncio.to_thread(self.client.delete_bucket_policy, bucket_name)

    async def set_bucket_to_public_read(self, bucket_name: str):
        """
        Sets a bucket's policy to allow public read access for all objects,
        including ListBucket for root access.
        """
        if not self._check_client():
            return

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                },
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:ListBucket"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}"],
                },
            ],
        }
        try:
            await self.set_bucket_policy(bucket_name, json.dumps(policy))
            logger.info(
                f"Successfully set public read policy for bucket '{bucket_name}'."
            )
        except S3Error as e:
            logger.error(
                f"Failed to set public read policy for bucket '{bucket_name}': {e}"
            )
            raise

    async def create_folder(self, bucket_name: str, folder_name: str) -> bool:
        """
        Creates a folder in a bucket by creating an empty object with a trailing slash.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        if not folder_name.endswith("/"):
            folder_name += "/"
        try:
            await asyncio.to_thread(
                self.client.put_object,
                bucket_name,
                folder_name,
                io.BytesIO(b""),
                0,
            )
            logger.info(f"Folder '{folder_name}' created in bucket '{bucket_name}'.")
            return True
        except S3Error as e:
            logger.error(f"Failed to create folder '{folder_name}': {e}")
            return False

    async def delete_folder(self, bucket_name: str, folder_name: str) -> bool:
        """
        Deletes a folder and all its contents from a bucket.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        if not folder_name.endswith("/"):
            folder_name += "/"
        try:
            objects_to_delete = await asyncio.to_thread(
                self.client.list_objects,
                bucket_name,
                prefix=folder_name,
                recursive=True,
            )
            for obj in objects_to_delete:
                if obj.object_name:
                    await asyncio.to_thread(
                        self.client.remove_object, bucket_name, obj.object_name
                    )
            logger.info(
                f"Folder '{folder_name}' and its contents deleted from bucket '{bucket_name}'."
            )
            return True
        except S3Error as e:
            logger.error(f"Failed to delete folder '{folder_name}': {e}")
            return False

    async def upload_file(
        self, bucket_name: str, object_name: str, file_path: str
    ) -> bool:
        """
        Uploads a local file to a bucket.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            await asyncio.to_thread(
                self.client.fput_object, bucket_name, object_name, file_path
            )
            logger.info(
                f"File '{file_path}' uploaded as '{object_name}' to bucket '{bucket_name}'."
            )
            return True
        except S3Error as e:
            logger.error(f"Failed to upload file '{file_path}': {e}")
            return False

    async def upload_file_stream(
        self, bucket_name: str, object_name: str, file_stream
    ) -> bool:
        """
        Uploads a file-like object to a bucket using a stream.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            # Get the size of the file by seeking to the end
            file_stream.file.seek(0, io.SEEK_END)
            file_size = file_stream.file.tell()
            file_stream.file.seek(0, io.SEEK_SET)

            await asyncio.to_thread(
                self.client.put_object,
                bucket_name,
                object_name,
                file_stream.file,
                length=file_size,
                content_type=file_stream.content_type,
            )
            logger.info(
                f"File stream '{object_name}' uploaded to bucket '{bucket_name}'."
            )
            return True
        except S3Error as e:
            logger.error(f"Failed to upload file stream '{object_name}': {e}")
            return False

    async def download_file(
        self, bucket_name: str, object_name: str, file_path: str
    ) -> bool:
        """
        Downloads an object from a bucket to a local file.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            await asyncio.to_thread(
                self.client.fget_object, bucket_name, object_name, file_path
            )
            logger.info(
                f"Object '{object_name}' downloaded from bucket '{bucket_name}' to '{file_path}'."
            )
            return True
        except S3Error as e:
            logger.error(f"Failed to download object '{object_name}': {e}")
            return False

    async def delete_object(self, bucket_name: str, object_name: str) -> bool:
        """
        Deletes an object from a bucket.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            await asyncio.to_thread(self.client.remove_object, bucket_name, object_name)
            logger.info(f"Object '{object_name}' deleted from bucket '{bucket_name}'.")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete object '{object_name}': {e}")
            return False

    async def delete_objects(
        self, bucket_name: str, object_names: List[str]
    ) -> tuple[int, list[str]]:
        """
        Deletes multiple objects from a bucket.
        Returns the number of successfully deleted objects and a list of errors.
        """
        if not self._check_client():
            return 0, ["S3 client not initialized"]
        assert self.client is not None

        from minio.deleteobjects import DeleteObject

        delete_object_list = [DeleteObject(name) for name in object_names]
        try:
            errors_iterator = await asyncio.to_thread(
                self.client.remove_objects, bucket_name, delete_object_list
            )
            errors = []
            for error in errors_iterator:
                errors.append(f"Error deleting object {error.name}: {error}")

            deleted_count = len(object_names) - len(errors)
            if errors:
                logger.error(
                    f"Failed to delete some objects from bucket '{bucket_name}': {errors}"
                )
            else:
                logger.info(
                    f"Successfully deleted {deleted_count} objects from bucket '{bucket_name}'."
                )
            return deleted_count, errors
        except S3Error as e:
            logger.error(f"An S3 error occurred during bulk deletion: {e}")
            return 0, [str(e)]

    async def get_download_url(
        self, bucket_name: str, object_name: str, expires_in_seconds: int = 3600
    ) -> Optional[str]:
        """
        Generates a presigned download URL for an object.
        """
        if not self._check_client():
            return None
        assert self.client is not None
        try:
            url = await asyncio.to_thread(
                self.client.get_presigned_url,
                "GET",
                bucket_name,
                object_name,
                expires=timedelta(seconds=expires_in_seconds),
                response_headers=_download_response_headers(object_name),
            )
            logger.info(
                f"Successfully generated download URL for object '{object_name}'."
            )
            return url
        except S3Error as e:
            logger.error(
                f"Failed to generate download URL for object '{object_name}': {e}"
            )
            return None

    async def list_objects(
        self, bucket_name: str, prefix: Optional[str] = None, recursive: bool = False
    ) -> Optional[List[Dict]]:
        """
        Lists objects (files and folders) in a bucket.
        """
        if not self._check_client():
            return None
        assert self.client is not None
        try:
            objects = await asyncio.to_thread(
                self.client.list_objects,
                bucket_name,
                prefix=prefix,
                recursive=recursive,
            )
            object_list = []
            for obj in objects:
                object_list.append(
                    {
                        "name": obj.object_name,
                        "is_dir": obj.is_dir,
                        "size": obj.size,
                        "last_modified": obj.last_modified,
                    }
                )
            return object_list
        except S3Error as e:
            logger.error(f"Failed to list objects: {e}")
            return None

    async def remove_bucket(self, bucket_name: str) -> bool:
        """
        Removes an empty bucket.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            await asyncio.to_thread(self.client.remove_bucket, bucket_name)
            logger.info(f"Bucket '{bucket_name}' removed successfully.")
            return True
        except S3Error as e:
            logger.error(f"Failed to remove bucket '{bucket_name}': {e}")
            return False

    def _mc_target(self) -> str:
        return "hyac-rustfs"

    def _mc_endpoint_url(self) -> str:
        endpoint = settings.object_storage_internal_endpoint
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        scheme = "https" if settings.S3_SECURE_INTERNAL else "http"
        return f"{scheme}://{endpoint}"

    async def _run_mc(self, *args: str) -> tuple[bool, str]:
        command = ["mc", *args]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        except FileNotFoundError:
            return False, "The 'mc' command was not found in PATH."

        output = "\n".join(
            part.decode("utf-8", errors="replace").strip()
            for part in (stdout, stderr)
            if part
        ).strip()
        return process.returncode == 0, output

    async def _ensure_mc_alias(self) -> tuple[bool, str]:
        access_key = settings.object_storage_access_key
        secret_key = settings.object_storage_secret_key
        if not access_key or not secret_key:
            return False, "S3 admin credentials are not configured."

        return await self._run_mc(
            "alias",
            "set",
            self._mc_target(),
            self._mc_endpoint_url(),
            access_key,
            secret_key,
        )

    async def ensure_user(self, access_key: str, secret_key: str) -> tuple[bool, str]:
        """
        Ensures an object-storage user exists.

        This uses the MinIO-compatible `mc admin` workflow supported by RustFS-like
        deployments. Callers should treat failure as a provisioning failure rather
        than falling back to root credentials.
        """
        ok, output = await self._ensure_mc_alias()
        if not ok:
            return False, output

        ok, output = await self._run_mc(
            "admin", "user", "info", self._mc_target(), access_key
        )
        if ok:
            return True, output

        ok, output = await self._run_mc(
            "admin", "user", "add", self._mc_target(), access_key, secret_key
        )
        return ok, output

    async def remove_user(self, access_key: str) -> tuple[bool, str]:
        """Removes an object-storage user if it exists."""
        ok, output = await self._ensure_mc_alias()
        if not ok:
            return False, output

        ok, info_output = await self._run_mc(
            "admin", "user", "info", self._mc_target(), access_key
        )
        if not ok:
            normalized_output = info_output.casefold()
            explicitly_missing = any(
                marker in normalized_output
                for marker in (
                    "specified user does not exist",
                    "user does not exist",
                    "user not found",
                    "no such user",
                )
            )
            if explicitly_missing:
                return True, info_output
            return False, info_output

        return await self._run_mc(
            "admin", "user", "remove", self._mc_target(), access_key
        )

    async def attach_bucket_policy_to_user(
        self, access_key: str, policy_name: str, bucket_names: list[str]
    ) -> tuple[bool, str]:
        """Ensures a least-privilege bucket policy exists and attaches it."""
        ok, output = await self._ensure_mc_alias()
        if not ok:
            return False, output

        bucket_resources = [f"arn:aws:s3:::{name}" for name in bucket_names]
        object_resources = [f"arn:aws:s3:::{name}/*" for name in bucket_names]
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
                    "Resource": bucket_resources,
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:AbortMultipartUpload",
                        "s3:ListMultipartUploadParts",
                    ],
                    "Resource": object_resources,
                },
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w+", delete=False, suffix=".json", encoding="utf-8"
        ) as tmp:
            json.dump(policy, tmp, indent=2)
            tmp_policy_path = tmp.name

        try:
            ok, output = await self._run_mc(
                "admin",
                "policy",
                "create",
                self._mc_target(),
                policy_name,
                tmp_policy_path,
            )
            if not ok:
                policy_exists, info_output = await self._run_mc(
                    "admin",
                    "policy",
                    "info",
                    self._mc_target(),
                    policy_name,
                )
                if policy_exists:
                    ok, output = True, info_output
            if not ok:
                return False, output

            ok, output = await self._run_mc(
                "admin",
                "policy",
                "attach",
                self._mc_target(),
                policy_name,
                "--user",
                access_key,
            )
            return ok, output
        finally:
            os.unlink(tmp_policy_path)


s3_manager = S3Manager()
