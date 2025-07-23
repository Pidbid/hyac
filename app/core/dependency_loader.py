# app/core/dependency_loader.py
import asyncio
import importlib
import sys
from typing import List
import os

from loguru import logger

from models.applications_model import Application, Dependency


class DependencyLoader:
    """
    Manages the dynamic installation of dependencies for applications.
    """

    @staticmethod
    async def install_dependencies(dependencies: List[Dependency]):
        """
        Dynamically installs Python packages using uv.

        Args:
            dependencies: A list of dictionaries, where each dictionary
                          represents a package and its version.
                          e.g., [{'name': 'package_name', 'version': '1.0.0'}]
        """
        for p in dependencies:
            package = p.name
            version = p.version
            # Check if the module is already loaded.
            if package in sys.modules:
                logger.info(
                    f"Dependency {package} already loaded, skipping installation."
                )
                continue

            try:
                package_and_version = (
                    f"{package}=={version}" if version != "latest" else package
                )
                # Using uv for installation
                install_command = [
                    "uv",
                    "pip",
                    "install",
                    "--system",
                    package_and_version,
                ]
                logger.info(f"Installing dependency: {' '.join(install_command)}")

                process = await asyncio.create_subprocess_exec(
                    *install_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_message = stderr.decode().strip()
                    logger.error(
                        f"Failed to install {package_and_version}: {error_message}"
                    )
                    raise RuntimeError(f"Failed to install dependency: {package}")
                else:
                    logger.info(f"Successfully installed {package_and_version}")
                    # Invalidate caches and try to import the newly installed package.
                    importlib.invalidate_caches()
            except Exception as e:
                logger.error(f"Error installing or importing {package}: {e}")
                raise


async def install_app_dependencies():
    """
    Installs common dependencies for the current application instance.
    The APP_ID should be provided as an environment variable.
    """
    app_id = os.getenv("APP_ID")
    if not app_id:
        logger.warning(
            "APP_ID environment variable not set. Skipping dependency installation."
        )
        return

    logger.info(f"Fetching dependencies for app: {app_id}")
    # It's important to handle the case where the application might not be found
    try:
        app = await Application.find_one(Application.app_id == app_id)
        if app and app.common_dependencies:
            logger.info(f"Installing dependencies for application '{app.app_name}'...")
            await DependencyLoader.install_dependencies(app.common_dependencies)
            logger.info(f"Dependencies for application '{app.app_name}' installed.")
        elif app:
            logger.info(
                f"No common dependencies found for application '{app.app_name}'."
            )
        else:
            logger.warning(f"Application with ID '{app_id}' not found in the database.")
    except Exception as e:
        logger.error(
            f"An error occurred while fetching or installing dependencies for app '{app_id}': {e}"
        )
