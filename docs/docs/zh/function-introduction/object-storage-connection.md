# 连接对象存储

Hyac 使用 RustFS 提供 S3 兼容对象存储。函数运行时推荐通过 `ctx.cloud.storage()` 访问当前应用对应的 Bucket，不需要在函数代码中直接维护 RustFS 的访问密钥。旧入口 `ctx.s3` 仍保持兼容。

![对象存储页面](../../assets/user-guide/storage-access.png)

控制台“存储”页展示当前应用 Bucket 的文件。函数中通过 `ctx.cloud.storage()` 读写的也是这份应用存储。

常见用途包括：

- 读取应用文件
- 写入函数生成的文件
- 管理临时或持久化对象数据

示例：

```python
async def handler(ctx):
    storage = ctx.cloud.storage()
    data = await storage.get("demo/hello.txt")
    if data is None:
        return {"ok": False, "message": "file not found or read failed"}

    return {"ok": True, "content": data.decode("utf-8")}
```

如果需要写入对象：

```python
async def handler(ctx):
    storage = ctx.cloud.storage()
    ok = await storage.put("demo/hello.txt", "Hello from Hyac".encode("utf-8"))
    if not ok:
        return {"ok": False, "message": "write failed"}

    return {"ok": True}
```

`put()` 返回 `False` 表示写入失败，`get()` 返回 `None` 表示读取失败或对象不存在。

底层存储服务是 RustFS，但接口保持 S3 兼容，因此配置项仍使用 `S3_*` 命名。
