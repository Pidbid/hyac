import httpx
import os
import re
from loguru import logger
from dotenv import dotenv_values
from core.config import settings
from core.docker_manager import docker_manager


class UpdateManager:
    GITHUB_REPO = "pidbid/hyac"

    def get_current_versions(self) -> dict:
        """
        Retrieves the current versions of all services from environment variables.
        """
        return {
            "server_version": settings.SERVER_IMAGE_TAG,
            "web_version": settings.WEB_IMAGE_TAG,
            "app_version": settings.APP_IMAGE_TAG,
        }

    async def get_changelogs(self) -> list[dict] | None:
        """
        Fetches all release information from the GitHub repository.
        """
        url = f"https://api.github.com/repos/{self.GITHUB_REPO}/releases"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                releases = response.json()
                if not releases:
                    return []

                changelogs = [
                    {
                        "version": r["tag_name"],
                        "changelog": r["body"],
                        "published_at": r["published_at"],
                    }
                    for r in releases
                ]
                return changelogs
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch changelogs from GitHub: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching changelogs: {e}")
            return None


update_manager = UpdateManager()
