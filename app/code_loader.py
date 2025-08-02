# app/code_loader.py
import inspect
from typing import Optional, Tuple
from loguru import logger
from types import SimpleNamespace

from core.cache import code_cache
from core.faas_minio import minio_open
from models.functions_model import Function, FunctionStatus, FunctionType


class CodeLoader:
    """
    Handles loading, compiling, and caching of serverless function code.
    """

    async def load_function_by_ids(
        self, app_id: str, function_id: str
    ) -> Optional[Tuple[dict, Function, Optional[inspect.Signature]]]:
        """
        Loads a function by its application ID and function ID.
        It first checks the cache, and if not found, queries the database,
        compiles the code, and caches the result.
        Returns a tuple of (compiled_code, function_document, signature).
        """
        cache_key = code_cache._make_key(app_id, function_id)

        # Attempt to retrieve from cache first.
        if cached_data := code_cache.get(cache_key):
            return cached_data

        # If not in cache, query the database.
        func_doc = await Function.find_one(
            Function.app_id == app_id,
            Function.function_id == function_id,
            Function.status == FunctionStatus.PUBLISHED,
            Function.function_type == FunctionType.ENDPOINT,
        )
        if not func_doc:
            return None

        # Compile the code and get its signature.
        compiled_code, signature = self._compile_code(func_doc.code, cache_key)

        # Cache the compiled code, the function document, and the signature.
        data_to_cache = (compiled_code, func_doc, signature)
        code_cache.set(cache_key, data_to_cache)
        return data_to_cache

    async def load_common_function_by_name(
        self, app_id: str, function_name: str
    ) -> Optional[dict]:
        """
        Loads a common function by its application ID and function name.
        It checks the cache first, and if not found, queries the database,
        compiles the code, and caches the result.
        """
        cache_key = code_cache._make_key(app_id, function_name, "common")

        # Attempt to retrieve from cache first.
        if cached_code := code_cache.get(cache_key):
            return cached_code

        # If not in cache, query the database for a common function.
        func = await Function.find_one(
            Function.app_id == app_id,
            Function.function_name == function_name,
            Function.status == FunctionStatus.PUBLISHED,
            Function.function_type == FunctionType.COMMON,
        )
        if not func:
            return None

        # Compile the code.
        compiled, _ = self._compile_code(func.code, cache_key)

        # Cache the compiled code and return.
        code_cache.set(cache_key, compiled)
        return compiled

    def _compile_code(
        self, code: str, module_key: str
    ) -> Tuple[dict, Optional[inspect.Signature]]:
        """
        Compiles code into a namespace and extracts the handler's signature.
        Injects custom functions like 'minio_open' into the execution namespace.
        Returns the namespace and the signature of the 'handler' function, if it exists.
        """
        try:
            # Use an independent namespace and inject custom functions.
            namespace = {
                "minio_open": minio_open,
            }
            exec(code, namespace)
            handler_func = namespace.get("handler")
            signature = (
                inspect.signature(handler_func) if callable(handler_func) else None
            )
            return namespace, signature
        except Exception as e:
            raise RuntimeError(
                f"Code compilation failed for module '{module_key}': {e}"
            )

    async def load_all_common_functions(self, app_id: str) -> SimpleNamespace:
        """
        Loads all common functions for a given application.
        It returns a dictionary where keys are function_names and values are the compiled modules (namespaces).
        """
        common_namespaces = {}
        # Find all published common functions for the app.
        func_cursor = Function.find(
            Function.app_id == app_id,
            Function.status == FunctionStatus.PUBLISHED,
            Function.function_type == FunctionType.COMMON,
        )

        async for func in func_cursor:
            cache_key = code_cache._make_key(app_id, func.function_name, "common")

            # Try to get from cache first
            if cached_module := code_cache.get(cache_key):
                # Convert dict to namespace for attribute access
                common_namespaces[func.function_name] = SimpleNamespace(**cached_module)
                continue

            # If not in cache, compile and cache it
            try:
                # Common functions do not need signature inspection.
                compiled_namespace, _ = self._compile_code(func.code, cache_key)
                code_cache.set(cache_key, compiled_namespace)
                # Convert dict to namespace for attribute access
                common_namespaces[func.function_name] = SimpleNamespace(
                    **compiled_namespace
                )
            except Exception as e:
                # Log the error but don't block other functions from loading
                logger.error(
                    f"Failed to compile common function {func.function_name} for app {app_id}: {e}"
                )

        # Return a namespace containing all common function namespaces
        return SimpleNamespace(**common_namespaces)
