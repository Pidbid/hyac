# 架构

Hyac 基于现代化的容器架构构建。它的设计目标是可扩展、高弹性和易于维护。

```mermaid
graph TD
    A[用户] --> B{Nginx};
    B --> C[Web UI (Vue3)];
    B --> D[服务端 API (FastAPI)];
    D --> E{Docker 管理器};
    E --> F[App 容器 (FaaS)];
    D --> G[MongoDB];
    D --> H[RustFS];
    F --> G;
    F --> H;
```

## 组件

### Web UI

Web UI 是一个使用 Vue 3 和 Naive UI 构建的单页应用。它为管理应用、函数和其他资源提供了用户友好的界面。

### 服务端 API

服务端 API 是 Hyac 平台的核心。它是一个 FastAPI 应用，为管理资源提供了 RESTful API。它负责：

- 用户认证
- 管理应用和函数
- 与数据库和对象存储交互
- 管理 FaaS 容器的生命周期

### 数据库

Hyac 使用 MongoDB 存储有关应用、函数和其他资源的元数据。

### 对象存储

Hyac 使用 RustFS 提供 S3 兼容对象存储，用于存储函数代码、依赖项和其他文件。

### Docker 管理器

Docker 管理器负责管理 FaaS 容器的生命周期。它使用 Docker API 来创建、启动、停止和删除容器。

### FaaS 容器

FaaS 容器是一个运行单个 FaaS 应用的 Docker 容器。它负责执行函数和管理依赖项。
