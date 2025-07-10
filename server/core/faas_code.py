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
    \"\"\"
    A comprehensive example demonstrating database operations.
    \"\"\"
    logger.info(f"Received parameters: name='{name}', value={value}")
    db = context.db
    demo_collection = db["hyac_demo"]
    
    # CREATE
    doc = {"name": name, "value": value, "createdAt": datetime.utcnow()}
    res = await demo_collection.insert_one(doc)
    inserted_id = res.inserted_id
    logger.info(f"CREATE: Document inserted with ID: {inserted_id}")

    # READ
    read_doc = await demo_collection.find_one({"_id": inserted_id})
    logger.info(f"READ: Found document: {read_doc}")

    # UPDATE
    await demo_collection.update_one({"_id": inserted_id}, {"$set": {"status": "updated"}})
    logger.info("UPDATE: Document status updated.")

    # DELETE
    await demo_collection.delete_one({"_id": inserted_id})
    logger.info("DELETE: Document cleaned up.")
    
    return {"status": "ok", "inserted_id": str(inserted_id)}
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
    ],
}
