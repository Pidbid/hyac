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
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_KEY: Optional[str] = None
    DEFAULT_ADMIN_USER: Optional[str] = "admin"
    DEFAULT_ADMIN_PASSWORD: Optional[str] = "admin123"
    DEV_MODE: Optional[bool] = False
    DEMO_MODE: Optional[bool] = False
    TZ: Optional[str] = "Asia/Shanghai"
    APP_CODE_PATH_ON_HOST: Optional[str] = None  # only used in dev mode
    SERVER_IMAGE_TAG: Optional[str] = "latest"
    WEB_IMAGE_TAG: Optional[str] = "latest"
    APP_IMAGE_TAG: Optional[str] = "latest"

    class Config:
        """
        Pydantic model configuration.
        """

        # env_file = "../.env"
        env_file = None
        case_sensitive = True


settings = Settings()
