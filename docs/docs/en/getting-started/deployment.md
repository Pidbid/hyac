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

Before starting the stack, replace every placeholder in `.env`. Production requires all of the following values:

-   `DOMAIN_NAME` and `EMAIL_ADDRESS`
-   `MONGODB_USERNAME` and `MONGODB_PASSWORD`
-   `S3_ACCESS_KEY` and `S3_SECRET_KEY`
-   `SECRET_KEY` (at least 32 characters)
-   `DEFAULT_ADMIN_USER` and `DEFAULT_ADMIN_PASSWORD`
-   `APP_IMAGE_TAG` (an immutable release tag such as `v1.2.3`, never `latest`)

`openssl rand -hex 32` generates a 64-character hexadecimal value that is supported by the administrator password fields. Generate a different value for every password or secret. Do not leave any `<...>` values from `.env.example` in the production file.

**Important:** To allow functions to be accessed via unique subdomains, you need to add a wildcard DNS record at your domain provider. Here are the details:

-   **Record Type**: `A`
-   **Host**: `*`
-   **Value**: Point this to your server's IP address

## 3. Generate the MongoDB Keyfile

Run the repository script before the first production start:

```bash
./scripts/01-create-mongo-keyfile.sh
```

Continue only after the script confirms mode `0400` and ownership by the MongoDB container user. If it cannot set the required owner, run it with sufficient privileges instead of starting MongoDB with an unreadable keyfile.

## 4. Start the Services

```bash
docker compose up -d
```

This will start all the required services in the background.

## 5. Access the System

You can now access the Hyac console at:

- `https://console.your-domain.name`

![Application list after opening the console](../../assets/user-guide/application-management.png)

After the first login, you will see the application list. Confirm that the default application or your newly created application is `running`, then enter the application workspace to create functions.
