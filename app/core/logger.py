import sys
from enum import Enum

from loguru import logger

from core.config import settings


class LogType(str, Enum):
    FUNCTION = "function"
    SYSTEM = "system"


def prefix_runtime_lines(text: str, runtime_label: str) -> str:
    """Prefix each runtime log line so function-scoped filtering keeps multiline errors."""
    normalized = text.strip("\n")
    if not normalized or not runtime_label:
        return normalized

    return "\n".join(f"{runtime_label}{line}" for line in normalized.splitlines())


def configure_logging():
    """
    Configures the Loguru logger for runtime streaming.
    """
    # Remove the default handler to avoid duplicate logs.
    logger.remove()
    logger.configure(extra={"runtime_label": ""})

    # Configure the console sink with a colored format.
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{extra[runtime_label]}{message}</level>",
        level="DEBUG" if settings.DEBUG else "INFO",
        backtrace=True,
        diagnose=settings.DEBUG,
    )
