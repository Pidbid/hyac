# core/database.py
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from core.config import settings
from models import (
    Application,
    SettingModel,
    FunctionsHistory,
    Function,
    LogEntry,
    Captcha,
    User,
    FunctionMetric,
    FunctionTemplate,
    Task,
    ScheduledTask,
)


class MongoDBManager:
    """
    Manages the MongoDB connection and Beanie ODM initialization.
    """

    def __init__(self):
        """
        Initializes the MongoDB client and database instance.
        """
        self.client = AsyncIOMotorClient(
            "mongodb",
            27017,
            username=settings.MONGODB_USERNAME,
            password=settings.MONGODB_PASSWORD,
            replicaSet="rs0",
        )
        self.db = self.client.get_database("hyac")

    async def init_beanie(self):
        """
        Initializes the Beanie ODM with all the document models.
        """
        await init_beanie(
            database=self.db,
            document_models=[
                Application,
                Captcha,
                Function,
                FunctionsHistory,
                LogEntry,
                User,
                FunctionMetric,
                FunctionTemplate,
                SettingModel,
                Task,
                ScheduledTask,
            ],
        )


mongodb_manager = MongoDBManager()
