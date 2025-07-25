import httpx
import os
import re
import subprocess
from loguru import logger
from core.config import settings


class UpdateManager:
    GITHUB_REPO = "pidbid/hyac"
    # A regex to validate Docker image tags. It allows for alphanumeric characters,
    # underscores, periods, and hyphens. This is a security measure to prevent
    # command injection.
    TAG_VALIDATION_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+$")

    def get_current_version(self) -> dict:
        """
        Retrieves the current versions of server and web from environment variables.
        """
        return {
            "server_version": settings.SERVER_IMAGE_TAG,
            "web_version": settings.WEB_IMAGE_TAG,
        }

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
        update_available = latest_info["version"] != current_versions.get(
            "server_version"
        )

        return {
            "update_available": update_available,
            "current_versions": current_versions,
            "latest_version_info": latest_info,
        }

    def run_update_script(self, tags: dict[str, str] | None = None):
        """
        Executes the system update script in a separate process.
        """
        env = os.environ.copy()
        services_to_update = []

        if not tags:
            # Default update behavior
            services_to_update = ["server", "web", "lsp", "app"]
        else:
            # Manual update behavior
            tag_map = {
                "server": "SERVER_IMAGE_TAG",
                "app": "APP_IMAGE_TAG",
                "lsp": "LSP_IMAGE_TAG",
                "web": "WEB_IMAGE_TAG",
            }

            for service, tag in tags.items():
                if tag:
                    # Security: Validate tag format to prevent command injection
                    if not self.TAG_VALIDATION_REGEX.match(tag):
                        logger.error(
                            f"Invalid tag format for service '{service}': {tag}"
                        )
                        continue
                    env[tag_map[service]] = tag
                    services_to_update.append(service)

        if not services_to_update:
            logger.info(
                "Update called but no valid services/tags provided. Nothing to do."
            )
            return

        service_list = " ".join(services_to_update)
        command = f"docker-compose pull {service_list} && docker-compose up -d --remove-orphans {service_list}"

        try:
            logger.info(f"Executing update command: {command}")
            subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            logger.info("System update process has been initiated successfully.")
        except FileNotFoundError:
            logger.error("`docker-compose` command not found.")
        except Exception as e:
            logger.error(f"Failed to start the update process: {e}")


update_manager = UpdateManager()
