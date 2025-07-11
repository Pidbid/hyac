# Hyac - 轻量级Python函数计算与应用平台

<p align="right">
  <a href="./README.en.md">English</a>
</p>

<div align="center">
  <img src="images/logo.svg" width="150" alt="Hyac Logo">
</div>

> [!WARNING]
> **当前项目处于早期开发阶段**
>
> - 功能和 API 可能会发生较大变化。
> - 直接部署用于生产环境可能会存在未知的风险和问题。
> - 项目架构在后期可能会进行调整和重构。
>
> 欢迎提供反馈和贡献，但请谨慎用于生产环境。

## 🖼️ 预览

<div align="center">
  <img src="images/demo.gif" alt="Demo">
</div>

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 📖 介绍

**Hyac** 是一个功能强大的全栈函数即服务 (FaaS) 平台，旨在提供一个高效、可扩展且易于使用的云原生开发环境。它允许开发者快速部署、管理和执行无服务器函数，极大地简化了从开发到生产的流程。

## ✨ 主要功能

- 🚀 **动态函数执行**: 在隔离的 Docker 容器中动态加载和执行函数代码。
- 🔥 **代码热更新**: 无需重启服务即可实现函数代码的实时更新。
- 🌐 **多语言支持**: 基于运行时的可扩展性，未来可以支持多种编程语言。
- 💻 **现代化前端**: 基于 Vue 3 和 Naive UI 构建，提供响应式、用户友好的管理界面。
- 📦 **统一对象存储**: 集成 MinIO，为函数和应用提供统一的文件存储服务。
- 🔗 **全面的 API**: 提供丰富的 API，用于管理应用、函数、数据库、日志等。

## 🏛️ 系统架构

Hyac 采用基于 Docker Compose 的微服务架构，各组件协同工作，形成一个高效的 FaaS 生态系统。

```mermaid
graph TD
    subgraph "👨‍💻 用户端"
        U[用户]
    end

    subgraph "🏗️ 基础设施"
        N[Nginx]
        DB[(MongoDB)]
        S[(MinIO)]
    end

    subgraph "⚙️ 后端服务"
        Server[Server]
        App[App]
    end

    subgraph "🎨 前端服务"
        Web[Web]
    end

    U -- HTTPS --> N
    N -- /api --> Server
    N -- / --> Web
    
    Server -- 管理 --> App
    Server -- 读写 --> DB
    Server -- 读写 --> S
    
    App -- 执行函数 --> App
    App -- 读写 --> DB
    App -- 读写 --> S

    Web -- API请求 --> Server
```

- **`nginx`**: 作为反向代理，处理所有外部请求，并根据路径将其路由到 `server` 或 `web` 服务。
- **`server`**: 核心后端服务，负责业务逻辑、API 路由、用户认证和 FaaS 应用管理。
- **`app`**: 函数执行器服务，在隔离的环境中动态执行用户定义的函数。
- **`web`**: 基于 Vue 3 的前端应用，提供用户交互界面。
- **`mongodb`**: 作为主数据库，存储应用、函数、用户等核心数据。
- **`minio`**: 用于对象存储，例如存放函数代码、依赖或其他文件。

## 🛠️ 技术栈

- **后端**: Python 3.10+, FastAPI, Beanie (Motor), Loguru
- **前端**: Vue.js 3, Vite, Naive UI, Pinia, UnoCSS, TypeScript
- **数据库与存储**: MongoDB, MinIO
- **容器化**: Docker, Docker Compose

## 🚀 快速开始

### ✅ 环境准备

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)

### ⚙️ 安装与配置

1.  克隆项目到本地:
    ```bash
    git clone https://github.com/your-repo/hyac.git
    cd hyac
    ```

2.  配置环境变量:
    复制 `.env.example` 文件并重命名为 `.env`，然后根据您的环境修改其中的配置。

### ▶️ 启动服务

执行以下命令以构建和启动所有服务：

```bash
docker-compose up -d
```

### 🌐 访问地址

- **前端应用**: `http://localhost:80`
- **MinIO 控制台**: `http://localhost:9001` (默认用户名/密码: `minioadmin`/`minioadmin`)

## 📁 主要项目结构

```
.
├── app/            # 函数执行器服务
├── server/         # 核心后端服务
├── web/            # 前端应用 (Vue 3)
├── nginx/          # Nginx 配置
├── docker-compose.yml # Docker Compose 配置
├── ...
├── ...
├── ...
└── .env            # 环境变量
```

## 📈 Star 历史

[![Star History Chart](https://api.star-history.com/svg?repos=Pidbid/Hyac&type=Date)](https://star-history.com/#Pidbid/Hyac&Date)


## 🤝 贡献指南

我们欢迎任何形式的贡献！如果您有好的想法或发现了问题，请随时提交 Pull Request 或 Issue。

## 📄 开源许可

本项目基于 [MIT License](LICENSE) 开源。
