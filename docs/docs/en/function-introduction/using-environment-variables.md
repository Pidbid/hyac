# Using Environment Variables in Functions

In Hyac, you can dynamically read and set environment variables specific to a function instance using the `context.env` object. This is very useful for managing configurations, secrets, or other data needed at runtime.

A core feature is that all changes to environment variables (whether made through the admin dashboard or via code) **take effect in real-time, without needing to restart the application or function**.

## 1. Getting an Environment Variable

You can use the `context.env.get("VARIABLE_NAME")` method to retrieve the value of an environment variable.

```python
async def handler(context):
    """
    A function demonstrating how to get an environment variable.
    """
    # Get the environment variable named 'API_KEY'
    api_key = context.env.get("API_KEY")

    if not api_key:
        return {"error": "API_KEY not configured."}

    return {"message": f"Successfully retrieved API_KEY: {api_key[:4]}****"}
```

## 2. Setting an Environment Variable

You can use the `await context.env.set("VARIABLE_NAME", "VALUE")` method to set or update an environment variable. This is an asynchronous operation.

**Important**: Environment variables set this way are persistent. They will override any variable of the same name set in the admin dashboard and will be available in all future executions of the function, without requiring a restart.

```python
async def handler(context):
    """
    A function demonstrating how to set an environment variable.
    """
    new_api_key = "a-new-secret-key-generated-at-runtime"
    
    # Set or update the environment variable named 'API_KEY'
    await context.env.set("API_KEY", new_api_key)
    
    return {"message": "API_KEY has been updated successfully."}
```

By combining the `get` and `set` methods, you can implement dynamic configuration management, state persistence, and other advanced features without worrying about service interruptions due to configuration changes.
