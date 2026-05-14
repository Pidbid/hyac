# Deployment

This guide will walk you through the process of deploying Hyac on your own server.

## Prerequisites

- A server with Docker and Docker Compose installed.
- A domain name.

## 1. Clone the Repository

```bash
git clone https://github.com/Pidbid/Hyac.git
cd Hyac
```

## 2. Configure Environment Variables

For more details on environment variables, please refer to the [Development Environment](../development/dev-environment.md) documentation.

Copy the `.env.example` file to `.env`.

```bash
cp .env.example .env
```

Then, open the `.env` file and make the following changes:

-   `DOMAIN_NAME`: Change this value to your own main domain name.
-   `EMAIL_ADDRESS`: Change this to your email address, which will be used for SSL certificate requests.

**Important:** To allow functions to be accessed via unique subdomains, you need to add a wildcard DNS record at your domain provider. Here are the details:

-   **Record Type**: `A`
-   **Host**: `*`
-   **Value**: Point this to your server's IP address

## 3. Start the Services

```bash
docker-compose up -d
```

This will start all the required services in the background.

## 4. Access the System

You can now access the Hyac console at:

- `https://console.your-domain.name`
