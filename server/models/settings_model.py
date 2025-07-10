# models/logger_model.py
from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field


class SettingModel(Document):
    """
    Represents a setting in the database.
    """

    name: str = Field(..., description="Setting name")
    data: Any
    create_at: datetime = Field(default_factory=datetime.now)
    update_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        """
        Pydantic and Beanie settings for the LogEntry model.
        """

        name = "settings"
        indexes = ["name"]
