# RustFS 对象存储配置说明

## 范围

本项目使用 RustFS 作为默认的 S3 兼容对象存储服务。所有 MinIO 相关的代码和配置已被移除，统一使用 S3 标准接口。

RustFS Docker 参数参考官方文档：<https://docs.rustfs.com/installation/docker/>

## 当前配置

- Docker Compose 使用 `rustfs/rustfs:latest` 镜像。
- 服务名称为 `rustfs`，容器名为 `hyac_rustfs`。
- 持久化卷使用 `rustfs_data`。
- 健康检查访问 S3 根路径并接受 `200` 或 `403`。
- 应用使用 `S3_*` 环境变量配置。
- 外部访问入口使用 `oss.${DOMAIN_NAME}`。
- `S3_REGION` 默认固定为 `us-east-1`。
- Server 镜像需要安装 MinIO/RustFS 兼容的 `mc` CLI，用于创建应用级存储用户并绑定 bucket 策略。
- 平台级 `S3_ACCESS_KEY` / `S3_SECRET_KEY` 只在 server 侧作为存储管理员凭据使用；应用运行时容器会注入应用级凭据。

## 环境变量

```bash
# S3 兼容对象存储配置
S3_ACCESS_KEY="rustfs"
S3_SECRET_KEY="rustfssecret"
S3_INTERNAL_ENDPOINT="rustfs:9000"
S3_EXTERNAL_ENDPOINT="oss.${DOMAIN_NAME}"
S3_SECURE_INTERNAL=false
S3_SECURE_EXTERNAL=true
S3_PUBLIC_BASE_URL="https://oss.${DOMAIN_NAME}"
S3_REGION="us-east-1"
```

## 代码结构

- `server/core/s3_manager.py` - 服务器端 S3 管理器
- `server/core/s3_external.py` - 服务器端外部 S3 管理器（用于 presigned URL）
- `server/core/app_storage.py` - 应用级存储编排服务，负责应用默认 bucket、静态站点 bucket、应用级用户和权限策略
- `server/models/storage_model.py` - 应用存储身份与 bucket 元数据
- `app/core/s3_context.py` - 应用端 S3 上下文
- `app/core/s3_manager.py` - 应用端 S3 管理器

## 应用级存储模型

- 每个应用拥有独立的 `ApplicationStorage` 记录，包含应用级 `access_key`、`secret_key` 和配置状态。
- 每个应用默认拥有一个私有 bucket，命名为 `app_id.lower()`。
- 每个应用仍保留 `web-{app_id.lower()}` 静态站点 bucket，并保持公开读策略。
- 启动应用运行时容器前，server 会调用 `app_storage_service.ensure_ready(app_id)` 确保存储资源和应用级权限存在。
- 应用运行时只拿到自己的应用级 S3 凭据，`s3_open()` 不再自动创建 bucket；bucket 不存在时会报错，避免用户代码用运行时凭据隐式创建资源。
- 删除应用时，server 会删除默认 bucket、静态站点 bucket、应用级存储用户和对应元数据。

## 测试环境验证

启动测试环境：

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d
```

检查服务：

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml ps
status=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/)
test "$status" = "403" -o "$status" = "200"
```

验证功能：

- 创建应用，确认自动创建默认 bucket、静态站点 bucket、应用级存储用户和只允许访问默认 bucket 的策略。
- 启动应用运行时，确认容器内 `S3_ACCESS_KEY` / `S3_SECRET_KEY` 为应用级凭据，而不是平台级管理员凭据。
- 上传文件，确认对象可列出。
- 下载文件，确认内容一致。
- 删除文件，确认对象消失。
- 生成 presigned URL，确认外部 URL 可访问。
- 访问静态站点 bucket，确认 `index.html` 和 SPA 回退正常。

## 注意事项

- Python 依赖保留 `minio==7.2.15` SDK，它是 S3 兼容客户端，不代表服务端使用 MinIO。
- `mc admin user/policy` 由 server 侧统一执行，用于创建应用级用户并绑定最小权限策略。
- 首次部署新版本前，需要重新构建 server 镜像，确保 `mc` CLI 已安装。
