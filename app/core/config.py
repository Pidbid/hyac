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

    class Config:
        """
        Pydantic model configuration.
        """

        env_file = None
        case_sensitive = True


settings = Settings()
