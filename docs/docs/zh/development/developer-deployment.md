# 开发者部署方法

本指南专为希望在本地环境搭建、开发和测试 Hyac 的开发者设计。

## 先决条件

-   一台安装了 Docker 和 Docker Compose 的电脑。
-   Git。

### 本地网络边界

开发 Compose 会把 Traefik 和所有调试端口绑定到 `127.0.0.1`，日常开发使用 `localhost` 子域名即可。若要通过隧道或公网反向代理暴露开发环境，必须显式修改端口绑定并单独进行安全审查；这不是默认部署方式。

## 1. 克隆仓库

```bash
git clone https://github.com/Pidbid/Hyac.git
cd Hyac
```

## 2. 配置环境变量

将 `.env.example` 复制为开发环境专用文件。

```bash
cp .env.example .env.dev
```

设置 `DOMAIN_NAME=localhost`，为 `S3_ACCESS_KEY`、`S3_SECRET_KEY`、`SECRET_KEY` 和管理员凭据填写仅用于开发的值，并把运行时源码挂载设置为宿主机规范绝对路径：

```bash
realpath app
# 将输出的绝对路径写入 .env.dev 的 APP_CODE_PATH_ON_HOST。
```

`APP_CODE_PATH_ON_HOST` 必须是规范化的绝对路径，且不能是文件系统根目录。不要在 `.env.dev` 中复用生产密钥。

有关环境变量的更多详细信息，请参阅[开发环境](./dev-environment.md)文档。

生成开发环境 Traefik 配置所引用的本地 TLS 文件。先按操作系统安装 `mkcert`，然后执行：

```bash
mkcert -install
mkdir -p traefik/certs
mkcert -cert-file traefik/certs/dev-cert.pem -key-file traefik/certs/dev-key.pem \
  localhost "*.localhost"
```

第一条命令会把本地开发 CA 安装到系统信任库。不要在生产环境复用这些证书。

## 3. 启动开发环境

在您的**本地开发机器**上，使用为开发环境优化的 `docker-compose.dev.yml` 文件来启动所有服务。

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --build
```

此命令将在后台构建并启动所有必需的服务。

## 4. 前端开发

前端服务已在 `hyac_web` Docker 容器中自动部署并启动。

**热重载**: 当您修改 `web/` 目录下的前端代码时，开发服务器会自动重新加载。您只需刷新浏览器即可看到更改。

## 5. 访问本地系统

完成上述设置后，通过仅限本机的地址访问开发环境：

-   **前端界面**: `https://console.localhost`
-   **服务端 API 文档**: `https://server.localhost/docs`

现在您已经成功搭建了本地开发环境，可以开始进行代码开发和调试了。
