# core/minio_external.py
import asyncio
from datetime import timedelta
from typing import Optional

from loguru import logger
from minio import Minio
from minio.error import S3Error

from core.config import settings


class MinioExternalManager:
    """
    Manages interactions with a Minio server for external-facing operations,
    specifically for generating presigned URLs with a public endpoint.
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
            logger.warning(
                "MinIO configuration is incomplete; external client not initialized."
            )
            return

        try:
            assert settings.MINIO_ACCESS_KEY is not None
            assert settings.MINIO_SECRET_KEY is not None
            self.client = Minio(
                endpoint=f"oss.{settings.DOMAIN_NAME}",
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=True,
            )
            logger.info("External MinIO client initialized successfully.")
        except Exception as e:
            logger.error(
                f"Failed to initialize external MinIO client: {e}", exc_info=True
            )
            self.client = None

    async def get_download_url(
        self, bucket_name: str, object_name: str, expires_in_seconds: int = 3600
    ) -> Optional[str]:
        """
        Generates a presigned download URL for an object.
        """
        if not self.client:
            logger.error("External MinIO client is not initialized.")
            return None
        try:
            url = await asyncio.to_thread(
                self.client.get_presigned_url,
                "GET",
                bucket_name,
                object_name,
                expires=timedelta(seconds=expires_in_seconds),
            )
            logger.info(
                f"Successfully generated external download URL for object '{object_name}'."
            )
            return url
        except Exception as e:
            logger.error(
                f"Failed to generate external download URL for object '{object_name}': {e}",
                exc_info=True,
            )
            return None


minio_external_manager = MinioExternalManager()
