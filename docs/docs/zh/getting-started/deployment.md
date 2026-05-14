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

然后，打开 `.env` 文件并进行以下修改：

-   `DOMAIN_NAME`: 将此值修改为您自己的主域名。
-   `EMAIL_ADDRESS`: 修改为您的电子邮件地址，用于 SSL 证书申请。

**重要提示：** 为了让函数能够通过唯一的子域名进行访问，您需要在您的域名服务商处添加一条泛解析（Wildcard）记录。具体操作如下：

-   **记录类型**: `A`
-   **主机记录**: `*`
-   **记录值**: 指向您服务器的 IP 地址

## 3. 启动服务

```bash
docker-compose up -d
```

这将在后台启动所有必需的服务。

## 4. 访问系统

现在，您可以通过以下地址访问 Hyac 控制台：

- `https://console.your-domain.name` 
-- 如 官方测试地址为：`https://console.hyacos.top`

![访问控制台后的应用列表](../../assets/user-guide/application-management.png)

首次登录后会进入应用列表。确认默认应用或新建应用处于 `running` 状态后，就可以进入应用工作台创建函数。
