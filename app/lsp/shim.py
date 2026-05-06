"""
This module defines the content shim and markers used to provide a proper
execution context for user code within the Language Server Protocol (LSP) proxy.

The shim injects necessary imports and context variables, allowing the LSP server
to provide accurate autocompletion and diagnostics for FaaS functions.
"""

PRELOAD_CONTENT_HEADER = """
# fmt:off
# --- Lsp shim for user code execution ---
from context import FunctionContext
from core.faas_s3 import s3_open

context: FunctionContext
# fmt:on
"""

USER_CODE_START_MARKER = "# --- HYAC USER CODE START ---"
USER_CODE_END_MARKER = "# --- HYAC USER CODE END ---"
