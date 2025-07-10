# core/database_dynamic.py
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from core.config import settings


class DynamicDB:
    def __init__(self) -> None:
        """
        Initializes the Dynamic_DB class with a MongoDB client.
        Connects to MongoDB using settings from core.config.
        """
        self.db_client = AsyncIOMotorClient(
            "mongodb",
            27017,
            username=settings.MONGODB_USERNAME,
            password=settings.MONGODB_PASSWORD,
        )

    def app_db(self, app_id: str):
        """
        Returns the database instance for a given application ID.

        Args:
            app_id (str): The ID of the application.

        Returns:
            motor.motor_asyncio.AsyncIOMotorDatabase: The database instance.
        """
        return self.db_client[app_id]

    async def app_insert_document(self, app_id: str, col_name: str, data: dict):
        """
        Inserts a single document into the specified collection.

        Args:
            app_id (str): The ID of the application (database name).
            col_name (str): The name of the collection.
            data (str): The document data to insert.

        Returns:
            pymongo.results.InsertOneResult: The result of the insert operation.
        """
        result = await self.db_client[app_id][col_name].insert_one(data)
        return result

    async def app_delete_one_document(self, app_id: str, col_name: str, filter: dict):
        """
        Deletes a single document from the specified collection based on a filter.

        Args:
            app_id (str): The ID of the application (database name).
            col_name (str): The name of the collection.
            filter (dict): The filter criteria to find the document.

        Returns:
            pymongo.results.DeleteResult: The result of the delete operation.
        """
        result = await self.db_client[app_id][col_name].delete_one(filter)
        return result

    async def app_delete_document_by_id(self, app_id: str, col_name: str, doc_id: str):
        """
        Deletes a single document from the specified collection by its ObjectId.

        Args:
            app_id (str): The ID of the application (database name).
            col_name (str): The name of the collection.
            doc_id (str): The string representation of the document's ObjectId.

        Returns:
            pymongo.results.DeleteResult: The result of the delete operation.
        """
        result = await self.db_client[app_id][col_name].delete_one(
            {"_id": ObjectId(doc_id)}
        )
        return result

    async def app_update_one_document(
        self, app_id: str, col_name: str, filter: dict, new_data: dict
    ):
        """
        Updates a single document in the specified collection based on a filter.

        Args:
            app_id (str): The ID of the application (database name).
            col_name (str): The name of the collection.
            filter (dict): The filter criteria to find the document.
            new_data (dict): The new data to set for the document.

        Returns:
            pymongo.results.UpdateResult: The result of the update operation.
        """
        result = await self.db_client[app_id][col_name].update_one(
            filter, {"$set": new_data}
        )
        return result

    async def app_update_document_by_id(
        self, app_id: str, col_name: str, doc_id: str, new_data: dict
    ):
        """
        Updates a single document in the specified collection by its ObjectId.

        Args:
            app_id (str): The ID of the application (database name).
            col_name (str): The name of the collection.
            doc_id (str): The string representation of the document's ObjectId.
            new_data (dict): The new data to set for the document.

        Returns:
            pymongo.results.UpdateResult: The result of the update operation.
        """
        result = await self.db_client[app_id][col_name].update_one(
            {"_id": ObjectId(doc_id)}, {"$set": new_data}
        )
        return result

    async def app_collections(self, app_id: str):
        """
        Retrieves a list of all collection names within the specified application database.

        Args:
            app_id (str): The ID of the application (database name).

        Returns:
            list[str]: A list of collection names.
        """
        return await self.app_db(app_id).list_collection_names()

    async def app_collection_documents(
        self, app_id: str, col_name: str, page: int, length: int
    ):
        """
        Retrieves documents from a specified collection with pagination.

        Args:
            app_id (str): The ID of the application (database name).
            col_name (str): The name of the collection.
            page (int): The page number (1-indexed).
            length (int): The number of documents per page.

        Returns:
            list[dict]: A list of documents from the collection.
        """
        skip_count = (page - 1) * length
        documents = (
            await self.app_db(app_id)[col_name]
            .find({})
            .skip(skip_count)
            .limit(length)
            .to_list(length)
        )
        return documents

    async def app_collection_documents_counts(self, app_id: str, col_name: str):
        """
        Retrieves the total number of documents in a specified collection.

        Args:
            app_id (str): The ID of the application (database name).
            col_name (str): The name of the collection.

        Returns:
            int: The total count of documents in the collection.
        """
        count = await self.app_db(app_id)[col_name].count_documents({})
        return count


dynamic_db = DynamicDB()
