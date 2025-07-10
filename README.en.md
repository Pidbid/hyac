# Hyac - A Lightweight Python FaaS and Application Platform

<div align="center">
  <img src="images/logo.svg" width="150" alt="Hyac Logo">
</div>

> [!WARNING]
> **This project is in the early development stage.**
>
> - Features and APIs are subject to significant changes.
> - Deploying to a production environment may lead to unknown risks and issues.
> - The project architecture may be adjusted and refactored in the future.
>
> Feedback and contributions are welcome, but please use with caution in production.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 📖 Introduction

**Hyac** is a powerful full-stack Function as a Service (FaaS) platform designed to provide an efficient, scalable, and easy-to-use cloud-native development environment. It allows developers to quickly deploy, manage, and execute serverless functions, greatly simplifying the workflow from development to production.

## ✨ Features

- 🚀 **Dynamic Function Execution**: Dynamically load and execute function code in isolated Docker containers.
- 🔥 **Hot Code Swapping**: Update function code in real-time without restarting the service.
- 🌐 **Multi-Language Support**: Extensible runtime allows for future support of multiple programming languages.
- 💻 **Modern Frontend**: Built with Vue 3 and Naive UI, providing a responsive and user-friendly management interface.
- 📦 **Unified Object Storage**: Integrated with MinIO to provide unified file storage for functions and applications.
- 🔗 **Comprehensive API**: Offers a rich API for managing applications, functions, databases, logs, and more.

## 🏛️ System Architecture

Hyac uses a microservices architecture based on Docker Compose, where components work together to form an efficient FaaS ecosystem.

```mermaid
graph TD
    subgraph "👨‍💻 User End"
        U[User]
    end

    subgraph "🏗️ Infrastructure"
        N[Nginx]
        DB[(MongoDB)]
        S[(MinIO)]
    end

    subgraph "⚙️ Backend Services"
        Server[Server]
        App[App]
    end

    subgraph "🎨 Frontend Service"
        Web[Web]
    end

    U -- HTTPS --> N
    N -- /api --> Server
    N -- / --> Web
    
    Server -- Manages --> App
    Server -- Reads/Writes --> DB
    Server -- Reads/Writes --> S
    
    App -- Executes Function --> App
    App -- Reads/Writes --> DB
    App -- Reads/Writes --> S

    Web -- API Requests --> Server
```

- **`nginx`**: Acts as a reverse proxy, handling all external requests and routing them to the `server` or `web` service based on the path.
- **`server`**: The core backend service, responsible for business logic, API routing, user authentication, and FaaS application management.
- **`app`**: The function execution service, which dynamically executes user-defined functions in an isolated environment.
- **`web`**: A Vue 3-based frontend application that provides the user interface.
- **`mongodb`**: The primary database, storing core data such as applications, functions, and users.
- **`minio`**: Used for object storage, such as storing function code, dependencies, or other files.

## 🛠️ Technology Stack

- **Backend**: Python 3.10+, FastAPI, Beanie (Motor), Loguru
- **Frontend**: Vue.js 3, Vite, Naive UI, Pinia, UnoCSS, TypeScript
- **Database & Storage**: MongoDB, MinIO
- **Containerization**: Docker, Docker Compose

## 🚀 Getting Started

### ✅ Prerequisites

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)

### ⚙️ Installation & Configuration

1.  Clone the project locally:
    ```bash
    git clone https://github.com/your-repo/hyac.git
    cd hyac
    ```

2.  Configure environment variables:
    Copy the `.env.example` file to `.env` and modify the configurations according to your environment.

### ▶️ Starting the Services

Execute the following command to build and start all services:

```bash
docker-compose up -d --build
```

### 🌐 Access Points

- **Frontend Application**: `http://localhost:80`
- **MinIO Console**: `http://localhost:9001` (Default username/password: `minioadmin`/`minioadmin`)

## 📁 Project Structure

```
.
├── app/            # Function Executor Service
├── server/         # Core Backend Service
├── web/            # Frontend Application (Vue 3)
├── core/           # Shared Libraries
├── nginx/          # Nginx Configuration
├── docker-compose.yml # Docker Compose Configuration
└── .env            # Environment Variables
```

## 📈 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Pidbid/Hyac&type=Date)](https://star-history.com/#Pidbid/Hyac&Date)

## 🤝 Contributing

We welcome contributions of all forms! If you have great ideas or find issues, please feel free to submit a Pull Request or Issue.

## 📄 License

This project is open-sourced under the [MIT License](LICENSE).
