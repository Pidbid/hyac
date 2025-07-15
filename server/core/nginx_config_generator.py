import os
import logging
from core.config import settings

logger = logging.getLogger(__name__)


def generate_nginx_configs():
    """
    Generates Nginx configuration files if they do not already exist.
    This function is designed to be run on server startup.
    """
    conf_dir = "/nginx/conf.d"
    os.makedirs(conf_dir, exist_ok=True)
    logger.info(f"Ensuring Nginx conf directory exists at: {conf_dir}")

    domain_name = settings.DOMAIN_NAME

    # Define a dictionary to hold all Nginx configurations
    configs = {
        "server.conf": f"""server {{
    listen 80;
    listen [::]:80;
    listen 443 ssl http2;
    listen [::]:443 ssl http2;

    server_name server.{domain_name};

    ssl_certificate /etc/letsencrypt/live/server.{domain_name}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/server.{domain_name}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/server.{domain_name}/chain.pem;
    ssl_dhparam /etc/letsencrypt/dhparams/dhparam.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    location / {{
        proxy_pass http://server:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
""",
        "oss.conf": f"""server {{
    listen 80;
    listen [::]:80;
    listen 443 ssl http2;
    listen [::]:443 ssl http2;

    server_name oss.{domain_name};

    ssl_certificate /etc/letsencrypt/live/oss.{domain_name}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/oss.{domain_name}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/oss.{domain_name}/chain.pem;
    ssl_dhparam /etc/letsencrypt/dhparams/dhparam.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    location / {{
        proxy_pass http://minio:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
""",
        "console.conf": f"""server {{
    listen 80;
    listen [::]:80;
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;

    server_name console.{domain_name};

    ssl_certificate /etc/letsencrypt/live/console.{domain_name}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/console.{domain_name}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/console.{domain_name}/chain.pem;
    ssl_dhparam /etc/letsencrypt/dhparams/dhparam.pem;

    access_log /var/log/nginx/console.access.log;
    error_log /var/log/nginx/console.error.log;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    set $minio_backend http://minio:9000/console;

    location / {{
        if ($request_uri = /) {{
            rewrite / /index.html last;
        }}
        proxy_intercept_errors on;
        proxy_pass $minio_backend$request_uri;
        error_page 404 = /index.html;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header x-amz-content-sha256 "UNSIGNED-PAYLOAD";
        proxy_hide_header 'x-amz-id-2';
        proxy_hide_header 'x-amz-request-id';
        proxy_hide_header 'x-amz-meta-server-side-encryption';
        proxy_hide_header 'x-amz-server-side-encryption';
        proxy_hide_header 'x-amz-version-id';
    }}

    location = /index.html {{
        proxy_pass $minio_backend/index.html;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header x-amz-content-sha256 "UNSIGNED-PAYLOAD";
    }}
}}
""",
    }

    # Write each configuration file if it doesn't exist
    for filename, content in configs.items():
        filepath = os.path.join(conf_dir, filename)
        if not os.path.exists(filepath):
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"Successfully generated Nginx config: {filepath}")
            except IOError as e:
                logger.error(f"Failed to write Nginx config {filepath}: {e}")
        else:
            logger.info(f"Nginx config already exists, skipping: {filepath}")
