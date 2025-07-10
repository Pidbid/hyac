# core/logger.py
import sys

from loguru import logger

from core.config import settings
from models.logger_model import LogEntry, LogLevel, LogType


async def mongodb_log_sink(message):
    """
    A Loguru sink that asynchronously writes log records to MongoDB.
    """
    record = message.record
    level_name = record["level"].name
    log_level = LogLevel.INFO if level_name == "SUCCESS" else LogLevel[level_name]
    log_type = (
        record["extra"].get("logtype")
        if record["extra"].get("logtype")
        else LogType.SYSTEM
    )

    log_entry = LogEntry(
        level=log_level,
        logtype=log_type,
        message=record["message"],
        module=record["module"],
        function=record["function"],
        app_id=record["extra"].get("app_id"),
        function_id=record["extra"].get("function_id"),
        extra=record["extra"],
        exception=record["exception"] if record["exception"] else None,
    )
    await log_entry.insert()


def configure_logging():
    """
    Configures the Loguru logger with console and MongoDB sinks.
    """
    # Remove the default handler to avoid duplicate logs.
    logger.remove()

    # Configure the console sink with a colored format.
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG" if settings.DEBUG else "INFO",
    )

    # Configure the MongoDB sink for structured logging.
    logger.add(
        mongodb_log_sink,
        format="{message}",
        level="INFO",
        enqueue=True,  # Enable asynchronous logging queue.
    )
