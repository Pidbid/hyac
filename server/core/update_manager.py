import httpx
import os
import re
from loguru import logger
from dotenv import dotenv_values
from core.config import settings
from core.docker_manager import docker_manager


class UpdateManager:
    GITHUB_REPO = "pidbid/hyac"
    VERSION_FILE_PATH = "/app/version.env"
    # A regex to validate Docker image tags. It allows for alphanumeric characters,
    # underscores, periods, and hyphens. This is a security measure to prevent
    # command injection.
    TAG_VALIDATION_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+$")

    def get_current_version(self) -> dict:
        """
        Retrieves the current versions of all services from the version.env file.
        """
        try:
            versions = dotenv_values(self.VERSION_FILE_PATH)
            return {
                "server_version": versions.get("SERVER_IMAGE_TAG"),
                "web_version": versions.get("WEB_IMAGE_TAG"),
                "app_version": versions.get("APP_IMAGE_TAG"),
                "lsp_version": versions.get("LSP_IMAGE_TAG"),
            }
        except Exception as e:
            logger.error(f"Failed to read version file: {e}")
            return {}

    async def get_latest_version_info(self, proxy: str | None = None) -> dict | None:
        """
        Fetches the all releases information from the GitHub repository.
        """
        url = f"https://api.github.com/repos/{self.GITHUB_REPO}/releases"
        try:
            async with httpx.AsyncClient(proxy=proxy) as client:
                response = await client.get(url)
                response.raise_for_status()
                releases = response.json()
                if not releases:
                    return None

                latest_release = releases[0]
                return {
                    "version": latest_release["tag_name"],
                    "changelog": latest_release["body"],
                    "published_at": latest_release["published_at"],
                }
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch latest version from GitHub: {e}")
            return None
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while fetching version info: {e}"
            )
            return None

    async def get_changelogs(self, proxy: str | None = None) -> list[dict] | None:
        """
        Fetches all release information from the GitHub repository.
        """
        url = f"https://api.github.com/repos/{self.GITHUB_REPO}/releases"
        try:
            async with httpx.AsyncClient(proxy=proxy) as client:
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

    async def check_for_updates(self, proxy: str | None = None) -> dict:
        """
        Compares current version with the latest version and returns update status.
        """
        current_versions = self.get_current_version()
        latest_info = await self.get_latest_version_info(proxy=proxy)

        if not latest_info:
            return {
                "update_available": False,
                "message": "Could not check for updates. Please try again later.",
                "current_versions": current_versions,
            }

        # A simple version comparison. Assumes tags are comparable.
        # For more robust comparison, consider using packaging.version.
        # Compare with server_version as a reference for the overall system version
        update_available = latest_info["version"] != current_versions.get(
            "server_version"
        )

        return {
            "update_available": update_available,
            "current_versions": current_versions,
            "latest_version_info": latest_info,
        }

    def _update_version_file(self, tags: dict[str, str]):
        """
        Updates the version.env file with new tags.
        """
        try:
            if os.path.exists(self.VERSION_FILE_PATH):
                current_versions = dotenv_values(self.VERSION_FILE_PATH)
            else:
                current_versions = {}

            tag_map = {
                "server": "SERVER_IMAGE_TAG",
                "app": "APP_IMAGE_TAG",
                "lsp": "LSP_IMAGE_TAG",
                "web": "WEB_IMAGE_TAG",
            }

            for service, tag in tags.items():
                if tag and service in tag_map:
                    current_versions[tag_map[service]] = tag

            with open(self.VERSION_FILE_PATH, "w") as f:
                for key, value in current_versions.items():
                    f.write(f"{key}={value}\n")
            logger.info("Version file updated successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to update version file: {e}")
            return False

    async def run_update_script_async(self, tags: dict[str, str] | None = None):
        """
        Asynchronous version of run_update_script to be called from async context.
        """
        services_to_update = []
        tags_to_apply = {}

        if not tags or not any(tags.values()):
            logger.info("Auto-update triggered. Fetching latest version info...")
            latest_info = await self.get_latest_version_info()
            if latest_info and "version" in latest_info:
                latest_tag = latest_info["version"]
                logger.info(
                    f"Latest version found: {latest_tag}. Applying to all services."
                )
                tags_to_apply = {
                    "server": latest_tag,
                    "web": latest_tag,
                    "app": latest_tag,
                    "lsp": latest_tag,
                }
                services_to_update = ["server", "web", "app", "lsp"]
            else:
                logger.error("Could not fetch latest version for auto-update.")
                return
        else:
            for service, tag in tags.items():
                if tag:
                    if not self.TAG_VALIDATION_REGEX.match(tag):
                        logger.error(
                            f"Invalid tag format for service '{service}': {tag}"
                        )
                        continue
                    tags_to_apply[service] = tag
                    services_to_update.append(service)

        if not services_to_update:
            logger.info(
                "Update called but no valid services/tags provided. Nothing to do."
            )
            return

        if not self._update_version_file(tags_to_apply):
            logger.error("Update aborted due to failure in updating version file.")
            return

        logger.info(f"Starting update for services: {services_to_update}")

        for service in services_to_update:
            tag = tags_to_apply.get(service)
            if not tag:
                continue

            logger.info(f"Updating service '{service}' to tag '{tag}'...")
            success = await docker_manager.recreate_service(
                service_name=service, new_image_tag=tag
            )

            if success:
                logger.info(f"Service '{service}' updated successfully.")
            else:
                logger.error(
                    f"Failed to update service '{service}'. "
                    "Please check the logs for more details. "
                    "You may need to manually intervene."
                )

        logger.info("System update process completed.")

    def run_update_script(self, tags: dict[str, str] | None = None):
        """
        Wraps the async update runner for background tasks.
        """
        import asyncio

        asyncio.run(self.run_update_script_async(tags=tags))


update_manager = UpdateManager()
