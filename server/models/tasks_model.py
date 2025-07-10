from enum import Enum
from typing import Optional, Dict, Any
from beanie import Document
from pydantic import Field
from datetime import datetime


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
    task_id: str = Field(..., unique=True)
    action: TaskAction
    status: TaskStatus = TaskStatus.PENDING
    payload: Dict[str, Any] = Field(default_factory=dict)  # 存储任务所需参数，如 app_id
    result: Optional[Dict[str, Any]] = None  # 存储任务执行结果或错误信息
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "tasks"  # MongoDB collection name

    def update_timestamp(self):
        self.updated_at = datetime.now()
