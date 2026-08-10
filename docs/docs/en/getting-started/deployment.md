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
-   `ACME_DNS_PROVIDER` and `ACME_DNS_CREDENTIALS_FILE`
-   `MONGODB_USERNAME` and `MONGODB_PASSWORD`
-   `S3_ACCESS_KEY` and `S3_SECRET_KEY`
-   `SECRET_KEY` (at least 32 characters)
-   `DEFAULT_ADMIN_USER` and `DEFAULT_ADMIN_PASSWORD`
-   `GLOBAL_TAG` (a stable release tag such as `v1.2.3`, never `latest`; server, web, app, and the LSP sidecar share it)

`openssl rand -hex 32` generates a 64-character hexadecimal value that is supported by the administrator password fields. Generate a different value for every password or secret. Do not leave any `<...>` values from `.env.example` in the production file.

**Important:** To allow functions to be accessed via unique subdomains, you need to add a wildcard DNS record at your domain provider. Here are the details:

-   **Record Type**: `A`
-   **Host**: `*`
-   **Value**: Point this to your server's IP address

## 3. Configure DNS-01 Credentials

Production uses DNS-01 exclusively to obtain the `*.DOMAIN_NAME` wildcard certificate; there is no HTTP-01 fallback. `ACME_DNS_PROVIDER` must be selected from the [Traefik/lego provider list](https://go-acme.github.io/lego/dns/). Because every provider has different credential variables, pass them through an environment file outside the repository instead of hard-coding them in Compose.

Create an administrator-only host directory such as `/etc/hyac/acme-dns`, then configure `.env`:

```dotenv
ACME_DNS_PROVIDER=namesilo
ACME_DNS_CREDENTIALS_FILE=/etc/hyac/acme-dns/provider.env
ACME_DNS_SECRETS_DIR=/etc/hyac/acme-dns
```

For NameSilo, `/etc/hyac/acme-dns/provider.env` can contain:

```dotenv
NAMESILO_API_KEY_FILE=/run/secrets/acme-dns/namesilo-api-key
NAMESILO_PROPAGATION_TIMEOUT=1800
```

Store the API key itself in `/etc/hyac/acme-dns/namesilo-api-key`; the environment file contains only its in-container path. For another DNS service, replace the provider and variables according to its lego documentation. Never commit the credentials directory, provider environment file, or API key.

For the first deployment, use Let's Encrypt staging and a separate storage file:

```dotenv
ACME_CA_SERVER=https://acme-staging-v02.api.letsencrypt.org/directory
ACME_STORAGE_FILE=/letsencrypt/acme-staging.json
```

After confirming that TXT records are created and cleaned up automatically and the wildcard certificate is issued, switch to the production CA and `/letsencrypt/acme.json` from `.env.example`. `*.DOMAIN_NAME` covers every current Hyac endpoint, but not the `DOMAIN_NAME` apex or `x.y.DOMAIN_NAME`.

When using FRP, configure wildcard HTTP and HTTPS proxies for `*.DOMAIN_NAME` to ports 80 and 443 on the Hyac host. FRP must preserve the HTTP Host and HTTPS SNI; Hyac's local Traefik continues to terminate TLS.

## 4. Generate the MongoDB Keyfile

Run the repository script before the first production start:

```bash
./scripts/01-create-mongo-keyfile.sh
```

Continue only after the script confirms mode `0400` and ownership by the MongoDB container user. If it cannot set the required owner, run it with sufficient privileges instead of starting MongoDB with an unreadable keyfile.

## 5. Start the Services

```bash
docker compose pull
docker compose up -d --no-build
```

This pulls `wicos/hyac_server`, `wicos/hyac_web`, and `wicos/hyac_app`, then starts the required services in the background. The LSP sidecar reuses the app image because its contents are identical; only its startup command differs.

## 6. Access the System

You can now access the Hyac console at:

- `https://console.your-domain.name`

![Application list after opening the console](../../assets/user-guide/application-management.png)

After the first login, you will see the application list. Confirm that the default application or your newly created application is `running`, then enter the application workspace to create functions.
