# app/context.py
import os
import asyncio
from typing import Any
from types import SimpleNamespace
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.database import Database
from pymongo import MongoClient


from code_loader import CodeLoader
from core.env_manager import set_dynamic_env
from core.notification_manager import NotificationManager
from models.applications_model import NotificationConfig


class EnvContext:
    """
    Provides an interface for FaaS functions to interact with environment variables.
    """

    def get(self, key: str, default: Any = None) -> Any:
        """
        Gets an environment variable.

        It retrieves variables from the current process's environment, which is kept
        up-to-date by a background Change Stream watcher.
        """
        return os.getenv(key, default)

    async def set(self, key: str, value: str):
        """
        Sets an environment variable, making it immediately available to the current process,
        updating the global cache, and persisting it to the database for future calls.

        This is an async function and must be awaited.
        """
        # Persist the change to the database and update the process environment.
        await set_dynamic_env(key, value)


class FunctionContext:
    """
    Context object provided to dynamically loaded functions.

    This class encapsulates resources that a function might need, such as a logger,
    request object, application/function identifiers, and database connections.
    """

    def __init__(
        self,
        app_id: str,
        func_id: str,
        pymongo_db: Database,
        motor_db: AsyncIOMotorDatabase,
        code_loader: CodeLoader,
        env: EnvContext,
        common: SimpleNamespace,
        notification_config: NotificationConfig,
    ):
        """
        Initializes the function context.

        Args:
            app_id: The ID of the application.
            func_id: The ID of the function.
            pymongo_db: The synchronous PyMongo database client.
            motor_db: The asynchronous Motor database client.
            code_loader: An instance of CodeLoader, kept for potential future use.
            env: An instance of EnvContext for environment variable management.
            common: A namespace object containing all pre-loaded common functions for the app.
            notification_config: The notification configuration for the application.
        """
        self.app_id = app_id
        self.func_id = func_id
        self.logger = logger  # Injects the global logger instance.
        self.pymongo_db = pymongo_db
        self.motor_db = motor_db
        self.code_loader = code_loader
        self.env = env
        self.common = common
        self.notification = NotificationManager(notification_config)

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """Provides convenient access to the asynchronous Motor database client."""
        return self.motor_db

    @property
    def sync_db(self) -> Database:
        """Provides convenient access to the synchronous PyMongo database client."""
        return self.pymongo_db
