# Developer Deployment

This guide is designed for developers who want to set up, develop, and test Hyac in a local environment.

## Prerequisites

-   A computer with Docker and Docker Compose installed.
-   Git.

### Local Network Boundary

The development Compose file binds Traefik and all debug ports to `127.0.0.1`. Use `localhost` subdomains for routine development. Exposing the development stack through a tunnel or public reverse proxy requires a deliberate port-binding change and a separate security review; it is not the default setup.

## 1. Clone the Repository

```bash
git clone https://github.com/Pidbid/Hyac.git
cd Hyac
```

## 2. Configure Environment Variables

Copy the `.env.example` file to a development-only environment file.

```bash
cp .env.example .env.dev
```

Set `DOMAIN_NAME=hyac.localhost`, give `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `SECRET_KEY`, and the admin credentials development-only values, and set the runtime source mount to the canonical host path:

```bash
realpath app
# Copy the printed absolute path to APP_CODE_PATH_ON_HOST in .env.dev.
```

`APP_CODE_PATH_ON_HOST` must be an absolute, normalized path and must not be a filesystem root. Do not reuse production secrets in `.env.dev`.

For more details on environment variables, please refer to the [Development Environment](./dev-environment.md) documentation.

Create the local TLS files referenced by the development Traefik configuration. Install `mkcert` for your platform first, then run:

```bash
mkcert -install
mkdir -p traefik/certs
mkcert -cert-file traefik/certs/dev-cert.pem -key-file traefik/certs/dev-key.pem \
  localhost traefik.localhost "*.hyac.localhost"
```

The first command installs a local development CA into your trust store. `*.hyac.localhost` covers both static endpoints and dynamic application subdomains, while the Traefik dashboard keeps an explicit `traefik.localhost` SAN. Never reuse these certificates in production.

## 3. Start the Development Environment

On your **local development machine**, use the `docker-compose.dev.yml` file, which is optimized for the development environment, to start all services.

```bash
./scripts/dev-up.sh --check
./scripts/dev-up.sh
```

The first command validates Docker access, the development environment, the canonical source path, and the certificate trust chain without changing the host. The second command builds the required images, starts the services, waits for their health checks, and verifies the local endpoints.

## 4. Frontend Development

The frontend service is automatically deployed and started in the `hyac_web` Docker container.

**Hot Reload**: When you modify the frontend code in the `web/` directory, the development server will automatically reload. You just need to refresh your browser to see the changes.

## 5. Access the Local System

After completing the setup, access the local environment through the loopback-only endpoints:

-   **Frontend**: `https://console.hyac.localhost`
-   **Server API Docs**: `https://server.hyac.localhost/docs`
-   **Object Storage**: `https://oss.hyac.localhost`
-   **Traefik Dashboard**: `https://traefik.localhost`

You have now successfully set up your local development environment and can start coding and debugging.
