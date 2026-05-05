from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables for the app container.
    """

    APP_ID: Optional[str] = None
    MONGODB_USERNAME: Optional[str] = None
    MONGODB_PASSWORD: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_INTERNAL_ENDPOINT: Optional[str] = "minio:9000"
    S3_SECURE_INTERNAL: Optional[bool] = False
    S3_REGION: Optional[str] = "us-east-1"
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_KEY: Optional[str] = None
    SECRET_KEY: Optional[str] = None
    DEV_MODE: Optional[bool] = False
    DEBUG: Optional[bool] = True
    LSP_MODE: str = "legacy"  # legacy | sidecar
    LSP_SIDECAR_URL: str = "ws://hyac_lsp_sidecar:9002/lsp"
    LSP_SIDECAR_TIMEOUT_SECONDS: int = 10
    LSP_SIDECAR_FALLBACK_LEGACY: bool = True

    class Config:
        """
        Pydantic model configuration.
        """

        env_file = None
        case_sensitive = True

    @property
    def object_storage_access_key(self) -> Optional[str]:
        """Returns the configured S3 access key, falling back to legacy MinIO vars."""
        return self.S3_ACCESS_KEY or self.MINIO_ACCESS_KEY

    @property
    def object_storage_secret_key(self) -> Optional[str]:
        """Returns the configured S3 secret key, falling back to legacy MinIO vars."""
        return self.S3_SECRET_KEY or self.MINIO_SECRET_KEY

    @property
    def object_storage_internal_endpoint(self) -> str:
        """Returns the internal S3 endpoint used inside the Docker network."""
        return self.S3_INTERNAL_ENDPOINT or "minio:9000"


settings = Settings()
