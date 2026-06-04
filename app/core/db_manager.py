# app/core/db_manager.py
from typing import Dict, Tuple
from pymongo import AsyncMongoClient, MongoClient
from pymongo.errors import ConnectionFailure
from loguru import logger

from models.applications_model import Application


class DBConnectionManager:
    """
    Manages database connections to avoid reconnecting for each function call.
    """

    def __init__(self):
        self._pymongo_clients: Dict[str, MongoClient] = {}
        self._async_clients: Dict[str, AsyncMongoClient] = {}

    async def get_clients(
        self, application: Application
    ) -> Tuple[MongoClient, AsyncMongoClient]:
        """
        Gets or creates database clients for a given application.
        """
        app_id = application.app_id
        if app_id in self._pymongo_clients and app_id in self._async_clients:
            return self._pymongo_clients[app_id], self._async_clients[app_id]

        if not application.db_password:
            raise Exception("Application or DB password not found")

        mongo_uri = f"mongodb://{application.app_id}:{application.db_password}@mongodb:27017/{application.app_id}?authSource=admin&replicaSet=rs0"

        try:
            logger.info(f"Connecting to MongoDB for app {app_id} with URI: {mongo_uri}")
            # Create PyMongo client
            pymongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            pymongo_client.admin.command("ping")
            self._pymongo_clients[app_id] = pymongo_client
            logger.info(f"Successfully connected to MongoDB (PyMongo) for app {app_id}")

            # Create async PyMongo client
            async_client = AsyncMongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            await async_client.admin.command("ping")
            self._async_clients[app_id] = async_client
            logger.info(
                f"Successfully connected to MongoDB (PyMongo Async) for app {app_id}"
            )

            return pymongo_client, async_client
        except ConnectionFailure as e:
            logger.error(f"Could not connect to MongoDB for app {app_id}: {e}")
            # Clean up any partially created clients
            if app_id in self._pymongo_clients:
                self._pymongo_clients[app_id].close()
                del self._pymongo_clients[app_id]
            if app_id in self._async_clients:
                await self._async_clients[app_id].close()
                del self._async_clients[app_id]
            raise Exception(f"Database connection failed for app {app_id}: {e}")

    async def close_all(self):
        """
        Closes all active database connections.
        """
        logger.info("Closing all MongoDB connections...")
        for client in self._pymongo_clients.values():
            client.close()
        for client in self._async_clients.values():
            await client.close()
        self._pymongo_clients.clear()
        self._async_clients.clear()
        logger.info("All MongoDB connections closed.")


# Global instance of the connection manager
db_manager = DBConnectionManager()
