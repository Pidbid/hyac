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
- `app/core/s3_context.py` - 应用端 S3 上下文
- `app/core/s3_manager.py` - 应用端 S3 管理器

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

- 创建应用，确认自动创建 bucket。
- 上传文件，确认对象可列出。
- 下载文件，确认内容一致。
- 删除文件，确认对象消失。
- 生成 presigned URL，确认外部 URL 可访问。
- 访问静态站点 bucket，确认 `index.html` 和 SPA 回退正常。

## 注意事项

- Python 依赖保留 `minio==7.2.15` SDK，它是 S3 兼容客户端，不代表服务端使用 MinIO。
- `mc admin user/policy` 功能需要在 RustFS 环境中验证兼容性。
