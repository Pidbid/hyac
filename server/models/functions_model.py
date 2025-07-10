# models/functions_model.py
from datetime import datetime
from enum import Enum
from typing import Optional

from beanie import Document
from pydantic import Field, model_validator
from pymongo import IndexModel

from core.utils import generate_short_id


class FunctionStatus(str, Enum):
    """
    Enum for the status of a function.
    """

    UNPUBLISHED = "unpublished"
    PUBLISHED = "published"


class FunctionType(str, Enum):
    """
    Enum for the type of a function.
    """

    ENDPOINT = "endpoint"
    COMMON = "common"


class Function(Document):
    """
    Represents a serverless function in the system.
    """

    function_id: str = Field(default_factory=lambda: generate_short_id(8))
    function_name: str = Field(..., min_length=1)
    app_id: str = Field(..., min_length=2)
    tags: list[str] = Field(default_factory=list)
    code: str = Field(..., min_length=10)
    status: FunctionStatus = Field(default=FunctionStatus.UNPUBLISHED)
    function_type: FunctionType = Field(default=FunctionType.ENDPOINT)
    memory_limit: int = 128  # Memory limit in MB
    timeout: int = 5  # Timeout in seconds
    requires_auth: bool = True  # Whether authentication is required
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    users: list[str] = Field(default_factory=list)  # List of associated users
    description: Optional[str] = Field(default="", max_length=500)
    minio_bucket: Optional[str] = Field(
        default=None,
        description="Name of the MinIO bucket associated with the function.",
    )

    @model_validator(mode="after")
    def set_minio_bucket(self) -> "Function":
        """
        Automatically sets the MinIO bucket name based on the app_id.
        """
        if self.app_id:
            self.minio_bucket = self.app_id.lower()
        return self

    class Settings:
        """
        Pydantic and Beanie settings for the Function model.
        """

        name = "functions"
        use_cache = False
        indexes = ["function_id", "app_id"]

    def update_timestamp(self):
        """
        Updates the 'updated_at' timestamp to the current time.
        """
        self.updated_at = datetime.now()
