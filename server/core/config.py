import re
from pathlib import Path
from typing import List, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DOMAIN_LABEL_PATTERN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)
_EMAIL_LOCAL_PATTERN = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+")


def _is_valid_production_domain(value: str) -> bool:
    if len(value) > 253 or "." not in value:
        return False
    labels = value.split(".")
    if any(not _DOMAIN_LABEL_PATTERN.fullmatch(label) for label in labels):
        return False
    top_level_domain = labels[-1]
    return top_level_domain.isalpha() or top_level_domain.lower().startswith("xn--")


def _is_valid_acme_email(value: str) -> bool:
    if len(value) > 254 or value.count("@") != 1:
        return False
    local_part, domain = value.split("@")
    if (
        not local_part
        or len(local_part) > 64
        or local_part.startswith(".")
        or local_part.endswith(".")
        or ".." in local_part
        or not _EMAIL_LOCAL_PATTERN.fullmatch(local_part)
    ):
        return False
    return _is_valid_production_domain(domain)


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
    DEFAULT_ADMIN_USER: Optional[str] = None
    DEFAULT_ADMIN_PASSWORD: Optional[str] = None
    DEV_MODE: Optional[bool] = False
    CI_SMOKE_MODE: bool = False
    RUNTIME_INGRESS_ENTRYPOINT: str = "websecure"
    RUNTIME_INGRESS_TLS: bool = True
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

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.APP_CODE_PATH_ON_HOST:
            self.validate_dev_mount_path()

        if self.CI_SMOKE_MODE:
            if self.DEV_MODE:
                raise ValueError("CI_SMOKE_MODE requires DEV_MODE=false")
            if self.DOMAIN_NAME != "ci.example.com":
                raise ValueError(
                    "CI_SMOKE_MODE is restricted to the disposable ci.example.com domain"
                )
            if (
                self.RUNTIME_INGRESS_ENTRYPOINT != "ci"
                or not self.RUNTIME_INGRESS_TLS
            ):
                raise ValueError(
                    "CI_SMOKE_MODE requires the isolated ci TLS ingress"
                )
        elif (
            self.RUNTIME_INGRESS_ENTRYPOINT != "websecure"
            or not self.RUNTIME_INGRESS_TLS
        ):
            raise ValueError(
                "Plaintext runtime ingress is restricted to CI_SMOKE_MODE"
            )
        if self.DEV_MODE:
            return self
        required = {
            "DOMAIN_NAME": self.DOMAIN_NAME,
            "EMAIL_ADDRESS": self.EMAIL_ADDRESS,
            "MONGODB_USERNAME": self.MONGODB_USERNAME,
            "MONGODB_PASSWORD": self.MONGODB_PASSWORD,
            "S3_ACCESS_KEY": self.S3_ACCESS_KEY,
            "S3_SECRET_KEY": self.S3_SECRET_KEY,
            "SECRET_KEY": self.SECRET_KEY,
            "DEFAULT_ADMIN_USER": self.DEFAULT_ADMIN_USER,
            "DEFAULT_ADMIN_PASSWORD": self.DEFAULT_ADMIN_PASSWORD,
            "APP_IMAGE_TAG": self.APP_IMAGE_TAG,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Missing required production settings: " + ", ".join(missing)
            )
        weak_values = {
            "hyacpassword",
            "rustfssecret",
            "admin123",
            "change-me",
            "changeme",
        }
        insecure = [
            key
            for key, value in required.items()
            if isinstance(value, str)
            and (value.lower() in weak_values or value.startswith("<"))
        ]
        if insecure:
            raise ValueError(
                "Insecure production settings are not allowed: "
                + ", ".join(insecure)
            )
        placeholders = []
        if self.DOMAIN_NAME and self.DOMAIN_NAME.lower() == "your-domain.com":
            placeholders.append("DOMAIN_NAME")
        if self.EMAIL_ADDRESS and self.EMAIL_ADDRESS.lower() == "xxxx@xxxx.com":
            placeholders.append("EMAIL_ADDRESS")
        if placeholders:
            raise ValueError(
                "Production placeholders are not allowed: "
                + ", ".join(placeholders)
            )
        if self.DOMAIN_NAME and not _is_valid_production_domain(self.DOMAIN_NAME):
            raise ValueError("DOMAIN_NAME must be a valid fully qualified DNS name")
        if self.EMAIL_ADDRESS and not _is_valid_acme_email(self.EMAIL_ADDRESS):
            raise ValueError("EMAIL_ADDRESS must be a valid email address")
        if self.SECRET_KEY and len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        if self.DEFAULT_ADMIN_PASSWORD and (
            not 8 <= len(self.DEFAULT_ADMIN_PASSWORD) <= 128
            or any(character.isspace() for character in self.DEFAULT_ADMIN_PASSWORD)
        ):
            raise ValueError(
                "DEFAULT_ADMIN_PASSWORD must contain 8-128 non-whitespace characters"
            )
        if self.MONGODB_PASSWORD and len(self.MONGODB_PASSWORD) < 12:
            raise ValueError("MONGODB_PASSWORD must contain at least 12 characters")
        if self.S3_SECRET_KEY and len(self.S3_SECRET_KEY) < 16:
            raise ValueError("S3_SECRET_KEY must contain at least 16 characters")
        if self.APP_IMAGE_TAG and self.APP_IMAGE_TAG.lower() == "latest":
            raise ValueError("APP_IMAGE_TAG must be an immutable non-latest tag")
        return self

    def validate_dev_mount_path(self) -> None:
        """Reject broad or ambiguous host mounts before passing them to Docker."""
        if not self.DEV_MODE:
            raise ValueError("APP_CODE_PATH_ON_HOST is only allowed in DEV_MODE")
        path = Path(self.APP_CODE_PATH_ON_HOST or "")
        if not path.is_absolute():
            raise ValueError("APP_CODE_PATH_ON_HOST must be an absolute path")
        path = path.resolve(strict=False)
        if path == Path(path.anchor):
            raise ValueError("APP_CODE_PATH_ON_HOST cannot mount a filesystem root")
        self.APP_CODE_PATH_ON_HOST = str(path)

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
