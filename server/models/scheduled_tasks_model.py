from beanie import Document
from pydantic import Field, BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid
from datetime import datetime


class TriggerType(str, Enum):
    CRON = "cron"
    INTERVAL = "interval"


class ScheduledTask(Document):
    """
    Represents a scheduled task in the database.
    """

    task_id: str = Field(
        default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}", unique=True
    )
    app_id: Optional[str] = Field(
        default=None,
        description="The ID of the application this task belongs to. Required for non-system tasks.",
        index=True,
    )
    function_id: Optional[str] = Field(
        default=None,
        description="The ID of the function to be executed. Required for non-system tasks.",
        index=True,
    )
    name: str = Field(..., max_length=100)
    trigger: TriggerType = Field(..., description="The type of trigger for the task.")
    trigger_config: Dict[str, Any] = Field(
        ...,
        description="Configuration for the trigger, e.g., {'minute': '*/5'} for cron",
    )

    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="The request query parameters to be passed to the function.",
    )
    body: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="The request body (event) to be passed to the function.",
    )

    enabled: bool = Field(
        default=True, description="Whether the task is currently enabled."
    )
    description: Optional[str] = Field(default=None, max_length=500)

    is_system_task: bool = Field(
        default=False,
        description="Indicates if the task is a system-level task that runs internal functions.",
    )

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "scheduled_tasks"

    class Config:
        json_schema_extra = {
            "example": {
                "function_id": "func_12345678",
                "name": "Example Cron Job",
                "trigger": "cron",
                "trigger_config": {"minute": "*/1"},
                "params": {"query": "test"},
                "body": {"key": "value"},
                "enabled": True,
                "description": "This is an example cron job that runs every minute.",
            }
        }
