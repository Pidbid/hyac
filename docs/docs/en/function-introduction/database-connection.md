# Database Connection

In Hyac's endpoint functions, you can easily interact with the database through the `context` object. The platform provides two ways to operate MongoDB:

-   **Asynchronous (Motor)**: Accessed via `context.motor_db`, offers higher performance and is the **recommended** method.
-   **Synchronous (PyMongo)**: Accessed via `context.pymongo_db`, uses a more traditional syntax, suitable for scenarios where you are not familiar with asynchronous programming.

## 1. Asynchronous Operations (Motor) - Recommended

Using the asynchronous approach allows you to take full advantage of Python's `asyncio` features, avoiding blocking the entire application while waiting for a database response, thus achieving higher concurrency.

### Key Points

-   The function must be defined with `async def`.
-   Get the asynchronous database instance via `context.motor_db`.
-   Use the `await` keyword before all database operations.

### Code Example

The following example demonstrates how to perform complete CRUD (Create, Read, Update, Delete) operations using Motor in an endpoint function.

```python
from datetime import datetime
from loguru import logger
from bson import ObjectId

async def handler(context, request, name: str = "World", value: int = 0):
    """
    A complete example of database operations using Motor (asynchronous).
    """
    
    logger.info(f"[Async] Received parameters: name='{name}', value={value}")
    db = context.motor_db  # Get the asynchronous Motor database client
    demo_collection = db["hyac_demo_async"]
    
    # 1. CREATE
    doc = {"name": name, "value": value, "createdAt": datetime.utcnow()}
    res = await demo_collection.insert_one(doc)
    inserted_id = res.inserted_id
    logger.info(f"[Async] CREATE: Document inserted, ID: {inserted_id}")

    # 2. READ
    read_doc = await demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[Async] READ: Found document: {read_doc}")

    # 3. UPDATE
    await demo_collection.update_one({"_id": inserted_id}, {"$set": {"status": "updated"}})
    updated_doc = await demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[Async] UPDATE: Document status updated: {updated_doc}")

    # 4. DELETE
    await demo_collection.delete_one({"_id": inserted_id})
    logger.info(f"[Async] DELETE: Document cleaned up")
    
    return {"status": "ok", "driver": "motor (async)", "inserted_id": str(inserted_id)}
```

## 2. Synchronous Operations (PyMongo)

If you are more accustomed to traditional synchronous programming or need to use libraries that do not support asynchronous operations, you can use PyMongo.

Hyac optimizes synchronous operations in the background: although your code is synchronous, FastAPI runs it in a separate thread pool to avoid blocking the main event loop.

### Key Points

-   It is still recommended to define the function with `async def` for consistency.
-   Get the synchronous database instance via `context.pymongo_db`.
-   Database operations use standard synchronous syntax, with no need for `await`.

### Code Example

```python
from datetime import datetime
from loguru import logger
from bson import ObjectId

async def handler(context, request, name: str = "World", value: int = 0):
    """
    A complete example of database operations using PyMongo (synchronous).
    """
    logger.info(f"[Sync] Received parameters: name='{name}', value={value}")
    db = context.pymongo_db  # Get the synchronous PyMongo database client
    demo_collection = db["hyac_demo_sync"]
    
    # 1. CREATE
    doc = {"name": name, "value": value, "createdAt": datetime.utcnow()}
    res = demo_collection.insert_one(doc)
    inserted_id = res.inserted_id
    logger.info(f"[Sync] CREATE: Document inserted, ID: {inserted_id}")

    # 2. READ
    read_doc = demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[Sync] READ: Found document: {read_doc}")

    # 3. UPDATE
    demo_collection.update_one({"_id": inserted_id}, {"$set": {"status": "updated"}})
    updated_doc = demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[Sync] UPDATE: Document status updated: {updated_doc}")

    # 4. DELETE
    demo_collection.delete_one({"_id": inserted_id})
    logger.info(f"[Sync] DELETE: Document cleaned up")
    
    return {"status": "ok", "driver": "pymongo (sync)", "inserted_id": str(inserted_id)}
