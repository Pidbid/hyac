import yaml
from dotenv import dotenv_values
import os

# Create nginx conf.d directory if it doesn't exist
os.makedirs("nginx/conf.d", exist_ok=True)

# Load environment variables from .env file
config = dotenv_values(".env")

# --- Production docker-compose.yml ---
compose_data_prod = {
    "services": {
        "mongodb": {
            "image": "bitnami/mongodb:latest",
            "container_name": "hyac_mongodb",
            "restart": "unless-stopped",
            "ports": ["27017:27017"],
            "environment": {
                "MONGODB_ROOT_USER": config.get("MONGODB_USERNAME"),
                "MONGODB_ROOT_PASSWORD": config.get("MONGODB_PASSWORD"),
                "MONGODB_REPLICA_SET_MODE": "primary",
                "MONGODB_REPLICA_SET_NAME": "rs0",
                "MONGODB_REPLICA_SET_KEY": config.get("MONGODB_PASSWORD"),
            },
            "volumes": ["mongodb_data:/bitnami/mongodb"],
            "networks": ["hyac_network"],
        },
        "minio": {
            "image": "bitnami/minio:latest",
            "container_name": "hyac_minio",
            "restart": "unless-stopped",
            "ports": ["9000:9000", "9001:9001"],
            "environment": {
                "MINIO_ROOT_USER": config.get("MINIO_ACCESS_KEY"),
                "MINIO_ROOT_PASSWORD": config.get("MINIO_SECRET_KEY"),
            },
            "volumes": ["minio_data:/data"],
            "networks": ["hyac_network"],
        },
        "nginx": {
            "image": "jonasal/nginx-certbot:latest",
            "container_name": "hyac_nginx",
            "restart": "unless-stopped",
            "environment": {"CERTBOT_EMAIL": config.get("EMAIL_ADDRESS")},
            "ports": ["80:80", "443:443"],
            "volumes": [
                "./nginx/conf.d:/etc/nginx/user_conf.d:ro",
                "./nginx/certs:/etc/letsencrypt",
            ],
            "depends_on": ["server"],
            "networks": ["hyac_network"],
        },
        "server": {
            "image": "hyac_server:latest",
            "container_name": "hyac_server",
            "restart": "unless-stopped",
            "environment": {
                "DOMAIN_NAME": config.get("DOMAIN_NAME"),
                "MONGODB_USERNAME": config.get("MONGODB_USERNAME"),
                "MONGODB_PASSWORD": config.get("MONGODB_PASSWORD"),
                "MINIO_ACCESS_KEY": config.get("MINIO_ACCESS_KEY"),
                "MINIO_SECRET_KEY": config.get("MINIO_SECRET_KEY"),
                "SECRET_KEY": config.get("SECRET_KEY"),
                "DEV_MODE": config.get("DEV_MODE"),
            },
            "ports": ["8000:8000"],
            "depends_on": ["mongodb", "minio"],
            "volumes": [
                "/var/run/docker.sock:/var/run/docker.sock",
                "./nginx/conf.d:/server/nginx/conf.d",
                "./server:/server",
            ],
            "networks": ["hyac_network"],
            "healthcheck": {
                "test": ["CMD", "python", "/healthcheck.py"],
                "interval": "5s",
                "timeout": "10s",
                "retries": 10,
                "start_period": "10s",
            },
        },
        "uploader": {
            "image": "hyac_uploader:latest",
            "container_name": "hyac_uploader",
            "environment": [
                f"MINIO_ACCESS_KEY={config.get('MINIO_ACCESS_KEY')}",
                f"MINIO_SECRET_KEY={config.get('MINIO_SECRET_KEY')}",
                f"BUILD={config.get('WEB_BUILD')}",
            ],
            "volumes": ["./web:/web"],
            "networks": ["hyac_network"],
            "depends_on": {"server": {"condition": "service_healthy"}},
            "restart": "no",
        },
    },
    "networks": {"hyac_network": {"driver": "bridge"}},
    "volumes": {
        "mongodb_data": {"driver": "local"},
        "minio_data": {"driver": "local"},
    },
}

