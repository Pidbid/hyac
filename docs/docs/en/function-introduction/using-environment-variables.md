# Using Environment Variables in Functions

In Hyac, you can dynamically read and set the current application's environment variables through the stable `ctx.cloud.env()` facade. This is useful for managing configurations, secrets, or other runtime data. Legacy entries `ctx.env` / `context.env` remain compatible.

![Environment Variable Settings](../../assets/user-guide/environment-variables.png)

Use "Settings / Environment Variables" to manage application-level environment variables. The runtime watches environment changes and updates the process environment dynamically; restarting the application runtime is not required.

Calling `await ctx.cloud.env().set(...)` from code persists the value and immediately updates `os.environ` in the current runtime process. When environment variables are changed from the console, the runtime environment watcher receives MongoDB Change Stream events and refreshes `os.environ` dynamically.

## 1. Getting an Environment Variable

Use `ctx.cloud.env().get("VARIABLE_NAME")` to retrieve the value of an environment variable.

```python
async def handler(ctx):
    """
    A function demonstrating how to get an environment variable.
    """
    env = ctx.cloud.env()
    # Get the environment variable named 'API_KEY'
    api_key = env.get("API_KEY")

    if not api_key:
        return {"error": "API_KEY not configured."}

    return {"message": f"Successfully retrieved API_KEY: {api_key[:4]}****"}
```

## 2. Setting an Environment Variable

Use `await ctx.cloud.env().set("VARIABLE_NAME", "VALUE")` to set or update an environment variable. This is an asynchronous operation.

**Important**: Environment variables set this way are persistent. They override any variable of the same name set in the admin dashboard and are immediately readable in the current runtime.

```python
async def handler(ctx):
    """
    A function demonstrating how to set an environment variable.
    """
    new_api_key = "a-new-secret-key-generated-at-runtime"
    env = ctx.cloud.env()
    
    # Set or update the environment variable named 'API_KEY'
    await env.set("API_KEY", new_api_key)
    
    return {"message": "API_KEY has been updated successfully."}
```

By combining the `get` and `set` methods, you can implement dynamic configuration management, state persistence, and other advanced features without worrying about service interruptions due to configuration changes.
