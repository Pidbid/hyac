# models/statistics_model.py
from datetime import datetime
from enum import Enum
from beanie import Document
from pydantic import Field, BaseModel
from typing import Optional, List, Any


class CallStatus(str, Enum):
    """Enum for the status of a function call."""

    SUCCESS = "success"
    ERROR = "error"
    UNKNOWN = "unknown"


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
    unknown: int


class FunctionRankingItem(BaseModel):
    function_name: str
    count: int
    average_execution_time: Optional[float] = None
    function_id: Optional[str] = None


class FunctionStats(BaseModel):
    count: int
    requests: RequestStats
    overall_average_execution_time: float
    ranking_by_count: List[FunctionRankingItem]
    ranking_by_time: List[FunctionRankingItem]


class CollectionStats(BaseModel):
    name: str
    count: int


class DatabaseStats(BaseModel):
    count: int
    collections: List[CollectionStats]


class StorageStats(BaseModel):
    total_usage_mb: float


class InsightItem(BaseModel):
    type: str  # e.g., 'info', 'warning'
    message_key: str  # e.g., 'insights.highErrorRate'
    metadata: Optional[dict[str, Any]] = None


class StatisticsSummary(BaseModel):
    functions: FunctionStats
    database: DatabaseStats
    storage: StorageStats
