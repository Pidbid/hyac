# Developer Deployment

This guide is designed for developers who want to set up, develop, and test Hyac in a local environment.

## Prerequisites

-   A computer with Docker and Docker Compose installed.
-   A server with a public IP address (for domain resolution and traffic forwarding).
-   A domain name with Wildcard DNS set up.
-   Git.

### Domain and Network Setup

To access the service via a public domain name during local development (which is crucial for testing features like Webhooks), you need to perform the following setup:

1.  **Domain Resolution**:
    At your domain provider, point your development domain (e.g., `dev.your-domain.name`) and its wildcard record to your public server's IP address.
    -   **Record Type**: `A`, **Host**: `dev`, **Value**: `YOUR_SERVER_PUBLIC_IP`
    -   **Record Type**: `A`, **Host**: `*.dev`, **Value**: `YOUR_SERVER_PUBLIC_IP`

2.  **Port Forwarding**:
    You need to set up a reverse proxy or a tool like **frp** or **ngrok** on your public server to forward requests from the public network to the corresponding ports on your local development machine.
    -   Forward traffic from port `80` on the public server to port `80` on your local machine.
    -   Forward traffic from port `443` on the public server to port `443` on your local machine.

    *This is a relatively advanced setup. Please refer to the official documentation of the tool you choose for specific configuration instructions.*

## 1. Clone the Repository

```bash
git clone https://github.com/Pidbid/Hyac.git
cd Hyac
```

## 2. Configure Environment Variables

Copy the `.env.example` file to `.env`.

```bash
cp .env.example .env
```

Then, open the `.env` file and modify the `DOMAIN_NAME` to your development domain:

-   `DOMAIN_NAME`: `dev.your-domain.name`

For more details on environment variables, please refer to the [Development Environment](./dev-environment.md) documentation.

## 3. Start the Development Environment

On your **local development machine**, use the `docker-compose.dev.yml` file, which is optimized for the development environment, to start all services.

```bash
docker-compose -f docker-compose.dev.yml up -d --build
```

This command will build and start all required services in the background.

## 4. Frontend Development

The frontend service is automatically deployed and started in the `hyac_web` Docker container.

**Hot Reload**: When you modify the frontend code in the `web/` directory, the development server will automatically reload. You just need to refresh your browser to see the changes.

## 5. Access the Local System

After completing all the setups, you can access your local development environment via the public domain name:

-   **Frontend**: `http://console.dev.your-domain.name`
-   **Server API Docs**: `http://server.dev.your-domain.name/docs`

You have now successfully set up your local development environment and can start coding and debugging.
