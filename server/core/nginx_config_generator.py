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

    server_name server.{domain_name};

    location / {{
        proxy_pass http://server:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
""",
        "oss.conf": f"""server {{
    listen 80;
    listen [::]:80;

    server_name oss.{domain_name};

    location / {{
        proxy_pass http://minio:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
""",
        "console.conf": f"""server {{
    listen 80;
    server_name console.{domain_name};

    access_log /var/log/nginx/console.access.log;
    error_log /var/log/nginx/console.error.log;

    location = / {{
        proxy_pass http://minio:9000/console/index.html;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header x-amz-content-sha256 "UNSIGNED-PAYLOAD";
        proxy_hide_header 'x-amz-id-2';
        proxy_hide_header 'x-amz-request-id';
        proxy_hide_header 'x-amz-meta-server-side-encryption';
        proxy_hide_header 'x-amz-server-side-encryption';
        proxy_hide_header 'x-amz-version-id';
    }}

    location / {{
        proxy_pass http://minio:9000/console/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header x-amz-content-sha256 "UNSIGNED-PAYLOAD";
        proxy_hide_header 'x-amz-id-2';
        proxy_hide_header 'x-amz-request-id';
        proxy_hide_header 'x-amz-meta-server-side-encryption';
        proxy_hide_header 'x-amz-server-side-encryption';
        proxy_hide_header 'x-amz-version-id';
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
