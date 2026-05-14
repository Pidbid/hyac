# 链接数据库

在 Hyac 的端点函数中，您可以通过 `context` 对象轻松地与数据库进行交互。平台同时提供了两种操作 MongoDB 的方式：

-   **异步 (Motor)**: 通过 `context.motor_db` 访问，性能更高，是**推荐**的方式。
-   **同步 (PyMongo)**: 通过 `context.pymongo_db` 访问，写法更传统，适合不熟悉异步编程的场景。

## 1. 异步操作 (Motor) - 推荐

使用异步方式可以充分利用 Python 的 `asyncio` 特性，避免在等待数据库响应时阻塞整个应用，从而实现更高的并发性能。

### 关键点

-   函数必须使用 `async def` 定义。
-   通过 `context.motor_db` 获取异步数据库实例。
-   在所有数据库操作前使用 `await` 关键字。

### 示例代码

下面的示例展示了如何在一个端点函数中使用 Motor 来执行完整的增、删、改、查（CRUD）操作。

```python
from datetime import datetime
from loguru import logger
from bson import ObjectId

async def handler(context, request, name: str = "World", value: int = 0):
    """
    一个使用 Motor (异步) 进行数据库操作的完整示例。
    """
    
    logger.info(f"[异步] 接收到参数: name='{name}', value={value}")
    db = context.motor_db  # 获取异步 Motor 数据库客户端
    demo_collection = db["hyac_demo_async"]
    
    # 1. 创建 (CREATE)
    doc = {"name": name, "value": value, "createdAt": datetime.utcnow()}
    res = await demo_collection.insert_one(doc)
    inserted_id = res.inserted_id
    logger.info(f"[异步] CREATE: 文档已插入, ID: {inserted_id}")

    # 2. 读取 (READ)
    read_doc = await demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[异步] READ: 查找到文档: {read_doc}")

    # 3. 更新 (UPDATE)
    await demo_collection.update_one({"_id": inserted_id}, {"$set": {"status": "updated"}})
    updated_doc = await demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[异步] UPDATE: 文档状态已更新: {updated_doc}")

    # 4. 删除 (DELETE)
    await demo_collection.delete_one({"_id": inserted_id})
    logger.info(f"[异步] DELETE: 文档已清理")
    
    return {"status": "ok", "driver": "motor (async)", "inserted_id": str(inserted_id)}
```

## 2. 同步操作 (PyMongo)

如果您更习惯传统的同步编程方式，或者需要执行一些不支持异步的库，可以使用 PyMongo。

Hyac 在后台对同步操作进行了优化：虽然您的代码是同步的，但 FastAPI 会在一个独立的线程池中运行它，从而避免阻塞主事件循环。

### 关键点

-   函数仍建议使用 `async def` 定义，以保持一致性。
-   通过 `context.pymongo_db` 获取同步数据库实例。
-   数据库操作是标准的同步写法，无需 `await`。

### 示例代码

```python
from datetime import datetime
from loguru import logger
from bson import ObjectId

async def handler(context, request, name: str = "World", value: int = 0):
    """
    一个使用 PyMongo (同步) 进行数据库操作的完整示例。
    """
    logger.info(f"[同步] 接收到参数: name='{name}', value={value}")
    db = context.pymongo_db  # 获取同步 PyMongo 数据库客户端
    demo_collection = db["hyac_demo_sync"]
    
    # 1. 创建 (CREATE)
    doc = {"name": name, "value": value, "createdAt": datetime.utcnow()}
    res = demo_collection.insert_one(doc)
    inserted_id = res.inserted_id
    logger.info(f"[同步] CREATE: 文档已插入, ID: {inserted_id}")

    # 2. 读取 (READ)
    read_doc = demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[同步] READ: 查找到文档: {read_doc}")

    # 3. 更新 (UPDATE)
    demo_collection.update_one({"_id": inserted_id}, {"$set": {"status": "updated"}})
    updated_doc = demo_collection.find_one({"_id": inserted_id})
    logger.info(f"[同步] UPDATE: 文档状态已更新: {updated_doc}")

    # 4. 删除 (DELETE)
    demo_collection.delete_one({"_id": inserted_id})
    logger.info(f"[同步] DELETE: 文档已清理")
    
    return {"status": "ok", "driver": "pymongo (sync)", "inserted_id": str(inserted_id)}
