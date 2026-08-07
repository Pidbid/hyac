# core/s3_external.py
import asyncio
from datetime import timedelta
from typing import Optional
from urllib.parse import quote

from loguru import logger
from minio import Minio

from core.config import settings


def _download_response_headers(object_name: str) -> dict[str, str]:
    """Returns response headers that ask browsers to download the object."""
    filename = object_name.rsplit("/", 1)[-1] or "download"
    return {
        "response-content-disposition": (
            f"attachment; filename*=UTF-8''{quote(filename)}"
        )
    }


class S3ExternalManager:
    """
    Manages interactions with an S3-compatible object storage server for external-facing operations,
    specifically for generating presigned URLs with a public endpoint.
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
            logger.warning(
                "S3 configuration is incomplete; external client not initialized."
            )
            return

        try:
            assert settings.object_storage_access_key is not None
            assert settings.object_storage_secret_key is not None
            self.client = Minio(
                endpoint=settings.object_storage_external_endpoint,
                access_key=settings.object_storage_access_key,
                secret_key=settings.object_storage_secret_key,
                secure=bool(settings.S3_SECURE_EXTERNAL),
                region=settings.S3_REGION,
            )
            logger.info("External S3-compatible object storage client initialized successfully.")
        except Exception as e:
            logger.error(
                f"Failed to initialize external S3-compatible object storage client: {e}", exc_info=True
            )
            self.client = None

    async def get_download_url(
        self, bucket_name: str, object_name: str, expires_in_seconds: int = 3600
    ) -> Optional[str]:
        """
        Generates a presigned download URL for an object.
        """
        if not self.client:
            logger.error("External S3 client is not initialized.")
            return None
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
                f"Successfully generated external download URL for object '{object_name}'."
            )
            return url
        except Exception as e:
            logger.error(
                f"Failed to generate external download URL for object '{object_name}': {e}",
                exc_info=True,
            )
            return None


s3_external_manager = S3ExternalManager()
