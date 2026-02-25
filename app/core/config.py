from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables for the app container.
    """

    APP_ID: Optional[str] = None
    MONGODB_USERNAME: Optional[str] = None
    MONGODB_PASSWORD: Optional[str] = None
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


settings = Settings()
