import httpx
from loguru import logger
from core.config import settings
from models.applications_model import Application


async def run_function(app_id: str, function_id: str, params: dict, body: dict):
    """
    Triggers a cloud function by sending an HTTP POST request to its endpoint.
    """
    try:
        app = await Application.find_one(Application.app_id == app_id)
        if not app:
            logger.error(
                f"Application with app_id {app_id} not found. Cannot run function {function_id}."
            )
            return

        # Construct the internal URL for the function
        # The request goes to the nginx proxy, which routes it to the correct app container.
        url = f"http://hyac-app-runtime-{app_id.lower()}:8001/{function_id}"

        headers = {
            "Content-Type": "application/json",
            # In the future, we might need an internal auth key for service-to-service calls
            # "X-Internal-Auth-Key": settings.INTERNAL_AUTH_KEY
        }

        async with httpx.AsyncClient() as client:
            logger.info(
                f"Sending scheduled request to function: {url} with params={params}"
            )
            response = await client.post(
                url, params=params, json=body, headers=headers, timeout=30.0
            )

            if response.status_code >= 400:
                logger.error(
                    f"Scheduled function call to {url} failed with status {response.status_code}: {response.text}"
                )
            else:
                logger.success(
                    f"Scheduled function call to {url} completed with status {response.status_code}."
                )

    except httpx.RequestError as e:
        logger.error(f"HTTP request failed when calling scheduled function {url}: {e}")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in run_function for {url}: {e}",
            exc_info=True,
        )
