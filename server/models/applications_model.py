# models/applications_model.py
from datetime import datetime
from typing import Optional, List
from enum import Enum

from beanie import Document
from pydantic import Field, BaseModel, model_validator
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


class Application(Document):
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
    environment_revision: int = Field(
        default=0,
        ge=0,
        description="Monotonic revision for atomic environment updates.",
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
    runtime_token_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 digest of the current application runtime credential.",
    )
    runtime_generation: int = Field(
        default=0,
        description="Incremented whenever the application runtime is recreated.",
    )
    pending_traefik_cleanup_generation: Optional[int] = Field(
        default=None,
        description=(
            "Runtime generation whose Traefik config deletion remains retryable."
        ),
    )
    runtime_cleanup_task_id: Optional[str] = Field(
        default=None,
        description="Internal task holding destructive runtime cleanup authority.",
    )
    runtime_cleanup_lease_owner: Optional[str] = Field(
        default=None,
        description="Internal worker claim paired with runtime cleanup authority.",
    )
    runtime_cleanup_lease_expires_at: Optional[datetime] = Field(
        default=None,
        description="Expiry for reclaimable runtime cleanup/adoption authority.",
    )
    lifecycle_revision: int = Field(
        default=0,
        ge=0,
        description="Monotonic fence incremented for every lifecycle transition.",
    )
    lifecycle_completed_task_id: Optional[str] = Field(
        default=None,
        description="Task whose lifecycle result was most recently published.",
    )
    runtime_memory_mb: int = Field(default=512, ge=128, le=4096)
    runtime_cpus: float = Field(default=1.0, ge=0.1, le=8.0)
    runtime_pids_limit: int = Field(default=128, ge=32, le=1024)
    cors_revision: int = Field(default=0, ge=0)
    cors: CORSConfig = Field(default_factory=CORSConfig, description="cors config")
    notification_revision: int = Field(default=0, ge=0)
    notification: NotificationConfig = Field(
        default_factory=NotificationConfig, description="notification config"
    )
    ai_config_revision: int = Field(default=0, ge=0)
    ai_config: AIConfig = Field(
        default_factory=AIConfig, description="AI service config"
    )
    status: ApplicationStatus = Field(
        default=ApplicationStatus.STOPPED,
        description="Status of the application (e.g., running, stopped).",
    )

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
