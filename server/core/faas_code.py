# --- Template for a Common Function ---
common_template_function = """from loguru import logger

# This is a simple function that can be called directly.
def add(a, b):
    \"\"\"Simple addition function.\"\"\"
    logger.info(f"Executing add({a}, {b})")
    return a + b
"""

# --- Template for a Common Class ---
common_template_class = """from loguru import logger

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
endpoint_template_get = """async def handler(ctx, request):
    return {"code": 0, "msg":"success", "data":"Hello, World!"}
"""

# --- Template for a POST Endpoint ---
endpoint_template_post = """from fastapi import Request
from typing import Optional

# The handler function can receive POST data in multiple ways.
# Choose the method that best suits your needs.

async def handler(
    ctx, 
    request: Request, 
    # Method 1: Automatic parameter binding from JSON body.
    # If the POST request sends `{"name": "Roo", "age": 3}`,
    # 'name' and 'age' will be automatically populated.
    name: Optional[str] = None, 
    age: Optional[int] = None,
    
    # Method 2: To get the raw request body, define a parameter named 'body'.
    # The FaaS runner will inject the raw bytes of the request body here.
    # Note: This is a special parameter name recognized by the runner.
    # body: Optional[bytes] = None
):
    \"\"\"
    An example demonstrating how to handle POST requests.
    \"\"\"
    
    # --- Usage Examples ---

    # 1. Using automatically bound parameters (from JSON)
    # This is the simplest method if you expect a JSON payload.
    if name and age is not None:
        return {
            "status": "success",
            "method": "automatic_binding",
            "message": f"Hello, {name}! You are {age} years old."
        }

    # 2. Using the raw request body (if 'body' parameter is enabled)
    # if body:
    #     body_content = body.decode('utf-8')
    #     return {
    #         "status": "success",
    #         "method": "raw_body",
    #         "content_type": request.headers.get("content-type"),
    #         "raw_payload": body_content
    #     }

    # 3. Advanced: Using the Request object for full control
    # This allows you to handle different content types, headers, etc.
    try:
        # Manually parse JSON from the request object
        json_payload = await request.json()
        return {
            "status": "success",
            "method": "manual_request_parsing",
            "data": json_payload
        }
    except Exception:
        # Handle cases where the body is not valid JSON or is empty
        return {
            "status": "info",
            "method": "manual_request_parsing",
            "message": "No valid JSON payload found in the request body."
        }

"""

# --- Template for an Endpoint with Pydantic Model Validation ---
endpoint_template_pydantic = """from pydantic import BaseModel, Field
from typing import Optional

# 1. Define your data model using Pydantic.
# This class defines the expected structure and validation rules for the request body.
class UserProfile(BaseModel):
    username: str = Field(
        ...,  # '...' indicates that this field is required
        min_length=3, 
        max_length=50,
        description="The user's unique username."
    )
    email: str = Field(..., description="The user's email address.")
    full_name: Optional[str] = Field(None, description="The user's full name (optional).")
    age: Optional[int] = Field(
        None, 
        gt=0,  # 'gt' means 'greater than'
        le=120, # 'le' means 'less than or equal to'
        description="The user's age, must be between 1 and 120."
    )

# 2. Use the model in the handler's signature.
# FastAPI will automatically validate the incoming request body against this model.
# If validation fails, it will return a detailed 422 error response automatically.
async def handler(ctx, profile: UserProfile):
    \"\"\"
    An example demonstrating Pydantic-based request body validation.
    \"\"\"
    # If the code reaches this point, the data in 'profile' is guaranteed to be valid.
    logger.info(f"Received valid user profile for: {profile.username}")
    
    # You can now work with the validated data object.
    # For example, save it to the database.
    # await ctx.motor_db["users"].insert_one(profile.dict())
    
    return {
        "status": "success",
        "message": "User profile processed successfully.",
        "user_data": profile.dict() # .dict() converts the model to a dictionary
    }
