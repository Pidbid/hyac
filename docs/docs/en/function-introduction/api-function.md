# API Functions

An API Function (or Endpoint Function) is the entry point for your business logic and can be accessed directly from the outside world via a unique URL. Every API function must define an asynchronous function named `handler`.

The parameters for the `handler` function are flexible, but `context` is a required first parameter.

```python
async def handler(context, request):
    """
    A basic API function that returns fixed JSON data.
    """
    # The request object can also be accessed via context.request
    # print(context.request.headers)
    return {"code": 0, "msg":"success", "data":[1,2,3]}
```

-   `context`: **(Required)** The context object, which contains environment information such as database connections, common function modules, and the request object (`context.request`).
-   `request`: **(Optional)** The FastAPI request object. You can inject it directly into the `handler` function or access it via `context.request`—both have the same effect. It contains detailed information about the request, such as headers and query parameters.

You can also define additional parameters for the `handler` function. These will be automatically injected from the request's query parameters or body, thanks to FastAPI's dependency injection feature.

```python
# A version that omits the request parameter
async def handler(context, name: str = "World"):
    """
    An API function that accepts a parameter.
    If the request includes a 'name' parameter (e.g., ?name=Hyac), it will be automatically injected.
    """
    return {"hello": name}
