import json
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any


class ShimBridge:
    """
    Stateful message bridge for per-session shim and URI mapping.
    """

    def __init__(self, virtual_workspace: str = "/app/.hyac_lsp"):
        self.virtual_workspace = virtual_workspace.rstrip("/")
        self._uri_forward: dict[str, str] = {}
        self._uri_reverse: dict[str, str] = {}

    def outbound(self, message: str) -> str:
        """
        Client -> sidecar:
        - map in-memory URIs to file URIs
        """
        payload = self._safe_load(message)
        if payload is None:
            return message

        transformed = deepcopy(payload)
        self._map_all_uris(transformed, reverse=False)
        self._rewrite_workspace_fields(transformed, reverse=False)
        self._inject_shim(transformed)
        return json.dumps(transformed)

    def inbound(self, message: str) -> str:
        """
        Sidecar -> client:
        - map file URIs back to original client URIs
        """
        payload = self._safe_load(message)
        if payload is None:
            return message

        transformed = deepcopy(payload)
        self._map_all_uris(transformed, reverse=True)
        self._rewrite_workspace_fields(transformed, reverse=True)
        return json.dumps(transformed)

    def _safe_load(self, message: str) -> dict[str, Any] | list[Any] | None:
        try:
            return json.loads(message)
        except json.JSONDecodeError:
            return None

    def _inject_shim(self, payload: dict[str, Any] | list[Any]) -> None:
        # Keep as no-op to preserve call sites and future extensibility.
        return

    def _rewrite_workspace_fields(
        self, payload: dict[str, Any] | list[Any], reverse: bool
    ) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("method") != "initialize":
            return
        params = payload.get("params")
        if not isinstance(params, dict):
            return

        if reverse:
            params["rootUri"] = "inmemory:///tmp"
            params["rootPath"] = "/tmp"
            if isinstance(params.get("workspaceFolders"), list):
                for folder in params["workspaceFolders"]:
                    if isinstance(folder, dict):
                        folder["uri"] = "inmemory:///tmp"
                        folder["name"] = "tmp"
            return

        workspace_uri = self._to_file_uri(self.virtual_workspace)
        params["rootUri"] = workspace_uri
        params["rootPath"] = self.virtual_workspace
        if isinstance(params.get("workspaceFolders"), list):
            for folder in params["workspaceFolders"]:
                if isinstance(folder, dict):
                    folder["uri"] = workspace_uri
                    folder["name"] = PurePosixPath(self.virtual_workspace).name or "workspace"

    def _map_all_uris(
        self, value: dict[str, Any] | list[Any] | str | int | float | bool | None, reverse: bool
    ) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "uri" and isinstance(item, str):
                    value[key] = self._map_uri(item, reverse=reverse)
                else:
                    self._map_all_uris(item, reverse=reverse)
            return
        if isinstance(value, list):
            for item in value:
                self._map_all_uris(item, reverse=reverse)

    def _map_uri(self, uri: str, reverse: bool) -> str:
        if reverse:
            return self._uri_reverse.get(uri, uri)

        if uri in self._uri_forward:
            return self._uri_forward[uri]

        if not uri.startswith("inmemory:///tmp/"):
            return uri

        tail = uri.removeprefix("inmemory:///tmp/").lstrip("/")
        mapped = self._to_file_uri(f"{self.virtual_workspace}/{tail}")
        self._uri_forward[uri] = mapped
        self._uri_reverse[mapped] = uri
        return mapped

    def _to_file_uri(self, path: str) -> str:
        clean = path if path.startswith("/") else f"/{path}"
        return f"file://{clean}"
