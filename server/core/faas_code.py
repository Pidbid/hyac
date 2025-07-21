# --- Template for a Common Function ---
common_template_base = """from loguru import logger

# This is a simple function that can be called directly.
def add(a, b):
    \"\"\"Simple addition function.\"\"\"
    logger.info(f"Executing add({a}, {b})")
    return a + b

# This is a more complex class that needs to be instantiated first.
class AdvancedCalculator:
    \"\"\"
    A calculator class that supports setting precision.
    \"\"\"
    def __init__(self, precision: int = 2):
        self.precision = precision
        logger.info(f"AdvancedCalculator initialized with precision {self.precision}")

    def multiply(self, a, b):
        \"\"\"Multiplication\"\"\"
        return a * b

    def divide(self, a, b):
        \"\"\"Division with precision control.\"\"\"
        if b == 0:
            return float('inf')
        result = a / b
        return round(result, self.precision)
"""

# --- Template for default endpoint function ---
endpoint_template_default = """async def handler(context, request):
    return {"code": 0, "msg":"success", "data":[1,2,3]}
"""

# --- Template for a Standard Endpoint (DB Operations) ---
endpoint_template_db = """from datetime import datetime
from loguru import logger
from bson import ObjectId

async def handler(context, request, name: str = "World", value: int = 0):
    # -----------------------------------------------------------------------------
    # Example 1: Asynchronous Database Operations (Motor) - Recommended
    # - Use `async def` to define the function.
    # - Get the asynchronous database instance via `context.motor_db`.
    # - Use the `await` keyword before all database operations to ensure non-blocking execution.
    # -----------------------------------------------------------------------------
    \"\"\"
    A complete example of database operations using Motor (asynchronous).
    \"\"\"
    
    logger.info(f"[Async] Received parameters: name='{name}', value={value}")
    db = context.motor_db  # Get the asynchronous Motor database client
    demo_collection = db["hyac_demo_async"]
    
    # CREATE
    doc = {"name": name, "value": value, "createdAt": datetime.utcnow()}
    res = await demo_collection.insert_one(doc)
    inserted_id = res.inserted_id
    logger.info(f"[Async] CREATE: Document inserted, ID: {inserted_id}")

    # READ
    read_doc = await demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[Async] READ: Found document: {read_doc}")

    # UPDATE
    await demo_collection.update_one({"_id": inserted_id}, {"$set": {"status": "updated"}})
    updated_doc = await demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[Async] UPDATE: Document status updated: {updated_doc}")

    # DELETE
    await demo_collection.delete_one({"_id": inserted_id})
    logger.info(f"[Async] DELETE: Document cleaned up")
    
    async_result = {"status": "ok", "driver": "motor (async)", "inserted_id": str(inserted_id)}
    
    # -----------------------------------------------------------------------------
    # Example 2: Synchronous Database Operations (Pymongo)
    # - Use `async def` to define the function.
    # - Get the synchronous database instance via `context.pymongo_db`.
    # - This is a synchronous operation, but in FastAPI's async environment, it runs 
    #   in a separate thread pool to avoid blocking the event loop.
    # -----------------------------------------------------------------------------
    \"\"\"
    A complete example of database operations using PyMongo (synchronous).
    \"\"\"
    logger.info(f"[Sync] Received parameters: name='{name}', value={value}")
    db = context.pymongo_db  # Get the synchronous PyMongo database client
    demo_collection = db["hyac_demo_sync"]
    
    # CREATE
    doc = {"name": name, "value": value, "createdAt": datetime.utcnow()}
    res = demo_collection.insert_one(doc)
    inserted_id = res.inserted_id
    logger.info(f"[Sync] CREATE: Document inserted, ID: {inserted_id}")

    # READ
    read_doc = demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[Sync] READ: Found document: {read_doc}")

    # UPDATE
    demo_collection.update_one({"_id": inserted_id}, {"$set": {"status": "updated"}})
    updated_doc = demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[Sync] UPDATE: Document status updated: {updated_doc}")

    # DELETE
    demo_collection.delete_one({"_id": inserted_id})
    logger.info(f"[Sync] DELETE: Document cleaned up")
    
    sync_result = {"status": "ok", "driver": "pymongo (sync)", "inserted_id": str(inserted_id)}
    return {"async_result": async_result, "sync_result": sync_result}
"""

