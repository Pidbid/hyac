# core/database.py
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from core.config import settings
from models.applications_model import Application
from models.functions_model import Function
from models.statistics_model import FunctionMetric
from models.logger_model import LogEntry


class MongoDBManager:
    """
    Manages the MongoDB connection and Beanie ODM initialization for the executor.
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
        Initializes the Beanie ODM with the document models required by the executor.
        """
        await init_beanie(
            database=self.db,
            document_models=[Application, Function, FunctionMetric, LogEntry],
        )
