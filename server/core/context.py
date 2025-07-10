# core/context.py
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.database import Database

from core.code_loader import CodeLoader


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
    ):
        """
        Initializes the function context.

        Args:
            app_id: The ID of the application.
            func_id: The ID of the function.
            pymongo_db: The synchronous PyMongo database client.
            motor_db: The asynchronous Motor database client.
            code_loader: An instance of CodeLoader for importing common functions.
        """
        self.app_id = app_id
        self.func_id = func_id
        self.logger = logger  # Injects the global logger instance.
        self.pymongo_db = pymongo_db
        self.motor_db = motor_db
        self.code_loader = code_loader

    async def import_common(self, function_id: str):
        """
        Dynamically imports a common function.

        Args:
            function_id: The ID of the common function to import.

        Returns:
            The handler of the imported common function.

        Raises:
            ImportError: If the common function cannot be found or loaded.
        """
        common_func = await self.code_loader.load_common_function(
            self.app_id, function_id
        )
        if not common_func:
            raise ImportError(
                f"Common function '{function_id}' not found in app '{self.app_id}'"
            )
        return common_func["handler"]

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """Provides convenient access to the asynchronous Motor database client."""
        return self.motor_db

    @property
    def sync_db(self) -> Database:
        """Provides convenient access to the synchronous PyMongo database client."""
        return self.pymongo_db
