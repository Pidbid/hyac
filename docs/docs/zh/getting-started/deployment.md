# 部署

本指南将引导您完成在您自己的服务器上部署 Hyac 的过程。

## 先决条件

- 一台安装了 Docker 和 Docker Compose 的服务器。
- 一个域名。

## 1. 克隆仓库

```bash
git clone https://github.com/Pidbid/Hyac.git
cd Hyac
```

## 2. 配置环境变量

有关环境变量的更多详细信息，请参阅[开发环境](../development/dev-environment.md)文档。

将 `.env.example` 文件复制为 `.env`。

```bash
cp .env.example .env
```

启动前必须替换 `.env` 中的全部占位值。生产环境必填项包括：

-   `DOMAIN_NAME`、`EMAIL_ADDRESS`
-   `ACME_DNS_PROVIDER`、`ACME_DNS_CREDENTIALS_FILE`
-   `MONGODB_USERNAME`、`MONGODB_PASSWORD`
-   `S3_ACCESS_KEY`、`S3_SECRET_KEY`
-   `SECRET_KEY`（至少 32 个字符）
-   `DEFAULT_ADMIN_USER`、`DEFAULT_ADMIN_PASSWORD`
-   `GLOBAL_TAG`（稳定发布标签，例如 `v1.2.3`，禁止使用 `latest`；server、web、app 和 LSP sidecar 共用该版本）

`openssl rand -hex 32` 会生成前后端管理员密码字段均支持的 64 位十六进制值。请为每个密码或密钥分别生成不同的随机值。生产配置中不得保留 `.env.example` 的任何 `<...>` 占位符。

**重要提示：** 为了让函数能够通过唯一的子域名进行访问，您需要在您的域名服务商处添加一条泛解析（Wildcard）记录。具体操作如下：

-   **记录类型**: `A`
-   **主机记录**: `*`
-   **记录值**: 指向您服务器的 IP 地址

## 3. 配置 DNS-01 凭据

生产环境只使用 DNS-01 申请 `*.DOMAIN_NAME` 通配符证书，不再提供 HTTP-01 回退。`ACME_DNS_PROVIDER` 必须来自 [Traefik/lego 支持列表](https://go-acme.github.io/lego/dns/)。不同 provider 使用不同的凭据变量，因此凭据通过仓库外的环境文件传入，而不是硬编码到 Compose。

推荐在宿主机创建仅管理员可读的目录，例如 `/etc/hyac/acme-dns`，并在 `.env` 中配置：

```dotenv
ACME_DNS_PROVIDER=namesilo
ACME_DNS_CREDENTIALS_FILE=/etc/hyac/acme-dns/provider.env
ACME_DNS_SECRETS_DIR=/etc/hyac/acme-dns
```

NameSilo 示例的 `/etc/hyac/acme-dns/provider.env`：

```dotenv
NAMESILO_API_KEY_FILE=/run/secrets/acme-dns/namesilo-api-key
NAMESILO_PROPAGATION_TIMEOUT=1800
```

把 API Key 单独保存在 `/etc/hyac/acme-dns/namesilo-api-key`，环境文件只保存容器内文件路径。其他 DNS 服务商应按其 lego 文档替换 provider 名称和变量。不要把凭据目录、provider 环境文件或 API Key 提交到 Git。

第一次部署建议使用 Let's Encrypt staging，并使用独立存储文件：

```dotenv
ACME_CA_SERVER=https://acme-staging-v02.api.letsencrypt.org/directory
ACME_STORAGE_FILE=/letsencrypt/acme-staging.json
```

确认 TXT 记录能自动创建和清理、通配符证书能成功签发后，再切换回 `.env.example` 中的生产 CA 和 `/letsencrypt/acme.json`。`*.DOMAIN_NAME` 覆盖当前所有 Hyac 入口，但不覆盖根域 `DOMAIN_NAME` 或 `x.y.DOMAIN_NAME`。

使用 FRP 时，为 `*.DOMAIN_NAME` 分别配置 HTTP 和 HTTPS 通配代理，转发到 Hyac 主机的 80/443。FRP 必须保留 HTTP Host 和 HTTPS SNI，TLS 仍由 Hyac 的 Traefik 终止。

## 4. 生成 MongoDB Keyfile

首次启动生产环境前，先执行仓库脚本：

```bash
./scripts/01-create-mongo-keyfile.sh
```

只有当脚本确认权限为 `0400` 且所有者为 MongoDB 容器用户后，才能继续。如果当前用户无法设置正确所有者，请使用足够权限重新运行脚本，不要让 MongoDB 使用不可读的 keyfile 启动。

## 5. 启动服务

```bash
docker compose pull
docker compose up -d --no-build
```

这会拉取 `wicos/hyac_server`、`wicos/hyac_web` 和 `wicos/hyac_app` 后在后台启动所有必需的服务。LSP sidecar 与 App Runtime 内容相同，因此复用 `hyac_app` 镜像，仅启动命令不同。

## 6. 访问系统

现在，您可以通过以下地址访问 Hyac 控制台：

- `https://console.your-domain.name` 
-- 如 官方测试地址为：`https://console.hyacos.top`

![访问控制台后的应用列表](../../assets/user-guide/application-management.png)

首次登录后会进入应用列表。确认默认应用或新建应用处于 `running` 状态后，就可以进入应用工作台创建函数。