# --- Template for an Endpoint that calls a Common Function ---
endpoint_template_common_call = """from loguru import logger

async def handler(context, request, x: int = 10, y: int = 3):
    \"\"\"
    An example of an endpoint that calls a common function.
    This example assumes a common function with function_id 'math_utils' exists.
    \"\"\"
    
    # 1. Call a simple function from the common module
    try:
        simple_sum = context.common.math_utils.add(x, y)
        logger.info(f"Called 'math_utils.add', result: {simple_sum}")
    except AttributeError:
        simple_sum = "Error: 'math_utils.add' not available."

    # 2. Use a class from the common module
    try:
        Calculator = context.common.math_utils.AdvancedCalculator
        calc_instance = Calculator(precision=4)
        product = calc_instance.multiply(x, y)
        quotient = calc_instance.divide(x, y)
        advanced_results = {"product": product, "quotient": quotient}
    except AttributeError:
        advanced_results = "Error: 'math_utils.AdvancedCalculator' not available."

    return {
        "code": 0,
        "msg": "Calculation successful",
        "data": {
            "simple_addition": simple_sum,
            "advanced_calculations": advanced_results
        }
    }
"""

# --- Template for an Endpoint with Storage Operations ---
endpoint_template_storage = """from loguru import logger
from fastapi.responses import StreamingResponse

# Note: The 'context' object provides access to 'minio_open'.
# You don't need to import it directly from 'app.core.faas_minio'.
# The FaaS environment injects it into the context.

async def handler(context, request, action: str = "read_write"):
    \"\"\"
    An example demonstrating file operations with MinIO.
    - action='read_write': Shows how to write and then read a file.
    - action='stream': Shows how to stream a large file as a response.
    \"\"\"
    
    file_path = "demo/my_test_file.txt"
    
    if action == "read_write":
        logger.info("--- MinIO Read/Write Demo ---")
        
        # 1. Write to a file (buffered)
        content_to_write = "Hello from Hyac FaaS! This is a test."
        try:
            with context.minio_open(file_path, "w", encoding="utf-8") as f:
                f.write(content_to_write)
            logger.info(f"Successfully wrote to '{file_path}'")
        except Exception as e:
            logger.error(f"Error writing to file: {e}")
            return {"status": "error", "operation": "write", "details": str(e)}

        # 2. Read from the file (buffered)
        read_content = ""
        try:
            with context.minio_open(file_path, "r", encoding="utf-8") as f:
                read_content = f.read()
            logger.info(f"Successfully read from '{file_path}'")
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return {"status": "error", "operation": "read", "details": str(e)}
            
        return {
            "status": "success",
            "operation": "read_write",
            "file_path": file_path,
            "content_written": content_to_write,
            "content_read": read_content
        }

    elif action == "stream":
        logger.info("--- MinIO Streaming Demo ---")
        
        # For demonstration, first ensure a file exists to be streamed.
        large_content = "This is a line in a large file.\\n" * 500
        with context.minio_open(file_path, "w") as f:
            f.write(large_content)
        logger.info(f"Created a sample large file for streaming at '{file_path}'")

        # Generator function to stream the file in chunks
        def file_streamer(path: str, chunk_size: int = 8192):
            try:
                # Use streaming=True for efficient, chunked reading
                with context.minio_open(path, "rb", streaming=True) as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
            except Exception as e:
                logger.error(f"Streaming failed: {e}")

        # Return a FastAPI StreamingResponse
        # The FaaS runner must be able to handle this response type.
        return StreamingResponse(file_streamer(file_path), media_type="text/plain")

    else:
        return {"status": "error", "message": "Invalid action specified. Use 'read_write' or 'stream'."}
"""

faas_templates = {
    "common": [
        {
            "name": "DEFAULT_COMMON",
            "code": common_template_base,
            "description": "Default common template",
        },
    ],
    "endpoint": [
        {
            "name": "DEFAULT_ENDPOINT",
            "code": endpoint_template_default,
            "description": "Default endpoint template",
        },
        {
            "name": "DB Example",
            "code": endpoint_template_db,
            "description": "Default endpoint template with db operations",
        },
        {
            "name": "Calling a Common Function Example",
            "code": endpoint_template_common_call,
            "description": "Default endpoint template with calling a common function",
        },
        {
            "name": "Storage Example (MinIO)",
            "code": endpoint_template_storage,
            "description": "Demonstrates buffered and streaming I/O with MinIO.",
        },
    ],
}
