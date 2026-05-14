# 开发者部署方法

本指南专为希望在本地环境搭建、开发和测试 Hyac 的开发者设计。

## 先决条件

-   一台安装了 Docker 和 Docker Compose 的电脑。
-   一个拥有公网 IP 的服务器（用于域名解析和流量转发）。
-   一个域名，并为其设置了泛解析（Wildcard DNS）。
-   Git。

### 域名与网络设置

为了在本地开发时也能通过公网域名访问服务（这对于测试 Webhook 等功能至关重要），您需要进行以下设置：

1.  **域名解析**:
    在您的域名服务商处，将您的开发域名（例如 `dev.your-domain.name`）及其泛解析记录指向您公网服务器的 IP 地址。
    -   **记录类型**: `A`, **主机记录**: `dev`, **记录值**: `YOUR_SERVER_PUBLIC_IP`
    -   **记录类型**: `A`, **主机记录**: `*.dev`, **记录值**: `YOUR_SERVER_PUBLIC_IP`

2.  **内网穿透 (Port Forwarding)**:
    您需要在您的公网服务器上设置一个反向代理或内网穿透工具（如 **frp**、**ngrok** 等），将来自公网的请求转发到您本地开发机器的相应端口。
    -   将公网服务器的 `80` 端口流量转发至本地开发机器的 `80` 端口。
    -   将公网服务器的 `443` 端口流量转发至本地开发机器的 `443` 端口。

    *这是一个相对高级的设置，具体配置取决于您选择的工具。请参考相关工具的官方文档完成设置。*

## 1. 克隆仓库

```bash
git clone https://github.com/Pidbid/Hyac.git
cd Hyac
```

## 2. 配置环境变量

将 `.env.example` 文件复制为 `.env`。

```bash
cp .env.example .env
```

然后，打开 `.env` 文件并修改 `DOMAIN_NAME` 为您设置的开发域名：

-   `DOMAIN_NAME`: `dev.your-domain.name`

有关环境变量的更多详细信息，请参阅[开发环境](./dev-environment.md)文档。

## 3. 启动开发环境

在您的**本地开发机器**上，使用为开发环境优化的 `docker-compose.dev.yml` 文件来启动所有服务。

```bash
docker-compose -f docker-compose.dev.yml up -d --build
```

此命令将在后台构建并启动所有必需的服务。

## 4. 前端开发

前端服务已在 `hyac_web` Docker 容器中自动部署并启动。

**热重载**: 当您修改 `web/` 目录下的前端代码时，开发服务器会自动重新加载。您只需刷新浏览器即可看到更改。

## 5. 访问本地系统

完成上述所有设置后，您可以通过公网域名访问您的本地开发环境：

-   **前端界面**: `http://console.dev.your-domain.name`
-   **服务端 API 文档**: `http://server.dev.your-domain.name/docs`

现在您已经成功搭建了本地开发环境，可以开始进行代码开发和调试了。