"""

# --- Template for an Endpoint with Background Tasks ---
endpoint_template_background = """from fastapi import BackgroundTasks
from loguru import logger
import time

def send_notification_email(email: str, message: str):
    \"\"\"
    A simulated long-running task. 
    In a real application, this would involve I/O operations like connecting to an SMTP server.
    \"\"\"
    logger.info(f"Preparing to send email to {email}...")
    time.sleep(5) # Simulate network latency or processing time
    logger.info(f"Email sent to {email} with message: '{message}'")

async def handler(ctx, background_tasks: BackgroundTasks, email_to: str, content: str):
    \"\"\"
    An example of scheduling a background task.
    The response is returned to the client immediately, while the task runs in the background.
    \"\"\"
    logger.info("Handler received request, scheduling email task.")
    
    # Add the task to be executed after the response has been sent.
    background_tasks.add_task(send_notification_email, email_to, content)
    
    # Return a response to the client immediately.
    return {
        "status": "accepted",
        "message": f"Email to {email_to} has been scheduled and will be sent in the background."
    }
"""

# --- Template for an Endpoint Calling an External API ---
endpoint_template_external_api = """import httpx
from loguru import logger

# It's a good practice to create the client once and reuse it.
# In a FaaS environment, you can define it globally like this.
async_client = httpx.AsyncClient(timeout=10.0)

