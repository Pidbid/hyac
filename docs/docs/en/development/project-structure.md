# Project Structure

The Hyac project uses a modular microservices architecture, consisting of the following core components:

-   `app`: The environment for loading and executing function code.
-   `server`: The core backend service, responsible for APIs, user management, function scheduling, etc.
-   `web`: The frontend user interface.
-   `uploader`: A service for building the frontend assets and uploading them to RustFS/S3-compatible object storage.
-   `lsp`: Language Server Protocol (in development).

Here is a detailed description of each main directory:

## Root Directory Files

-   `docker-compose.yml`: Docker Compose configuration file for the production environment.
-   `docker-compose.dev.yml`: Docker Compose configuration file for the development environment.
-   `README.md`: The main project README file.

## `app`

This directory contains the implementation of the function runtime environment. When the `server` schedules a function for execution, it uses the `app` service to load and run the corresponding function code.

-   `main.py`: The main entry point for the service.
-   `code_loader.py`: Responsible for loading function code from MongoDB.
-   `core/`: Contains core components like caching, database connections, and the S3-compatible object storage client.
-   `Dockerfile`: The Dockerfile for building the function runtime environment image.

## `server`

This is the core backend of Hyac, providing all major APIs and business logic.

-   `main.py`: The main entry point for the FastAPI application.
-   `routers/`: Contains the route definitions for all API endpoints, such as `applications.py`, `functions.py`, `users.py`, etc.
-   `core/`: Stores core business logic and components, for example:
    -   `docker_manager.py`: Manages Docker containers for function execution.
    -   `faas_code.py`: Used to initialize default function templates.
    -   `jwt_auth.py`: JWT user authentication.
    -   `task_worker.py`: A background task processor.
-   `models/`: Defines the data models for interacting with MongoDB.
-   `Dockerfile`: The Dockerfile for building the backend service image.

## `web`

The frontend project, built with Vue 3 and Vite.

-   `src/`: The frontend source code.
    -   `views/`: Page components.
    -   `components/`: Reusable UI components.
    -   `router/`: Vue Router configuration.
    -   `store/`: Pinia state management.
    -   `service/`: API request services.
-   `package.json`: Node.js dependencies and script configurations.
-   `vite.config.ts`: Vite configuration file.
-   `uno.config.ts`: UnoCSS configuration file.

## `uploader`

A Node.js service whose main responsibility is to build the frontend project in the `web` directory and upload the generated static files (assets) to the `console` bucket in RustFS.

-   `uploader.js`: The implementation of the build and upload logic.
-   `package.json`: Node.js dependency configuration.
-   `Dockerfile`: The Dockerfile for building this service's image.

## `lsp`

The Language Server, designed to provide advanced features like code completion and syntax checking for the online code editor in the frontend. **This service is currently under development and not yet officially enabled.**

-   `server.js`: The main entry point for the LSP service.
-   `package.json`: Node.js dependency configuration.
-   `Dockerfile`: The Dockerfile for building the LSP service image.
