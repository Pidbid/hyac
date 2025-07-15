# models/applications_model.py
from datetime import datetime
from typing import Dict, Optional, List
from enum import Enum

from beanie import Document
from pydantic import Field, model_validator, BaseModel
from pymongo import IndexModel

from core.utils import generate_short_id


class Dependency(BaseModel):
    """Represents a single dependency."""

    name: str
    version: str


class EnvironmentVariable(BaseModel):
    """Represents a single environment variable."""

    key: str
    value: str


class CORSConfig(BaseModel):
    allow_origins: List[str] = Field(default_factory=list)
    allow_credentials: bool = True
    allow_methods: List[str] = Field(default_factory=list)
    allow_headers: List[str] = Field(default_factory=list)


class EmailNotification(BaseModel):
    enabled: bool = False
    smtpServer: str = ""
    port: int = 465
    username: str = ""
    password: str = ""
    fromAddress: str = ""


class WebhookNotification(BaseModel):
    enabled: bool = False
    url: str = ""
    method: str = "POST"
    template: str = ""


class WeChatNotification(BaseModel):
    enabled: bool = False
    notificationId: str = ""


class NotificationConfig(BaseModel):
    email: EmailNotification = Field(default_factory=EmailNotification)
    webhook: WebhookNotification = Field(default_factory=WebhookNotification)
    wechat: WeChatNotification = Field(default_factory=WeChatNotification)


class AIConfig(BaseModel):
    """Represents the AI configuration for an application."""

    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""


class ApplicationStatus(str, Enum):
    """
    Enum for the status of an application.
    """

    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    DELETING = "deleting"
    ERROR = "error"


class Application(Document):
    """
    Represents an application in the system.
    """

    app_id: str = Field(default_factory=lambda: generate_short_id(8))
    app_name: str = Field(default=..., min_length=2)
    description: Optional[str] = None
    common_dependencies: List[Dependency] = Field(
        default_factory=[],
        description="Common dependencies for the application.",
    )
    environment_variables: List[EnvironmentVariable] = Field(
        default_factory=[],
        description="Environment variables for the application.",
    )
    users: list[str] = Field(
        default_factory=list,
        description="List of users associated with the application.",
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    db_password: str = Field(
        description="Password for the database associated with the application."
    )
    minio_bucket: Optional[str] = Field(
        default=None,
        description="Name of the MinIO bucket associated with the application.",
    )
    cors: CORSConfig = Field(default_factory=CORSConfig, description="cors config")
    notification: NotificationConfig = Field(
        default_factory=NotificationConfig, description="notification config"
    )
    ai_config: AIConfig = Field(
        default_factory=AIConfig, description="AI service config"
    )
    status: ApplicationStatus = Field(
        default=ApplicationStatus.STOPPED,
        description="Status of the application (e.g., running, stopped).",
    )

    @model_validator(mode="after")
    def set_minio_bucket(self) -> "Application":
        """
        Automatically sets the MinIO bucket name based on the app_id.
        """
        if self.app_id:
            self.minio_bucket = self.app_id.lower()
        return self

    class Settings:
        """
        Pydantic and Beanie settings for the Application model.
        """

        name = "applications"
        indexes = [
            IndexModel("app_id", unique=True),
            IndexModel("app_name", unique=True),
        ]

    def update_timestamp(self):
        """
        Updates the 'updated_at' timestamp to the current time.
        """
        self.updated_at = datetime.now()
