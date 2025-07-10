# models/statistics_model.py
from datetime import datetime
from enum import Enum
from beanie import Document
from pydantic import Field, BaseModel
from typing import Optional, List


class CallStatus(str, Enum):
    """Enum for the status of a function call."""

    SUCCESS = "success"
    ERROR = "error"


class FunctionMetric(Document):
    """Represents a single call to a serverless function."""

    function_id: str = Field(...)
    function_name: str = Field(...)
    app_id: str = Field(...)
    status: CallStatus = Field(...)
    execution_time: float  # Execution time in seconds
    timestamp: datetime = Field(default_factory=datetime.now)
    extra: Optional[dict] = None

    class Settings:
        name = "function_metrics"
        indexes = ["function_id", "app_name", "timestamp"]


# --- New Models for Statistics Summary ---


class RequestStats(BaseModel):
    total: int
    success: int
    error: int


class FunctionRequestStats(BaseModel):
    function_name: str
    request_count: int


class FunctionStatsOther(BaseModel):
    last_24_hours: int
    request_sort: list[FunctionRequestStats]


class FunctionStats(BaseModel):
    count: int
    requests: RequestStats
    other: FunctionStatsOther


class CollectionStats(BaseModel):
    name: str
    count: int


class DatabaseStats(BaseModel):
    count: int
    collections: List[CollectionStats]


class StorageStats(BaseModel):
    total_usage_mb: float


class StatisticsSummary(BaseModel):
    functions: FunctionStats
    database: DatabaseStats
    storage: StorageStats
