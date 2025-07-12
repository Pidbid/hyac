import asyncio
import httpx
from pydantic import BaseModel


class PackageInfoModel(BaseModel):
    name: str
    author: str | None = None
    description: str = ""
    description_type: str = "text/markdown"
    versions: list[str] = []


class DependenceManager:
    def __init__(self):
        self.url = "https://pypi.org"
        self.client = httpx.AsyncClient(timeout=10.0)

    async def _check_package_exists(self, name: str) -> str | None:
        """Check if a package exists on PyPI using a HEAD request."""
        try:
            # Use HEAD request for efficiency as we only need the status code
            response = await self.client.head(f"{self.url}/pypi/{name}/json")
            if response.status_code == 200:
                return name
        except httpx.RequestError:
            return None
        return None

    async def package_search(self, name: str) -> list[str]:
        """
        Suggests package names by checking for existence of common variations.
        This is not a real search, but a validation/suggestion mechanism.
        """
        if not name:
            return []

        # Create a set of candidate names to check for common naming conventions
        name = name.lower()
        candidates = {name}
        if "-" in name:
            candidates.add(name.replace("-", "_"))
        if "_" in name:
            candidates.add(name.replace("_", "-"))

        # Asynchronously check for the existence of all candidates
        tasks = [self._check_package_exists(candidate) for candidate in candidates]
        results = await asyncio.gather(*tasks)

        # Return a list of valid, non-None package names
        return sorted([res for res in results if res])

    async def package_info(self, name: str) -> dict:
        """Fetches detailed information for a single package."""
        try:
            response = await self.client.get(f"{self.url}/pypi/{name}/json")
            response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes

            pkg_json = response.json()
            info = pkg_json.get("info", {})
            releases = pkg_json.get("releases", {})

            # Sort versions using a robust method if possible, otherwise reverse chronological
            try:
                from packaging.version import parse as parse_version

                sorted_versions = sorted(
                    releases.keys(), key=parse_version, reverse=True
                )
            except ImportError:
                sorted_versions = sorted(releases.keys(), reverse=True)

            return {
                "name": info.get("name", name),
                "author": info.get("author"),
                "description": info.get("description", ""),
                "description_type": info.get(
                    "description_content_type", "text/markdown"
                ),
                "versions": sorted_versions,
            }
        except (httpx.RequestError, httpx.HTTPStatusError):
            return {}

    async def package_add(self, appid: str, name: str, version: str):
        # This method seems to be a placeholder, keeping it as is.
        return


dependence_manager = DependenceManager()