async def handler(ctx, user_id: int = 1):
    \"\"\"
    An example of calling an external API asynchronously using httpx.
    This example fetches data from a public test API (JSONPlaceholder).
    \"\"\"
    api_url = f"https://jsonplaceholder.typicode.com/users/{user_id}"
    logger.info(f"Calling external API: {api_url}")
    
    try:
        response = await async_client.get(api_url)
        
        # Raise an exception for 4xx or 5xx status codes.
        response.raise_for_status()
        
        external_data = response.json()
        logger.info(f"Successfully received data for user: {external_data.get('name')}")
        
        return {
            "status": "success",
            "source": "external_api",
            "data": external_data
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(f"API call failed with status {e.response.status_code} for URL: {e.request.url}")
        return {"status": "error", "type": "http_status_error", "detail": str(e)}
    except httpx.RequestError as e:
        logger.error(f"An error occurred while requesting {e.request.url!r}.")
        return {"status": "error", "type": "request_error", "detail": str(e)}
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return {"status": "error", "type": "unexpected", "detail": str(e)}
"""

# --- Template for a Standard Endpoint (DB Operations) ---
endpoint_template_db = """from datetime import datetime
from loguru import logger
from bson import ObjectId

async def handler(ctx, request, name: str = "World", value: int = 0):
    # -----------------------------------------------------------------------------
    # Example 1: Asynchronous Database Operations (Motor) - Recommended
    # - Use `async def` to define the function.
    # - Get the asynchronous database instance via `ctx.motor_db`.
    # - Use the `await` keyword before all database operations to ensure non-blocking execution.
    # -----------------------------------------------------------------------------
    \"\"\"
    A complete example of database operations using Motor (asynchronous).
    \"\"\"
    
    logger.info(f"[Async] Received parameters: name='{name}', value={value}")
    db = ctx.motor_db  # Get the asynchronous Motor database client
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
    # - Get the synchronous database instance via `ctx.pymongo_db`.
    # - This is a synchronous operation, but in FastAPI's async environment, it runs 
    #   in a separate thread pool to avoid blocking the event loop.
    # -----------------------------------------------------------------------------
    \"\"\"
    A complete example of database operations using PyMongo (synchronous).
    \"\"\"
    logger.info(f"[Sync] Received parameters: name='{name}', value={value}")
    db = ctx.pymongo_db  # Get the synchronous PyMongo database client
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

async def handler(ctx, request, x: int = 10, y: int = 3):
    \"\"\"
    An example of an endpoint that calls a common function.
    This example assumes a common function with function_id 'math_utils' exists.
    \"\"\"
    
    # 1. Call a simple function from the common module
    try:
        simple_sum = ctx.common.math_utils.add(x, y)
        logger.info(f"Called 'math_utils.add', result: {simple_sum}")
    except AttributeError:
        simple_sum = "Error: 'math_utils.add' not available."

    # 2. Use a class from the common module
    try:
        Calculator = ctx.common.math_utils.AdvancedCalculator
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

# Note: The 'ctx' object provides access to 'minio_open'.
# You don't need to import it directly from 'app.core.faas_minio'.
# The FaaS environment injects it into the ctx.

async def handler(ctx, request, action: str = "read_write"):
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
            with ctx.minio_open(file_path, "w", encoding="utf-8") as f:
                f.write(content_to_write)
            logger.info(f"Successfully wrote to '{file_path}'")
        except Exception as e:
            logger.error(f"Error writing to file: {e}")
            return {"status": "error", "operation": "write", "details": str(e)}

        # 2. Read from the file (buffered)
        read_content = ""
        try:
            with ctx.minio_open(file_path, "r", encoding="utf-8") as f:
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
        with ctx.minio_open(file_path, "w") as f:
            f.write(large_content)
        logger.info(f"Created a sample large file for streaming at '{file_path}'")

        # Generator function to stream the file in chunks
        def file_streamer(path: str, chunk_size: int = 8192):
            try:
                # Use streaming=True for efficient, chunked reading
                with ctx.minio_open(path, "rb", streaming=True) as f:
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

# --- Template for an Endpoint with Notification Operations ---
endpoint_template_notification = """from loguru import logger

async def handler(ctx, action: str = "email"):
    \"\"\"
    An example demonstrating how to send notifications.
    - action='email': Sends a sample email.
    - action='webhook': Sends a sample webhook notification.
    \"\"\"
    
    if action == "email":
        logger.info("--- Sending Email Demo ---")
        try:
            await ctx.notification.send_email(
                to_address="recipient@example.com",
                subject="Hello from Hyac FaaS!",
                body="This is a test email sent from a FaaS function."
            )
            return {"status": "success", "message": "Email sent successfully."}
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return {"status": "error", "details": str(e)}
            
    elif action == "webhook":
        logger.info("--- Sending Webhook Demo ---")
        try:
            # Example payload for a Slack-like webhook
            payload = {
                "text": "New Event from Hyac FaaS",
                "attachments": [{
                    "title": "Task Completed",
                    "text": "The background processing task has finished successfully.",
                    "color": "#7CD197"
                }]
            }
            await ctx.notification.send_webhook(payload=payload)
            return {"status": "success", "message": "Webhook sent successfully."}
        except Exception as e:
            logger.error(f"Error sending webhook: {e}")
            return {"status": "error", "details": str(e)}
            
    else:
        return {"status": "error", "message": "Invalid action. Use 'email' or 'webhook'."}
"""

faas_templates = {
    "common": [
        {
            "name": "Common Function",
            "code": common_template_function,
            "description": "A simple, direct-callable function.",
        },
        {
            "name": "Common Class",
            "code": common_template_class,
            "description": "A class that needs to be instantiated before use.",
        },
    ],
    "endpoint": [
        {
            "name": "Default Endpoint GET",
            "code": endpoint_template_get,
            "description": "Default endpoint template",
        },
        {
            "name": "Default Endpoint POST",
            "code": endpoint_template_post,
            "description": "Default endpoint template for POST requests",
        },
        {
            "name": "Pydantic Validation Example",
            "code": endpoint_template_pydantic,
            "description": "Demonstrates automatic request validation with Pydantic.",
        },
        {
            "name": "Background Task Example",
            "code": endpoint_template_background,
            "description": "Shows how to run tasks in the background.",
        },
        {
            "name": "External API Call Example",
            "code": endpoint_template_external_api,
            "description": "Demonstrates calling external APIs with httpx.",
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
        {
            "name": "Notification Example",
            "code": endpoint_template_notification,
            "description": "Shows how to send email and webhook notifications.",
        },
    ],
}
