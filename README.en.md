# Hyac - A Lightweight Python Cloud Function (FaaS) Platform

<p align="right">
  <a href="./README.md">简体中文</a>
</p>

<div align="center">
  <img src="images/logo.png" width="150" alt="Hyac Logo">
</div>

> [!WARNING]
> **This project is in the early development stage.**
>
> - Features and APIs may undergo significant changes.
> - Direct deployment to a production environment may pose unknown risks and issues.
> - The project architecture may be adjusted and refactored in the future.
>
> Feedback and contributions are welcome, but please use it with caution in a production environment.

## 🖼️ Preview

<div align="center">
  <img src="images/demo.gif" alt="Demo">
</div>

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 📖 Introduction

**Hyac** is a powerful full-stack Function as a Service (FaaS) platform designed to provide an efficient, scalable, and user-friendly cloud-native development environment. It allows developers to quickly deploy, manage, and execute serverless functions, greatly simplifying the workflow from development to production.


## 🌐 Online Access

- **Project Demo**: https://console.hyacos.top
  - Default username: `admin`, Default password: `admin123`
- **Project Documentation**: https://docs.hyacos.top
## ✨ Key Features

- 🚀 **Dynamic Function Execution**: Dynamically load and execute function code in isolated Docker containers.
- 🔥 **Hot Code-Swapping**: Real-time updates of function code without service restarts.
- 🌐 **Multi-language Support**: Extensibility based on runtimes allows for future support of multiple programming languages.
- 💻 **Modern Frontend**: Built with Vue 3 and Naive UI, providing a responsive, user-friendly management interface.
- 📦 **Unified Object Storage**: Integrated with RustFS/S3-compatible object storage to provide unified file storage for functions and applications.
- 🔗 **Comprehensive API**: Offers a rich set of APIs for managing applications, functions, databases, logs, etc.

## 🏛️ System Architecture

Hyac adopts a microservices architecture based on Docker Compose, where various components work together to form an efficient FaaS ecosystem.

```mermaid
graph TD
    subgraph "👨‍💻 User End"
        U[User]
    end

    subgraph "🏗️ Infrastructure"
        T[Traefik]
        DB[(MongoDB)]
        S[(RustFS)]
    end

    subgraph "⚙️ Backend Services"
        Server[Server]
        App[App]
    end

    subgraph "🎨 Frontend Service"
        Web[Web]
    end

    U -- HTTPS --> T
    T -- Routes by domain --> Server
    T -- Routes by domain --> Web
    T -- Routes by domain --> S
    
    Server -- Manages --> App
    Server -- Reads/Writes --> DB
    Server -- Reads/Writes --> S
    
    App -- Executes Function --> App
    App -- Reads/Writes --> DB
    App -- Reads/Writes --> S

    Web -- API Requests --> Server
```

- **`traefik`**: Acts as a reverse proxy and load balancer, handling all external requests and automatically routing them to the `server`, `web`, or S3-compatible object storage service based on the domain.
- **`server`**: The core backend service, responsible for business logic, API routing, user authentication, and FaaS application management.
- **`app`**: The function executor service, which dynamically executes user-defined functions in an isolated environment.
- **`web`**: A Vue 3-based frontend application that provides the user interface.
- **`mongodb`**: Serves as the primary database, storing core data such as applications, functions, and users.
- **`rustfs`**: Provides S3-compatible object storage, for instance, to store function code, dependencies, or other files.

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, FastAPI, Beanie, PyMongo Async, Loguru
- **Frontend**: Vue.js 3, Vite, Naive UI, Pinia, UnoCSS, TypeScript
- **Database & Storage**: MongoDB, RustFS(S3-compatible)
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

2.  Configure production environment variables:

    ```bash
    cp .env.example .env
    ```

    Replace every placeholder in `.env` before startup. Required values are:

    - `DOMAIN_NAME` and `EMAIL_ADDRESS`
    - `MONGODB_USERNAME` and `MONGODB_PASSWORD`
    - `S3_ACCESS_KEY` and `S3_SECRET_KEY`
    - `SECRET_KEY` (at least 32 characters)
    - `DEFAULT_ADMIN_USER` and `DEFAULT_ADMIN_PASSWORD`
    - `GLOBAL_TAG` (a stable release tag such as `v1.2.3`, never `latest`; it is shared by server, web, app, and the LSP sidecar)

    `openssl rand -hex 32` generates a 64-character hexadecimal value that is supported by the administrator password fields. Generate a different value for every password or secret. Do not leave any `<...>` placeholder from `.env.example` in production.

