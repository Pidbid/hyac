# models/applications_model.py
from datetime import datetime
from typing import Optional, List
from enum import Enum

from pydantic import Field, BaseModel, model_validator

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
    allow_credentials: bool = False
    allow_methods: List[str] = Field(default_factory=list)
    allow_headers: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_policy(self):
        if self.allow_credentials and "*" in self.allow_origins:
            raise ValueError("Wildcard CORS origins cannot allow credentials")
        return self


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
    proxy: str = ""


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


class Application(BaseModel):
    """
    Represents an application in the system.
    """

    app_id: str = Field(default_factory=lambda: generate_short_id(8))
    app_name: str = Field(default=..., min_length=2)
    description: Optional[str] = None
    common_dependencies: List[Dependency] = Field(
        default_factory=list,
        description="Common dependencies for the application.",
    )
    environment_variables: List[EnvironmentVariable] = Field(
        default_factory=list,
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
    runtime_token_hash: Optional[str] = None
    runtime_generation: int = 0
    runtime_memory_mb: int = 512
    runtime_cpus: float = 1.0
    runtime_pids_limit: int = 128
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

    def update_timestamp(self):
        """
        Updates the 'updated_at' timestamp to the current time.
        """
        self.updated_at = datetime.now()
