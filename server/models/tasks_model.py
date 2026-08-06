import uuid
from enum import Enum
from typing import Optional, Dict, Any
from beanie import Document
from pydantic import Field
from datetime import datetime
from pymongo import IndexModel


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TaskAction(str, Enum):
    START_APP = "start_app"
    STOP_APP = "stop_app"
    RESTART_APP = "restart_app"
    DELETE_APP = "delete_app"


class Task(Document):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True)
    app_id: Optional[str] = None
    action: TaskAction
    status: TaskStatus = TaskStatus.PENDING
    payload: Dict[str, Any] = Field(default_factory=dict)  # 存储任务所需参数，如 app_id
    result: Optional[Dict[str, Any]] = None  # 存储任务执行结果或错误信息
    attempts: int = 0
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    next_attempt_at: Optional[datetime] = None
    last_error: Optional[str] = None
    published_at: Optional[datetime] = None
    published_status: Optional[str] = None
    published_lifecycle_revision: Optional[int] = None
    published_runtime_generation: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "tasks"  # MongoDB collection name
        indexes = [
            IndexModel("task_id", unique=True),
            IndexModel([("status", 1), ("next_attempt_at", 1), ("created_at", 1)]),
            IndexModel([("app_id", 1), ("status", 1)]),
        ]

    def update_timestamp(self):
        self.updated_at = datetime.now()
