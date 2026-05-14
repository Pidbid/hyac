# Common Functions

When your business logic becomes complex, putting all the code in a single API function can become difficult to maintain. In such cases, you can extract the reusable parts into **Common Functions**.

Common functions are like reusable code libraries. They cannot be called directly via an API but can be referenced by any API function, enabling code reuse and logical decoupling.

A common function module can contain any number of functions and classes.

## 1. Create a Common Function

First, create a common function module. For example, let's create a module named `math_utils` for mathematical operations.

```python
# Common Function Module: math_utils
from loguru import logger

def add(a, b):
    """A simple addition function."""
    logger.info(f"Executing add({a}, {b})")
    return a + b

class AdvancedCalculator:
    """A calculator class that supports setting precision."""
    def __init__(self, precision: int = 2):
        self.precision = precision
        logger.info(f"AdvancedCalculator initialized with precision {self.precision}")

    def multiply(self, a, b):
        return a * b
```

## 2. Call it from an API Function

Then, in your API function, you can call this common function module through the `context.common` object.

```python
# API Function
from loguru import logger

async def handler(context, x: int = 10, y: int = 3):
    """
    An example of an API function that calls a common function.
    This example assumes a common function named 'math_utils' exists.
    """
    
    # Call the common function via context.common.math_utils
    simple_sum = context.common.math_utils.add(x, y)
    logger.info(f"Called 'math_utils.add', result: {simple_sum}")

    # Use a class from the common module
    Calculator = context.common.math_utils.AdvancedCalculator
    calc_instance = Calculator(precision=4)
    product = calc_instance.multiply(x, y)
    
    return {
        "code": 0,
        "msg": "Calculation successful",
        "data": {
            "simple_addition": simple_sum,
            "product": product
        }
    }
```

This approach allows you to break down complex business logic into multiple, maintainable common modules, keeping your API functions clean and concise.
