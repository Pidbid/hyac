# core/utils.py
import random
import string

from typing import Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

from core.config import settings


def generate_short_id(length: int = 8) -> str:
    """
    Generates a short ID of a specified length, containing only lowercase and uppercase letters.
    """
    letters = string.ascii_lowercase + string.ascii_uppercase
    return "".join(random.choice(letters) for _ in range(length))


def motor_result_serializer(cursor):
    """
    Serializes Motor query results by converting ObjectId instances to strings.
    """
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])  # Convert the primary key

        # Recursively handle ObjectIds in nested documents
        def convert_ids(obj):
            if isinstance(obj, dict):
                return {
                    k: str(v) if isinstance(v, ObjectId) else convert_ids(v)
                    for k, v in obj.items()
                }
            if isinstance(obj, list):
                return [convert_ids(i) for i in obj]
            return obj

        results.append(convert_ids(doc))
    return results


async def create_mongodb_user(username: str, password: str, target_db: str) -> bool:
    """
    Creates a new MongoDB user with root credentials and grants full admin rights
    to a specific database.

    Args:
        username: The username for the new user.
        password: The password for the new user.
        target_db: The name of the database to grant access to.

    Returns:
        True if the user was created successfully, False otherwise.
    """
    # Connect to the 'admin' database using root credentials from .env
    # The user in .env must have the userAdminAnyDatabase or root role.
    client = AsyncIOMotorClient(
        host="mongodb",
        port=27017,
        username=settings.MONGODB_USERNAME,
        password=settings.MONGODB_PASSWORD,
        authSource="admin",  # Authentication database
    )

    try:
        admin_db = client.admin

        # Define roles for the user, granting full admin rights to the target_db.
        # The dbAdmin role includes read/write permissions.
        roles = [
            {"role": "dbAdmin", "db": target_db},
            {"role": "readWrite", "db": target_db},
        ]

        # Create the user
        await admin_db.command("createUser", username, pwd=password, roles=roles)
        print(
            f"User '{username}' created successfully with full admin rights on database '{target_db}'."
        )
        return True
    except OperationFailure as e:
        # Capture and handle failures, such as if the user already exists.
        error_message = e.details.get("errmsg", str(e)) if e.details else str(e)
        print(f"Failed to create user '{username}': {error_message}")
        return False
    except Exception as e:
        print(f"An unknown error occurred during user creation: {e}")
        return False
    finally:
        # Close the client connection
        client.close()
