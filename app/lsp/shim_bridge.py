import json
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

from lsp.shim import PRELOAD_CONTENT_HEADER, USER_CODE_START_MARKER, USER_CODE_END_MARKER

_SHIM_HEADER_WITH_MARKERS = (
    PRELOAD_CONTENT_HEADER
    + "\n"
    + USER_CODE_START_MARKER
    + "\n"
)


class ShimBridge:
    """
    Stateful message bridge for per-session shim and URI mapping.
    """

    def __init__(self, virtual_workspace: str = "/app/.hyac_lsp"):
        self.virtual_workspace = virtual_workspace.rstrip("/")
        self._uri_forward: dict[str, str] = {}
        self._uri_reverse: dict[str, str] = {}
        self._shim_line_count: int = 0

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
        self._adjust_position_outbound(transformed)
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
        self._adjust_diagnostics(transformed)
        self._adjust_completion_response(transformed)
        self._adjust_formatting_response(transformed)
        return json.dumps(transformed)

    def _safe_load(self, message: str) -> dict[str, Any] | list[Any] | None:
        try:
            return json.loads(message)
        except json.JSONDecodeError:
            return None

    def _strip_shim(self, text: str) -> str:
        """Remove shim header and markers if already present (idempotent)."""
        # Try full header+start-marker prefix
        if text.startswith(_SHIM_HEADER_WITH_MARKERS):
            text = text[len(_SHIM_HEADER_WITH_MARKERS):]
            end_idx = text.find(USER_CODE_END_MARKER)
            if end_idx != -1:
                text = text[:end_idx]
            return text.lstrip("\n")
        # Try just the start marker
        if text.startswith(USER_CODE_START_MARKER):
            text = text[len(USER_CODE_START_MARKER):]
            end_idx = text.find(USER_CODE_END_MARKER)
            if end_idx != -1:
                text = text[:end_idx]
            return text.lstrip("\n")
        return text

    def _inject_shim(self, payload: dict[str, Any] | list[Any]) -> None:
        if not isinstance(payload, dict):
            return

        method = payload.get("method")
        if method not in ("textDocument/didOpen", "textDocument/didChange"):
            return

        params = payload.get("params")
        if not isinstance(params, dict):
            return

        text_document = params.get("textDocument")
        if not isinstance(text_document, dict):
            return

        # Handle didOpen
        if method == "textDocument/didOpen" and "text" in text_document:
            original_text = self._strip_shim(text_document["text"])
            shimmed_text = (
                _SHIM_HEADER_WITH_MARKERS
                + original_text
                + "\n"
                + USER_CODE_END_MARKER
            )
            text_document["text"] = shimmed_text
            self._shim_line_count = _SHIM_HEADER_WITH_MARKERS.count("\n")
            return

        # Handle didChange
        if method == "textDocument/didChange":
            content_changes = params.get("contentChanges")
            if not isinstance(content_changes, list):
                return
            for change in content_changes:
                if isinstance(change, dict) and "text" in change:
                    original_text = self._strip_shim(change["text"])
                    shimmed_text = (
                        _SHIM_HEADER_WITH_MARKERS
                        + original_text
                        + "\n"
                        + USER_CODE_END_MARKER
                    )
                    change["text"] = shimmed_text
                    self._shim_line_count = _SHIM_HEADER_WITH_MARKERS.count("\n")
                    break

    def _adjust_position_outbound(self, payload: dict[str, Any] | list[Any]) -> None:
        """Adjust position in requests to account for the shim header."""
        if not isinstance(payload, dict):
            return

        method = payload.get("method", "")
        # Only adjust position-based requests
        position_methods = (
            "textDocument/completion",
            "textDocument/hover",
            "textDocument/signatureHelp",
            "textDocument/references",
            "textDocument/definition",
            "textDocument/documentHighlight",
            "textDocument/rename",
            "textDocument/prepareRename",
            "textDocument/codeAction",
            "textDocument/formatting",
            "textDocument/rangeFormatting",
        )
        if method not in position_methods:
            return

        params = payload.get("params")
        if not isinstance(params, dict):
            return

        shim_offset = self._shim_line_count
        if shim_offset == 0:
            return

        position = params.get("position")
        if isinstance(position, dict) and "line" in position:
            position["line"] = position["line"] + shim_offset

    def _adjust_diagnostics(self, payload: dict[str, Any] | list[Any]) -> None:
        if not isinstance(payload, dict):
            return

        method = payload.get("method")
        if method != "textDocument/publishDiagnostics":
            return

        params = payload.get("params")
        if not isinstance(params, dict):
            return

        diagnostics = params.get("diagnostics")
        if not isinstance(diagnostics, list):
            return

        # Calculate the line offset for user code
        # PRELOAD_CONTENT_HEADER starts with \n, so +1 for that leading empty line
        # Then +1 for the USER_CODE_START_MARKER line
        shim_line_count = self._shim_line_count
        if shim_line_count == 0:
            shim_line_count = _SHIM_HEADER_WITH_MARKERS.count("\n")

        adjusted_diagnostics = []
        for diag in diagnostics:
            if not isinstance(diag, dict):
                continue

            range_obj = diag.get("range")
            if not isinstance(range_obj, dict):
                continue

            start = range_obj.get("start")
            end = range_obj.get("end")

            if isinstance(start, dict) and "line" in start:
                start_line = start["line"] - shim_line_count
                if start_line < 0:
                    continue
                start["line"] = start_line

            if isinstance(end, dict) and "line" in end:
                end_line = end["line"] - shim_line_count
                if end_line < 0:
                    continue
                end["line"] = end_line

            adjusted_diagnostics.append(diag)

        params["diagnostics"] = adjusted_diagnostics

    def _adjust_completion_response(self, payload: dict[str, Any] | list[Any]) -> None:
        """Adjust line numbers in completion response items back to original coordinates."""
        if not isinstance(payload, dict):
            return

        # Only process responses (has "result" and an "id")
        if "id" not in payload or "result" not in payload:
            return

        result = payload.get("result")
        if not isinstance(result, (dict, list)):
            return

        shim_offset = self._shim_line_count
        if shim_offset == 0:
            return

        items: list[dict] = []
        if isinstance(result, list):
            items = [item for item in result if isinstance(item, dict)]
        elif isinstance(result, dict):
            raw_items = result.get("items")
            if isinstance(raw_items, list):
                items = [item for item in raw_items if isinstance(item, dict)]

        for item in items:
            # Adjust textEdit.range
            text_edit = item.get("textEdit")
            if isinstance(text_edit, dict):
                range_obj = text_edit.get("range")
                if isinstance(range_obj, dict):
                    self._offset_range_lines(range_obj, -shim_offset)

            # Adjust additionalTextEdits ranges
            additional_edits = item.get("additionalTextEdits")
            if isinstance(additional_edits, list):
                for edit in additional_edits:
                    if isinstance(edit, dict):
                        range_obj = edit.get("range")
                        if isinstance(range_obj, dict):
                            self._offset_range_lines(range_obj, -shim_offset)

    def _adjust_formatting_response(self, payload: dict[str, Any] | list[Any]) -> None:
        """Extract user code from formatting response and adjust ranges to client coordinates."""
        if not isinstance(payload, dict):
            return

        if "id" not in payload or "result" not in payload:
            return

        result = payload.get("result")
        if not isinstance(result, list):
            return

        shim_offset = self._shim_line_count
        if shim_offset == 0:
            shim_offset = _SHIM_HEADER_WITH_MARKERS.count("\n")

        for item in result:
            if not isinstance(item, dict):
                continue
            new_text = item.get("newText")
            if not isinstance(new_text, str):
                continue

            # Try to extract user code between markers
            start_idx = new_text.find(USER_CODE_START_MARKER)
            end_idx = new_text.find(USER_CODE_END_MARKER)
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                user_code = new_text[
                    start_idx + len(USER_CODE_START_MARKER) :
                    end_idx
                ]
                user_code = user_code.lstrip("\n")
                item["newText"] = user_code
            elif _SHIM_HEADER_WITH_MARKERS in new_text:
                # Markers may have been altered, but shim header is present
                stripped = self._strip_shim(new_text)
                item["newText"] = stripped
                user_code = stripped
            else:
                # No shim detected, skip
                continue

            # Adjust range to client coordinates
            range_obj = item.get("range")
            if isinstance(range_obj, dict):
                start = range_obj.get("start")
                end = range_obj.get("end")
                if isinstance(start, dict) and "line" in start:
                    start["line"] = max(0, start["line"] - shim_offset)
                if isinstance(end, dict) and "line" in end:
                    user_code_lines = user_code.count("\n") + 1
                    if isinstance(start, dict):
                        end["line"] = max(0, start["line"] + user_code_lines - 1)
                    else:
                        end["line"] = max(0, end["line"] - shim_offset)

    def _offset_range_lines(self, range_obj: dict[str, Any], offset: int) -> None:
        """Offset line numbers in a LSP range object."""
        start = range_obj.get("start")
        end = range_obj.get("end")
        if isinstance(start, dict) and "line" in start:
            start["line"] = max(0, start["line"] + offset)
        if isinstance(end, dict) and "line" in end:
            end["line"] = max(0, end["line"] + offset)

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
