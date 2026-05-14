# Architecture

Hyac is built on a modern, container-based architecture. It's designed to be scalable, resilient, and easy to maintain.

```mermaid
graph TD
    A[User] --> B{Nginx};
    B --> C[Web UI (Vue3)];
    B --> D[Server API (FastAPI)];
    D --> E{Docker Manager};
    E --> F[App Container (FaaS)];
    D --> G[MongoDB];
    D --> H[RustFS];
    F --> G;
    F --> H;
```

## Components

### Web UI

The Web UI is a single-page application built with Vue 3 and Naive UI. It provides a user-friendly interface for managing applications, functions, and other resources.

### Server API

The Server API is the core of the Hyac platform. It's a FastAPI application that provides a RESTful API for managing resources. It's responsible for:

- Authenticating users
- Managing applications and functions
- Interacting with the database and object storage
- Managing the lifecycle of FaaS containers

### Database

Hyac uses MongoDB to store metadata about applications, functions, and other resources.

### Object Storage

Hyac uses RustFS as S3-compatible object storage for function code, dependencies, and other files.

### Docker Manager

The Docker Manager is responsible for managing the lifecycle of FaaS containers. It uses the Docker API to create, start, stop, and remove containers.

### FaaS Container

A FaaS Container is a Docker container that runs a single FaaS application. It's responsible for executing functions and managing dependencies.
