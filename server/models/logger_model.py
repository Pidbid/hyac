# models/logger_model.py
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from beanie import Document
from pydantic import Field


class LogLevel(str, Enum):
    """
    Enum for log levels.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogType(str, Enum):
    """
    Enum for log type
    """

    FUNCTION = "function"
    SYSTEM = "system"


class LogEntry(Document):
    """
    Represents a log entry in the database.
    """

    level: LogLevel
    logtype: LogType
    timestamp: datetime = Field(default_factory=datetime.now)
    message: str
    module: Optional[str]
    function: Optional[str]
    app_id: Optional[str] = None
    function_id: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    exception: Optional[str]

    class Settings:
        """
        Pydantic and Beanie settings for the LogEntry model.
        """

        name = "logs"
        indexes = ["timestamp", "level", "module", "app_id", "function_id"]