# --- Development docker-compose.dev.yml ---
compose_data_dev = {
    "services": {
        "mongodb": compose_data_prod["services"]["mongodb"],
        "minio": compose_data_prod["services"]["minio"],
        "nginx": compose_data_prod["services"]["nginx"],
        "server": {
            "image": "hyac_server:latest",
            "container_name": "hyac_server",
            "restart": "unless-stopped",
            "environment": {
                "MONGODB_USERNAME": config.get("MONGODB_USERNAME"),
                "MONGODB_PASSWORD": config.get("MONGODB_PASSWORD"),
                "MINIO_ACCESS_KEY": config.get("MINIO_ACCESS_KEY"),
                "MINIO_SECRET_KEY": config.get("MINIO_SECRET_KEY"),
                "SECRET_KEY": config.get("SECRET_KEY"),
                "DEV_MODE": config.get("DEV_MODE"),
            },
            "ports": ["8000:8000"],
            "depends_on": ["mongodb", "minio"],
            "volumes": [
                "/var/run/docker.sock:/var/run/docker.sock",
                "./nginx/conf.d:/server/nginx/conf.d",
                "./server:/server",
            ],
            "networks": ["hyac_network"],
        },
        "lsp": {
            "image": "hyac_lsp:latest",
            "container_name": "hyac_lsp",
            "restart": "unless-stopped",
            "ports": ["8765:8765"],
            "networks": ["hyac_network"],
        },
    },
    "networks": {"hyac_network": {"driver": "bridge"}},
    "volumes": {
        "mongodb_data": {"driver": "local"},
        "minio_data": {"driver": "local"},
    },
}

# --- Nginx Configurations ---

# nginx/conf.d/server.conf
nginx_server_conf = f"""server {{
    listen 80;
    listen [::]:80;

    server_name server.{config.get('DOMAIN_NAME')};

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
"""

# nginx/conf.d/lsp.conf
nginx_lsp_conf = f"""server {{
    listen 80;
    listen [::]:80;
    server_name lsp.{config.get('DOMAIN_NAME')};

    location / {{
        proxy_pass http://lsp:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;

        # CORS configuration
        add_header 'Access-Control-Allow-Origin' 'https://console.{config.get('DOMAIN_NAME')}' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;
        add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        if ($request_method = 'OPTIONS') {{
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }}
    }}
}}
"""

# nginx/conf.d/oss.conf
nginx_oss_conf = f"""server {{
    listen 80;
    listen [::]:80;

    server_name oss.{config.get('DOMAIN_NAME')};

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
"""

# nginx/conf.d/console.conf
nginx_console_conf = f"""server {{
    listen 80;
    server_name console.{config.get('DOMAIN_NAME')};

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
"""

# --- Write Files ---

# Write docker-compose.yml
with open("docker-compose.yml", "w", encoding="utf-8") as f:
    yaml.dump(compose_data_prod, f, default_flow_style=False, sort_keys=False)
print("docker-compose.yml has been generated successfully.")

# Write docker-compose.dev.yml
with open("docker-compose.dev.yml", "w", encoding="utf-8") as f:
    yaml.dump(compose_data_dev, f, default_flow_style=False, sort_keys=False)
print("docker-compose.dev.yml has been generated successfully.")

# Write nginx/conf.d/server.conf
with open("nginx/conf.d/server.conf", "w", encoding="utf-8") as f:
    f.write(nginx_server_conf)
print("nginx/conf.d/server.conf has been generated successfully.")

# Write nginx/conf.d/lsp.conf
# with open("nginx/conf.d/lsp.conf", "w", encoding="utf-8") as f:
#     f.write(nginx_lsp_conf)
# print("nginx/conf.d/lsp.conf has been generated successfully.")

# Write nginx/conf.d/oss.conf
with open("nginx/conf.d/oss.conf", "w", encoding="utf-8") as f:
    f.write(nginx_oss_conf)
print("nginx/conf.d/oss.conf has been generated successfully.")

# Write nginx/conf.d/console.conf
with open("nginx/conf.d/console.conf", "w", encoding="utf-8") as f:
    f.write(nginx_console_conf)
print("nginx/conf.d/console.conf has been generated successfully.")
