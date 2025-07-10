# core/minio_manager.py
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

    def create_bucket(self, bucket_name: str) -> bool:
        """
        Creates a new bucket if it does not already exist.

        Args:
            bucket_name: The name of the bucket to create.

        Returns:
            True if the bucket was created or already exists, False on error.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            found = self.client.bucket_exists(bucket_name)
            if not found:
                self.client.make_bucket(bucket_name)
                logger.info(f"Bucket '{bucket_name}' created.")
                return True
            else:
                logger.info(f"Bucket '{bucket_name}' already exists.")
                return True
        except S3Error as e:
            logger.error(f"Failed to create bucket '{bucket_name}': {e}")
            return False

    def create_folder(self, bucket_name: str, folder_name: str) -> bool:
        """
        Creates a folder in a bucket by creating an empty object with a trailing slash.

        Args:
            bucket_name: The name of the bucket.
            folder_name: The name of the folder (e.g., 'my-folder/').

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        if not folder_name.endswith("/"):
            folder_name += "/"
        try:
            self.client.put_object(
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

    def delete_folder(self, bucket_name: str, folder_name: str) -> bool:
        """
        Deletes a folder and all its contents from a bucket.

        Args:
            bucket_name: The name of the bucket.
            folder_name: The name of the folder.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        if not folder_name.endswith("/"):
            folder_name += "/"
        try:
            objects_to_delete = self.client.list_objects(
                bucket_name, prefix=folder_name, recursive=True
            )
            for obj in objects_to_delete:
                if obj.object_name:
                    self.client.remove_object(bucket_name, obj.object_name)
            logger.info(
                f"Folder '{folder_name}' and its contents deleted from bucket '{bucket_name}'."
            )
            return True
        except S3Error as e:
            logger.error(f"Failed to delete folder '{folder_name}': {e}")
            return False

    def upload_file(self, bucket_name: str, object_name: str, file_path: str) -> bool:
        """
        Uploads a local file to a bucket.

        Args:
            bucket_name: The name of the bucket.
            object_name: The destination object name in the bucket.
            file_path: The path to the local file.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            self.client.fput_object(bucket_name, object_name, file_path)
            logger.info(
                f"File '{file_path}' uploaded as '{object_name}' to bucket '{bucket_name}'."
            )
            return True
        except S3Error as e:
            logger.error(f"Failed to upload file '{file_path}': {e}")
            return False

    def download_file(self, bucket_name: str, object_name: str, file_path: str) -> bool:
        """
        Downloads an object from a bucket to a local file.

        Args:
            bucket_name: The name of the bucket.
            object_name: The name of the object in the bucket.
            file_path: The local path to save the downloaded file.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            self.client.fget_object(bucket_name, object_name, file_path)
            logger.info(
                f"Object '{object_name}' downloaded from bucket '{bucket_name}' to '{file_path}'."
            )
            return True
        except S3Error as e:
            logger.error(f"Failed to download object '{object_name}': {e}")
            return False

    def delete_object(self, bucket_name: str, object_name: str) -> bool:
        """
        Deletes an object from a bucket.

        Args:
            bucket_name: The name of the bucket.
            object_name: The name of the object to delete.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False
        assert self.client is not None
        try:
            self.client.remove_object(bucket_name, object_name)
            logger.info(f"Object '{object_name}' deleted from bucket '{bucket_name}'.")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete object '{object_name}': {e}")
            return False

    def get_download_url(
        self, bucket_name: str, object_name: str, expires_in_seconds: int = 3600
    ) -> Optional[str]:
        """
        Generates a presigned download URL for an object.

        Args:
            bucket_name: The name of the bucket.
            object_name: The name of the object.
            expires_in_seconds: The URL's validity period in seconds.

        Returns:
            The presigned URL, or None on error.
        """
        if not self._check_client():
            return None
        assert self.client is not None
        try:
            url = self.client.get_presigned_url(
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

    def list_objects(
        self, bucket_name: str, prefix: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        Lists objects (files and folders) in a bucket.

        Args:
            bucket_name: The name of the bucket.
            prefix: An optional prefix to filter objects (e.g., for listing folder contents).

        Returns:
            A list of object dictionaries, or None on error.
        """
        if not self._check_client():
            return None
        assert self.client is not None
        try:
            objects = self.client.list_objects(
                bucket_name, prefix=prefix, recursive=False
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

    def add_user(self, access_key: str, secret_key: str) -> bool:
        """
        Adds a new MinIO user using the 'mc' client.
        Requires the MinIO Client (mc) to be installed and configured.

        Args:
            access_key: The access key for the new user.
            secret_key: The secret key for the new user.

        Returns:
            True if successful, False otherwise.
        """
        if not self._check_client():
            return False

        # Note: 'myminio' is an alias configured in the mc client.
        # This should be read from config in a production environment.
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
            result = subprocess.run(
                command, capture_output=True, text=True, check=True, encoding="utf-8"
            )
            logger.info(f"User '{access_key}' created successfully: {result.stdout}")
            return True
        except FileNotFoundError:
            logger.error(
                "The 'mc' command was not found. Ensure the MinIO Client is installed and in the system's PATH."
            )
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create user '{access_key}': {e.stderr}")
            return False

    def set_user_policy_for_bucket(
        self, policy_name: str, bucket_name: str, permission: str, access_key: str
    ) -> bool:
        """
        Sets a policy for a user on a specific bucket.

        Args:
            policy_name: A unique name for the policy.
            bucket_name: The name of the bucket.
            permission: The permission level ('readonly' or 'readwrite').
            access_key: The user's access key.

        Returns:
            True if successful, False otherwise.
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
            # 1. Create the policy
            create_policy_command = [
                "mc",
                "admin",
                "policy",
                "add",
                mc_alias,
                policy_name,
                tmp_policy_path,
            ]
            subprocess.run(
                create_policy_command,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )
            logger.info(f"Policy '{policy_name}' created or updated successfully.")

            # 2. Attach the policy to the user
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
            subprocess.run(
                attach_policy_command,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )
            logger.info(
                f"Policy '{policy_name}' successfully attached to user '{access_key}'."
            )

            return True
        except FileNotFoundError:
            logger.error("The 'mc' command was not found.")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set policy: {e.stderr}")
            # Attempt to clean up the created policy if attachment fails
            cleanup_command = ["mc", "admin", "policy", "remove", mc_alias, policy_name]
            subprocess.run(
                cleanup_command, capture_output=True, text=True, encoding="utf-8"
            )
            logger.info(f"Attempted to clean up policy '{policy_name}'.")
            return False
        finally:
            import os

            os.unlink(tmp_policy_path)


minio_manager = MinioManager()
