# RustFS 替代 MinIO 迁移说明

## 范围

本项目已将默认对象存储部署目标从 MinIO 调整为 RustFS，并保留 S3 API 兼容访问方式。生产迁移必须通过 S3 API 同步数据，不要直接把旧 `minio_data` 卷挂载给 RustFS。

RustFS Docker 参数参考官方文档：<https://docs.rustfs.com/installation/docker/>

## 已实施

- Docker Compose 使用 `rustfs/rustfs:latest` 替代 MinIO 镜像。
- RustFS 持久化卷使用 `rustfs_data`。
- 健康检查改为访问 S3 根路径并接受 `200` 或 `403`，因为 RustFS 会将未知路径按 bucket 解析。
- 应用新增 `S3_*` 配置，并兼容旧 `MINIO_*` 变量。
- 外部对象存储入口继续使用 `oss.${DOMAIN_NAME}`。
- 未设置 `RUSTFS_SERVER_DOMAINS`，因为 Hyac 当前使用 path-style S3 访问；设置该变量会让内部 `minio:9000` Host 被错误地按 virtual-host bucket 解析。
- `S3_REGION` 默认固定为 `us-east-1`，避免生成 presigned URL 时服务端容器必须解析外部域名来查询 bucket location。

## 未彻底实施或保留兼容的点

- Compose service name 暂时仍为 `minio`，用于保持内部 DNS `minio:9000` 兼容；容器名已改为 `hyac_rustfs`。
- Python 依赖仍保留 `minio==7.2.15` SDK，因为它是 S3 兼容客户端，不代表服务端仍使用 MinIO。
- `MinioManager`、`MinioContext`、`minio_open` 等类名/API 名称暂未改名，避免破坏用户函数和现有调用面。
- `MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` 仍作为兼容变量保留一个迁移周期。
- `mc admin user/policy` 能力未在真实 RustFS 环境完成兼容性验证，生产启用前必须单独测试或改为 RustFS 支持的用户/访问密钥管理方式。
- 本次未自动迁移任何生产数据，也未执行 Docker Compose 启动验证。

## 测试环境验证

- 启动测试环境：

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d
```

- 检查服务：

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml ps
status=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/)
test "$status" = "403" -o "$status" = "200"
```

- 验证 Hyac 存储功能：

- 创建应用，确认自动创建 bucket。
- 上传文件，确认对象可列出。
- 下载文件，确认内容一致。
- 删除文件，确认对象消失。
- 生成 presigned URL，确认外部 URL 可访问。
- 访问静态站点 bucket，确认 `index.html` 和 SPA 回退正常。

## 生产迁移步骤

- 备份 MinIO 数据卷或底层存储快照。
- 单独启动 RustFS 实例并使用全新 `rustfs_data` 卷。
- 使用 S3 API 工具配置源和目标：

```bash
mc alias set oldminio https://oss.example.com "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"
mc alias set rustfs https://oss.example.com "$S3_ACCESS_KEY" "$S3_SECRET_KEY"
```

- 对每个 bucket 执行全量同步：

```bash
mc mirror --overwrite oldminio/<bucket> rustfs/<bucket>
```

- 校验 bucket 列表、对象数量、对象大小汇总，并抽样下载比对内容。
- 进入短暂停写窗口，执行增量同步。
- 切换 Compose 配置到 RustFS，启动服务并执行完整验收。
- 保留 MinIO 只读实例至少一个观察窗口。

## 回滚

- 停止写入入口，避免 MinIO 和 RustFS 数据分叉。
- 恢复 MinIO 服务定义、`minio_data` 卷和原 endpoint 配置。
- 若 RustFS 切换期间产生新增对象，先反向同步新增对象回 MinIO。
- 重启 `minio`、`server`、`web`，验证健康检查、上传、下载、presigned URL。
