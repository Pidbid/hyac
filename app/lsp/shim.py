"""
This module defines the content shim and markers used to provide a proper
execution context for user code within the Language Server Protocol (LSP) proxy.

The shim injects necessary imports and context variables, allowing pylsp to
provide accurate autocompletion and diagnostics for FaaS functions.
"""

# The "shim" content that provides the execution context for user code.
# It includes necessary imports and type hints for pylsp to understand the environment.
PRELOAD_CONTENT_HEADER = """
# fmt:off
# --- Lsp shim for user code execution ---
from context import FunctionContext
from core.faas_minio import minio_open

context: FunctionContext
# fmt:on
"""

# Markers to wrap user code. This allows for safe extraction of user code
# from formatted responses, preventing the shim from leaking into the editor.
USER_CODE_START_MARKER = "# --- HYAC USER CODE START ---"
USER_CODE_END_MARKER = "# --- HYAC USER CODE END ---"
