# core/minio_manager.py
import asyncio
import io
import json
import subprocess
import tempfile
from datetime import timedelta
from typing import Dict, List, Optional

from loguru import logger
from minio import Minio
from minio.error import S3Error

from core.config import settings


class MinioManager:
    """
    Manages interactions with a Minio server, including bucket and object operations.
    """

    def __init__(self):
        """
        Initializes the Minio client using settings from the application configuration.
        """
        self.client = None
        if not all(
            [
                settings.MINIO_ACCESS_KEY,
                settings.MINIO_SECRET_KEY,
            ]
        ):
            logger.warning("MinIO configuration is incomplete; client not initialized.")
            return

        try:
            assert settings.MINIO_ACCESS_KEY is not None
            assert settings.MINIO_SECRET_KEY is not None
            self.client = Minio(
                endpoint="minio:9000",
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=False,
            )
            logger.info("MinIO client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            self.client = None

    def _check_client(self) -> bool:
        """
        Checks if the Minio client is initialized.
        """
        if not self.client:
            logger.error(
                "MinIO client is not initialized. Cannot perform MinIO operations."
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
            logger.error("MinIO client is not initialized. Cannot set bucket policy.")
            return
        assert self.client is not None
        await asyncio.to_thread(self.client.set_bucket_policy, bucket_name, policy)

    async def set_bucket_to_public_read(self, bucket_name: str):
        """
        Sets a bucket's policy to allow public read access for all objects.
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

    async def add_user(self, access_key: str, secret_key: str) -> bool:
        """
        Adds a new MinIO user using the 'mc' client.
        """
        if not self._check_client():
            return False

        mc_alias = "myminio"
        command = [
            "mc",
            "admin",
            "user",
            "add",
            mc_alias,
            access_key,
            secret_key,
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(
                    f"User '{access_key}' created successfully: {stdout.decode()}"
                )
                return True
            else:
                logger.error(f"Failed to create user '{access_key}': {stderr.decode()}")
                return False
        except FileNotFoundError:
            logger.error(
                "The 'mc' command was not found. Ensure the MinIO Client is installed and in the system's PATH."
            )
            return False

    async def set_user_policy_for_bucket(
        self, policy_name: str, bucket_name: str, permission: str, access_key: str
    ) -> bool:
        """
        Sets a policy for a user on a specific bucket.
        """
        if not self._check_client():
            return False

        if permission == "readonly":
            actions = ["s3:GetObject"]
        elif permission == "readwrite":
            actions = [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket",
            ]
        else:
            logger.error(f"Invalid permission type: {permission}")
            return False

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": actions,
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                }
            ],
        }

        mc_alias = "myminio"

        with tempfile.NamedTemporaryFile(
            mode="w+", delete=False, suffix=".json", encoding="utf-8"
        ) as tmp:
            json.dump(policy, tmp, indent=4)
            tmp_policy_path = tmp.name

        try:
            create_policy_command = [
                "mc",
                "admin",
                "policy",
                "add",
                mc_alias,
                policy_name,
                tmp_policy_path,
            ]
            process = await asyncio.create_subprocess_exec(*create_policy_command)
            await process.wait()
            if process.returncode != 0:
                raise Exception(f"Failed to create policy '{policy_name}'.")

            logger.info(f"Policy '{policy_name}' created or updated successfully.")

            attach_policy_command = [
                "mc",
                "admin",
                "policy",
                "attach",
                mc_alias,
                policy_name,
                "--user",
                access_key,
            ]
            process = await asyncio.create_subprocess_exec(*attach_policy_command)
            await process.wait()
            if process.returncode != 0:
                raise Exception(f"Failed to attach policy to user '{access_key}'.")

            logger.info(
                f"Policy '{policy_name}' successfully attached to user '{access_key}'."
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set policy: {e}")
            cleanup_command = ["mc", "admin", "policy", "remove", mc_alias, policy_name]
            await asyncio.create_subprocess_exec(*cleanup_command)
            logger.info(f"Attempted to clean up policy '{policy_name}'.")
            return False
        finally:
            import os

            os.unlink(tmp_policy_path)


minio_manager = MinioManager()
