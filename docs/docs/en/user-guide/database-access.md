# Database Access

Hyac provides an isolated MongoDB database for each application. The runtime injects database connections automatically, so function code does not need to build MongoDB connection strings.

The current version no longer uses Motor. User functions should use PyMongo's async or sync clients.

![Database Access](../../assets/user-guide/database-access.png)

The Database page manages collections and documents for the current application. Function code accesses the same application database through the injected runtime context.

## Recommended: Async PyMongo

Use `ctx.db` to access the current application's async database. It is backed by `pymongo.AsyncMongoClient` and is the recommended choice for most functions.

```python
async def handler(ctx, request):
    collection = ctx.db["todos"]

    result = await collection.insert_one({
        "title": "Write Hyac docs",
        "done": False
    })

    document = await collection.find_one({"_id": result.inserted_id})

    return {
        "id": str(result.inserted_id),
        "title": document["title"],
        "done": document["done"]
    }
```

Common operations:

```python
async def handler(ctx, request):
    users = ctx.db["users"]

    await users.insert_one({"name": "Alice"})
    one = await users.find_one({"name": "Alice"})
    await users.update_one({"name": "Alice"}, {"$set": {"active": True}})

    rows = []
    async for item in users.find({"active": True}).limit(10):
        item["_id"] = str(item["_id"])
        rows.append(item)

    return {"one": str(one["_id"]), "rows": rows}
```

## Sync PyMongo: `ctx.sync_db`

If a third-party library or existing code must run synchronously, use `ctx.sync_db`.

```python
async def handler(ctx, request):
    collection = ctx.sync_db["events"]
    result = collection.insert_one({"type": "login"})
    return {"id": str(result.inserted_id)}
```

Synchronous database operations block the current execution thread. For high-concurrency functions, prefer `ctx.db`.

## Database Isolation

Each application uses its own database account and database name. The runtime loads the connection by application:

```text
mongodb://<app_id>:<db_password>@mongodb:27017/<app_id>?authSource=admin&replicaSet=rs0
```

User functions normally do not need this connection string. Use `ctx.db` or `ctx.sync_db`.

## ObjectId Handling

MongoDB `_id` values are `ObjectId` instances by default and cannot be returned as JSON directly. Convert them to strings before returning.

```python
async def handler(ctx, request):
    doc = await ctx.db["items"].find_one({})
    if not doc:
        return None

    doc["_id"] = str(doc["_id"])
    return doc
```

## Error Handling

For database writes, catch exceptions and return a business-friendly message.

```python
from pymongo.errors import PyMongoError

async def handler(ctx, request):
    try:
        await ctx.db["orders"].insert_one({"status": "created"})
        return {"ok": True}
    except PyMongoError as exc:
        ctx.logger.error(f"database write failed: {exc}")
        return {"ok": False, "message": "database write failed"}
```

## Migration Note

Older docs or functions may contain `ctx.motor_db` or `context.motor_db`. In the current codebase, it is only a compatibility alias and should not be used in new functions.

Use:

```python
db = ctx.db
```

For synchronous code:

```python
db = ctx.sync_db
```

## Recommendations

- Do not hard-code MongoDB admin credentials in functions.
- Do not read or write another application's database.
- Prefer `ctx.db` for high-concurrency functions.
- Convert `_id`, `datetime`, and other non-JSON-native values before returning.
- Before delete or bulk update operations, make the query condition explicit.
