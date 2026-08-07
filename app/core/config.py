from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables for the app container.
    """

    APP_ID: Optional[str] = None
    APP_DB_USERNAME: Optional[str] = None
    APP_DB_PASSWORD: Optional[str] = None
    RUNTIME_TOKEN: Optional[str] = None
    RUNTIME_GENERATION: int = 0
    CONTROL_PLANE_URL: str = "http://hyac_server:8000/internal/runtime"
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_INTERNAL_ENDPOINT: Optional[str] = "rustfs:9000"
    S3_SECURE_INTERNAL: Optional[bool] = False
    S3_REGION: Optional[str] = "us-east-1"
    DEV_MODE: Optional[bool] = False
    DEBUG: Optional[bool] = True
    LSP_MODE: str = "legacy"  # legacy | sidecar
    LSP_SIDECAR_URL: str = "ws://hyac_lsp_sidecar:9002/lsp"
    LSP_SIDECAR_TIMEOUT_SECONDS: int = 10
    LSP_SIDECAR_FALLBACK_LEGACY: bool = True

    model_config = SettingsConfigDict(env_file=None, case_sensitive=True)

    @property
    def object_storage_access_key(self) -> Optional[str]:
        """Returns the configured S3 access key."""
        return self.S3_ACCESS_KEY

    @property
    def object_storage_secret_key(self) -> Optional[str]:
        """Returns the configured S3 secret key."""
        return self.S3_SECRET_KEY

    @property
    def object_storage_internal_endpoint(self) -> str:
        """Returns the internal S3 endpoint used inside the Docker network."""
        return self.S3_INTERNAL_ENDPOINT or "rustfs:9000"


settings = Settings()