3.  Generate the MongoDB cluster authentication keyfile:

    ```bash
    ./scripts/01-create-mongo-keyfile.sh
    ```

    Continue only after the script confirms mode `0400` and ownership by the MongoDB container user.

### ▶️ Starting the Services

Pull the three multi-architecture images for the selected release and start all services:

```bash
docker compose pull
docker compose up -d --no-build
```

Pushing an annotated stable `vX.Y.Z` tag starts the release workflow. It publishes `wicos/hyac_server`, `wicos/hyac_web`, and `wicos/hyac_app`. The LSP sidecar deliberately reuses the `hyac_app` image with a different startup command.

### 📦 Creating a Release

The workflow fixes the Docker Hub username to `wicos`. Configure only this GitHub Actions secret in the repository:

- `DOCKERHUB_TOKEN`: a Docker Hub access token with push permission.

Do not enable Docker Hub immutable tags, because a failed workflow must be rerunnable for the same tag. Before release, add a non-empty section for the exact same version to both `changelog/CHANGELOG.zh-CN.md` and `changelog/CHANGELOG.md`, and make sure the release commit is already on `main`. Then create and push an annotated stable tag manually:

```bash
git tag -a v1.2.3 -m "Hyac v1.2.3"
git push origin v1.2.3
```

The workflow runs the base CI, builds and pushes all three images for `linux/amd64` and `linux/arm64`, runs the production Compose/Chrome smoke test, and finally creates the bilingual GitHub Release. A smoke failure never creates the Release.

### 🌐 Access Points

- **Frontend Application**: `https://console.<DOMAIN_NAME>`

### 🔐 Local development with trusted HTTPS

Use a separate `.env.dev` with `DOMAIN_NAME=hyac.localhost` and set
`APP_CODE_PATH_ON_HOST` to the canonical output of `realpath app`. Install
`mkcert`, initialize its local CA, and create the certificate used by Traefik:

```bash
mkcert -install
mkdir -p traefik/certs
mkcert -cert-file traefik/certs/dev-cert.pem -key-file traefik/certs/dev-key.pem \
  localhost traefik.localhost "*.hyac.localhost"
```

Run the preflight before starting the development stack:

```bash
./scripts/dev-up.sh --check
./scripts/dev-up.sh
```

The preflight validates Docker, development settings, the canonical source
path, and the certificate trust chain. `*.hyac.localhost` covers static and
dynamic application subdomains; the Traefik dashboard retains the explicit
`traefik.localhost` alias. The preflight never modifies the system trust store
automatically. Local endpoints are:

- `https://console.hyac.localhost`
- `https://server.hyac.localhost/docs`
- `https://oss.hyac.localhost`
- `https://traefik.localhost`

## 📁 Major Project Structure

```
.
├── app/            # Function Executor Service
├── server/         # Core Backend Service
├── web/            # Frontend Application (Vue 3)
├── nginx/          # Nginx Configuration
├── docker-compose.yml # Docker Compose Configuration
├── ...
├── ...
├── ...
└── .env            # Environment Variables
```

## 📈 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Pidbid/Hyac&type=Date)](https://star-history.com/#Pidbid/Hyac&Date)


## 📜 Changelog

- [简体中文](./changelog/CHANGELOG.zh-CN.md)
- [English](./changelog/CHANGELOG.md)

## ️ Roadmap

We plan to add more powerful features in future versions to build a more complete, enterprise-grade FaaS platform.

For a detailed overview of future features, architectural enhancements, and improvement plans, please see our [Feature Roadmap (FEATURES.en.md)](./FEATURES.en.md). Community contributions and suggestions are welcome!

## 🤝 Contributing

We welcome contributions of all forms! If you have great ideas or find issues, please feel free to submit a Pull Request or Issue.

## 📄 License

This project is open-sourced under the [MIT License](LICENSE).
