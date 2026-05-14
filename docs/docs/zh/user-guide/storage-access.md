# 对象存储访问

对象存储用于管理当前应用的文件。Hyac 默认使用 RustFS 提供 S3 兼容存储，但用户在控制台和函数代码中通常不需要直接处理 RustFS 访问密钥。

![对象存储](../../assets/user-guide/storage-access.png)

对象存储页面展示当前应用 Bucket 的文件。控制台中的上传、下载和预览操作，与函数代码中的 `ctx.s3` 访问的是同一份应用存储。

## 控制台文件管理

进入“对象存储”页面后，看到的是当前应用对应的 Bucket 内容。

支持的常见操作：

- 浏览文件和文件夹。
- 上传文件。
- 下载文件。
- 删除单个或多个文件。
- 创建和删除文件夹。
- 预览图片、音频、视频和 JSON 文件。

如果页面为空，请先确认当前选中的应用是否正确。

## 路径规则

对象存储使用对象路径，不是真实目录。控制台会用文件夹形式展示路径前缀。

示例：

```text
images/logo.png
exports/report.json
tmp/upload.csv
```

建议按业务分类组织文件，避免把所有文件放在根目录。

## 函数中读取文件

函数运行时通过 `ctx.s3` 访问当前应用的对象存储。

```python
async def handler(ctx, request):
    data = await ctx.s3.get("demo/hello.txt")
    if not data:
        return {"content": ""}

    return {"content": data.decode("utf-8")}
```

## 函数中写入文件

```python
async def handler(ctx, request):
    ok = await ctx.s3.put("demo/hello.txt", b"Hello from Hyac")
    return {"ok": ok}
```

## 常见场景

### 保存函数生成的文件

```python
import json

async def handler(ctx, request):
    payload = {"status": "ok"}
    await ctx.s3.put(
        "exports/result.json",
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )
    return {"saved": True}
```

### 读取用户上传的配置

```python
import json

async def handler(ctx, request):
    raw = await ctx.s3.get("config/settings.json")
    if not raw:
        return {"error": "settings.json not found"}

    settings = json.loads(raw.decode("utf-8"))
    return {"settings": settings}
```

## 权限和隔离

对象存储按应用隔离。一个应用的函数默认只应访问自己的 Bucket。

不要在函数代码中硬编码全局 S3 密钥。需要访问外部对象存储时，应把外部凭据放在环境变量中，并限制权限。

## 常见问题

### 预览失败

确认文件类型是否支持预览。控制台通常支持图片、视频、音频和 JSON；其他文件可以下载后查看。

### 上传后函数读不到

检查路径是否一致。对象路径区分前缀，`demo/a.txt` 和 `a.txt` 是两个不同对象。

### 外部无法访问文件

控制台下载链接由后端生成，是否可外部访问取决于部署域名、Traefik、RustFS 和签名 URL 配置。生产环境应使用 `https://oss.<DOMAIN_NAME>`。
