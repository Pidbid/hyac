# Project Hyac - Future Features & Improvements

This document outlines the future development roadmap for Project Hyac, focusing on enhancing its architecture, developer experience, security, and scalability.

## 1. Architectural Enhancements

### 1.1. Multi-tenancy Support
- **Goal**: Implement complete tenant isolation, allowing different users or teams to securely run their applications on shared infrastructure.
- **Implementation**:
    - **Data Isolation**: Implement logical or physical data isolation for each tenant (user/team) at the database level.
    - **Network Isolation**: Ensure that a tenant's containerized application cannot access the network resources of another tenant.
    - **Resource Quotas**: Set quotas for CPU, memory, storage, and function execution counts for each tenant.

### 1.2. Runtime Management
- **Goal**: Allow administrators to dynamically add, configure, and manage new function runtime environments.
- **Implementation**:
    - **Pluggable Runtimes**: Design a standard interface to simplify the integration of new runtimes (e.g., Node.js, Deno, Java).
    - **Version Control**: Support multiple versions of the same language (e.g., Python 3.9, 3.10, 3.11).

## 2. Developer Experience (DX) Improvements

### 2.1. Context-Aware Intellisense in Editor

- **Current Limitation:** The frontend CodeMirror editor lacks code completion for the `context` object because the context is "magically" injected on the backend.
- **Proposed Feature:** Provide full, context-aware Intellisense directly in the user's editor.
  - **Implementation:**
    - **Frontend:** Dynamically prepend a virtual "shim" file to the user's code in-memory. This shim, invisible to the user, will contain `import` statements and type definitions (e.g., `from app.context import FunctionContext`).
    - **LSP:** The language server will receive this complete code block, enabling it to analyze the context and provide accurate autocompletion.
    - **Backend:** The execution engine will similarly prepend the shim before `exec` to ensure the runtime environment matches the development environment.
  - **Benefits:**
    - A seamless and professional development experience.
    - Reduced errors and improved developer productivity.

## 3. Security Hardening

### 3.1. Sandbox for User Code Execution

- **Current Limitation:** User code is executed directly via `exec`, posing a significant security risk. Malicious code could compromise the host system.
- **Proposed Feature:** Execute all user-provided code within a secure, isolated sandbox.
  - **Implementation Options:**
    - **gVisor/Firecracker (Recommended):** Utilize lightweight virtualization technology to create a secure sandbox for each function execution. This provides strong kernel-level isolation.
    - **Restricted `__builtins__`:** As a baseline measure, severely limit the available built-in functions within the `exec` scope to prevent access to the filesystem (`open`), network, or other sensitive APIs.
    - **WebAssembly (WASM) Runtime:** Explore compiling user Python code to WASM and running it in a secure WASM runtime for maximum isolation.
  - **Benefits:**
    - Prevents security breaches and data leaks.
    - Ensures the stability and integrity of the platform.

## 4. Scalability and Performance

### 4.1. Evolution to a Distributed Task Queue

- **Current Architecture:** The system already leverages FastAPI's capabilities to execute functions non-blockingly. Whether native `async` functions or `def` synchronous functions running in a thread pool, they do not block the main event loop.
- **Future Challenges:** For complex tasks that are long-running (exceeding standard HTTP timeouts), require retry mechanisms, or need to be decoupled from the main application lifecycle, the current request-response model has limitations.
- **Proposed Feature:** Introduce a dedicated distributed task queue system, evolving the function execution model from "immediate execution" to "background tasks".
  - **Implementation:**
    - Integrate a message queue system (e.g., Celery with Redis/RabbitMQ).
    - For functions marked as "background tasks", the API will receive the request, dispatch the task to the queue, and immediately return a task ID.
    - A pool of independently scalable Worker processes will consume tasks from the queue and execute the code.
    - Provide API endpoints to allow clients to query the task's status, progress, and results using the task ID.
  - **Benefits:**
    - **Support for Long-Running Tasks:** Reliably execute tasks that exceed web request timeout limits.
    - **Enhanced System Resilience:** Support for automatic retries and error handling, improving task success rates.
    - **Better Resource Isolation:** Completely separate compute-intensive tasks from the API server, allowing workers to be scaled independently without affecting API responsiveness.
    - **Asynchronous Communication:** Lays the foundation for future implementation of Webhooks or other event-driven architectures.

## 5. Platform & Application Features

### 5.1. Platform-Level Features
- [ ] **Multi-User & Permissions Management**: Introduce roles (e.g., admin, developer) for fine-grained access control and collaborative development.
- [ ] **Platform Monitoring Dashboard**: Provide a global view of system status, resource utilization, and audit logs.
- [ ] **System-Level Integration Configuration**: Offer a unified interface to configure global SMTP, object storage, and third-party notification services.

### 5.2. Application-Level Features
- [ ] **Custom Domains & Advanced Access Control**: Support binding custom domains and provide IP whitelist/blacklist functionality.
- [ ] **Dependency Analysis & Security Scanning**: Integrate tools to detect dependency conflicts and known security vulnerabilities.
- [ ] **Function Template Marketplace**: Create a community-driven marketplace for sharing and using pre-built function templates.
