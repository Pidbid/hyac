# core/database.py
from beanie import init_beanie
from pymongo import AsyncMongoClient

from core.config import settings
from models import (
    Application,
    SettingModel,
    FunctionsHistory,
    Function,
    Captcha,
    User,
    FunctionMetric,
    FunctionTemplate,
    Task,
    ScheduledTask,
    ApplicationStorage,
    StorageBucket,
)


class MongoDBManager:
    """
    Manages the MongoDB connection and Beanie ODM initialization.
    """

    def __init__(self):
        """
        Initializes the MongoDB client and database instance.
        """
        self.client = AsyncMongoClient(
            "mongodb",
            27017,
            username=settings.MONGODB_USERNAME,
            password=settings.MONGODB_PASSWORD,
            replicaSet="rs0",
        )
        self.db = self.client.get_database("hyac")

    def get_collection(self, document_model):
        """
        Returns the async PyMongo collection for a Beanie document model.
        """
        return self.db[document_model.get_settings().name]

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
                User,
                FunctionMetric,
                FunctionTemplate,
                SettingModel,
                Task,
                ScheduledTask,
                ApplicationStorage,
                StorageBucket,
            ],
        )

    async def close(self):
        """
        Closes the MongoDB client.
        """
        await self.client.close()


mongodb_manager = MongoDBManager()
