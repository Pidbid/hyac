# 项目结构

Hyac 项目采用模块化的微服务架构，主要由以下几个核心部分组成：

-   `app`: 函数代码加载与执行环境。
-   `server`: 核心后端服务，负责 API、用户管理、函数调度等。
-   `web`: 前端用户界面。
-   `uploader`: 用于构建前端产物并上传至 RustFS/S3 兼容对象存储的服务。
-   `lsp`: 语言服务器（开发中）。

以下是各主要目录的详细说明：

## 根目录文件

-   `docker-compose.yml`: 生产环境的 Docker Compose 配置文件。
-   `docker-compose.dev.yml`: 开发环境的 Docker Compose 配置文件。
-   `README.md`: 项目主说明文档。

## `app`

此目录包含了函数运行环境的实现。当 `server` 调度一个函数执行时，它会通过 `app` 服务来加载并运行相应的函数代码。

-   `main.py`: 服务主入口。
-   `code_loader.py`: 负责从 MongoDB 加载函数代码。
-   `core/`: 包含缓存、数据库连接、S3 兼容对象存储客户端等核心组件。
-   `Dockerfile`: 用于构建函数运行环境的 Docker 镜像。

## `server`

这是 Hyac 的核心后端，提供所有主要的 API 和业务逻辑。

-   `main.py`: FastAPI 应用主入口。
-   `routers/`: 包含了所有 API 端点的路由定义，如 `applications.py`, `functions.py`, `users.py` 等。
-   `core/`: 存放核心业务逻辑和组件，例如：
    -   `docker_manager.py`: 管理函数执行的 Docker 容器。
    -   `faas_code.py`: 用于初始化默认的函数模板。
    -   `jwt_auth.py`: JWT 用户认证。
    -   `task_worker.py`: 后台任务处理器。
-   `models/`: 定义了与 MongoDB 交互的数据模型。
-   `Dockerfile`: 用于构建后端服务的 Docker 镜像。

## `web`

前端项目，基于 Vue 3 和 Vite 构建。

-   `src/`: 前端源代码。
    -   `views/`: 页面组件。
    -   `components/`: 可复用的 UI 组件。
    -   `router/`: Vue Router 的路由配置。
    -   `store/`: Pinia 状态管理。
    -   `service/`: API 请求服务。
-   `package.json`: Node.js 依赖和脚本配置。
-   `vite.config.ts`: Vite 配置文件。
-   `uno.config.ts`: UnoCSS 配置文件。

## `uploader`

一个 Node.js 服务，其主要职责是构建 `web` 目录下的前端项目，并将生成的静态文件（产物）上传到 RustFS 的 `console` Bucket 中。

-   `uploader.js`: 构建与上传逻辑的实现。
-   `package.json`: Node.js 依赖配置。
-   `Dockerfile`: 用于构建此服务的 Docker 镜像。

## `lsp`

语言服务器，旨在为前端的在线代码编辑器提供代码补全、语法检查等高级功能。**此服务目前仍在开发阶段，未正式启用。**

-   `server.js`: LSP 服务主入口。
-   `package.json`: Node.js 依赖配置。
-   `Dockerfile`: 用于构建 LSP 服务的 Docker 镜像。
