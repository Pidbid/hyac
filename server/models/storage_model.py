from datetime import datetime
from enum import Enum
from typing import Optional

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class StorageStatus(str, Enum):
    """Provisioning state for app storage resources."""

    CREATING = "creating"
    READY = "ready"
    DELETING = "deleting"
    ERROR = "error"


class StorageBucketPolicy(str, Enum):
    """Supported bucket exposure policies."""

    PRIVATE = "private"
    PUBLIC_READ = "public_read"


class ApplicationStorage(Document):
    """Per-application object storage identity."""

    app_id: str = Field(..., min_length=2)
    access_key: str = Field(..., min_length=2)
    secret_key: str = Field(..., min_length=16)
    status: StorageStatus = Field(default=StorageStatus.CREATING)
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "application_storage"
        indexes = [IndexModel("app_id", unique=True)]

    def mark_ready(self):
        self.status = StorageStatus.READY
        self.last_error = None
        self.updated_at = datetime.now()

    def mark_error(self, error: str):
        self.status = StorageStatus.ERROR
        self.last_error = error
        self.updated_at = datetime.now()


class StorageBucket(Document):
    """Bucket metadata owned by an application."""

    app_id: str = Field(..., min_length=2)
    bucket_name: str = Field(..., min_length=2)
    display_name: str = Field(..., min_length=1)
    policy: StorageBucketPolicy = Field(default=StorageBucketPolicy.PRIVATE)
    is_default: bool = False
    status: StorageStatus = Field(default=StorageStatus.CREATING)
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "storage_buckets"
        indexes = [
            IndexModel([("app_id", 1), ("bucket_name", 1)], unique=True),
            IndexModel([("app_id", 1), ("is_default", 1)]),
        ]

    def mark_ready(self):
        self.status = StorageStatus.READY
        self.last_error = None
        self.updated_at = datetime.now()

    def mark_error(self, error: str):
        self.status = StorageStatus.ERROR
        self.last_error = error
        self.updated_at = datetime.now()
