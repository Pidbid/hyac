import httpx
from fastapi import APIRouter, Request, Response
from loguru import logger

from core.config import settings
from core.docker_manager import start_app_container
from models.applications_model import Application

router = APIRouter()

# A client that can make requests to other services
http_client = httpx.AsyncClient()


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def reverse_proxy(request: Request, path: str):
    """
    This is a catch-all route that acts as a reverse proxy for the first request to an app.
    It starts the app container, creates the Nginx config, and proxies the initial request.
    Subsequent requests will be handled directly by Nginx.
    """
    host = request.headers.get("host", "").split(":")[0]
    base_domain = settings.DOMAIN_NAME or "localhost"

    # This router should only handle subdomain requests that haven't been matched yet.
    if not host.endswith(base_domain) or host == base_domain:
        # If it's the base domain, it means no API route was matched.
        return Response(status_code=404, content=f"Not Found: No API route or application found for {host}/{path}")

    # It's a request for a subdomain, i.e., a function app
    app_id = host.replace(f".{base_domain}", "")
    logger.info(f"First request for app '{app_id}'. Initiating runtime environment...")

    # Find the application document
    app = await Application.find_one(Application.app_id == app_id)
    if not app:
        return Response(status_code=404, content=f"Application '{app_id}' not found.")

    # Ensure the container for this app is running
    container_info = await start_app_container(app)
    if not container_info:
        return Response(status_code=502, content=f"Failed to start execution environment for app '{app_id}'.")

    # Proxy the current (first) request to the newly started app container
    container_name = container_info["name"]
    target_url = f"http://{container_name}:8001/{path}"
    
    headers = dict(request.headers)
    headers["host"] = host # Keep the original host for the app container
    
    content = await request.body()
    
    try:
        logger.info(f"Proxying initial request to {target_url}")
        proxied_response = await http_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=request.query_params,
            content=content,
            timeout=60.0,
        )
        
        return Response(
            content=proxied_response.content,
            status_code=proxied_response.status_code,
            headers=dict(proxied_response.headers),
        )
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy initial request to {target_url}: {e}")
        return Response(status_code=502, content="Bad Gateway: Could not contact newly started service.")
