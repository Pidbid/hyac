from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or a .env file.
    """

    DOMAIN_NAME: Optional[str] = None
    EMAIL_ADDRESS: Optional[str] = None
    MONGODB_USERNAME: Optional[str] = None
    MONGODB_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None
    DEBUG: Optional[bool] = None
    CODE_CACHE_EXPIRE: Optional[int] = None
    ALLOWED_DEPENDENCIES: Optional[List[str]] = Field(
        default_factory=list, description="List of allowed dynamic dependencies."
    )
    API_PREFIX: Optional[str] = None
    SECRET_KEY: Optional[str] = None  # JWT secret key
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_INTERNAL_ENDPOINT: Optional[str] = "rustfs:9000"
    S3_EXTERNAL_ENDPOINT: Optional[str] = None
    S3_SECURE_INTERNAL: Optional[bool] = False
    S3_SECURE_EXTERNAL: Optional[bool] = True
    S3_PUBLIC_BASE_URL: Optional[str] = None
    S3_REGION: Optional[str] = "us-east-1"
    DEFAULT_ADMIN_USER: Optional[str] = "admin"
    DEFAULT_ADMIN_PASSWORD: Optional[str] = "admin123"
    DEV_MODE: Optional[bool] = False
    DEMO_MODE: Optional[bool] = False
    TZ: Optional[str] = "Asia/Shanghai"
    APP_CODE_PATH_ON_HOST: Optional[str] = None  # only used in dev mode
    SERVER_IMAGE_TAG: Optional[str] = "latest"
    WEB_IMAGE_TAG: Optional[str] = "latest"
    APP_IMAGE_TAG: Optional[str] = "latest"
    LSP_MODE: Optional[str] = "legacy"
    LSP_SIDECAR_URL: Optional[str] = "ws://hyac_lsp_sidecar:9002/lsp"
    LSP_SIDECAR_TIMEOUT_SECONDS: Optional[int] = 10
    LSP_SIDECAR_FALLBACK_LEGACY: Optional[bool] = True

    class Config:
        """
        Pydantic model configuration.
        """

        # env_file = "../.env"
        env_file = None
        case_sensitive = True

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

    @property
    def object_storage_external_endpoint(self) -> str:
        """Returns the public S3 endpoint used for presigned URLs."""
        if self.S3_EXTERNAL_ENDPOINT:
            return self.S3_EXTERNAL_ENDPOINT
        if self.DOMAIN_NAME:
            return f"oss.{self.DOMAIN_NAME}"
        return "localhost:9000"

    @property
    def object_storage_internal_url(self) -> str:
        """Returns the internal S3 endpoint with an HTTP scheme for reverse proxies."""
        endpoint = self.object_storage_internal_endpoint
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        scheme = "https" if self.S3_SECURE_INTERNAL else "http"
        return f"{scheme}://{endpoint}"

    @property
    def object_storage_internal_host_header(self) -> str:
        """Returns the Host header value for internal S3 reverse proxy requests."""
        endpoint = self.object_storage_internal_endpoint
        return endpoint.removeprefix("http://").removeprefix("https://").rstrip("/")


settings = Settings()
