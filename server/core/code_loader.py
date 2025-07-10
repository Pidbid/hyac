# services/code_loader.py
from typing import Optional

from core.cache import code_cache
from core.faas_minio import minio_open
from models.applications_model import Application
from models.functions_model import Function, FunctionStatus, FunctionType


class CodeLoader:
    """
    Handles loading, compiling, and caching of serverless function code.
    """

    @staticmethod
    def _generate_module_key(app_id: str, function_id: str) -> str:
        """
        Generates a unique key for a function module.
        """
        return f"{app_id}::{function_id}"

    async def load_function_by_name(
        self, app_id: str, function_id: str
    ) -> Optional[dict]:
        """
        Loads a function by its application name and function ID.
        It first checks the cache, and if not found, queries the database,
        compiles the code, and caches the result.
        """
        cache_key = code_cache._make_key(app_id, function_id)

        # Attempt to retrieve from cache first.
        if cached_code := code_cache.get(cache_key):
            return cached_code

        # If not in cache, query the database.
        func = await Function.find_one(
            Function.app_id == app_id,
            Function.function_id == function_id,
            Function.status == FunctionStatus.PUBLISHED,
            Function.function_type == FunctionType.ENDPOINT,
        )
        if not func:
            return None

        # Compile the code.
        compiled = self._compile_code(func.code, cache_key)

        # Cache the compiled code and return.
        code_cache.set(cache_key, compiled)
        return compiled

    async def load_function_by_ids(
        self, app_id: str, function_id: str
    ) -> Optional[dict]:
        """
        Loads a function by application ID and function ID.
        This method first resolves the application name from the app_id.
        """
        # First, find the app_id from the app_id.
        app = await Application.find_one(Application.app_id == app_id)
        if not app:
            return None

        # Then, find the function document using the app_id and function_id.
        func_doc = await Function.find_one(
            Function.app_id == app.app_id,
            Function.function_id == function_id,
            Function.status == FunctionStatus.PUBLISHED,
            Function.function_type == FunctionType.ENDPOINT,
        )
        if not func_doc:
            return None

        # Call load_function_by_name with the resolved names.
        return await self.load_function_by_name(app.app_id, func_doc.function_id)

    async def load_common_function(
        self, app_id: str, function_id: str
    ) -> Optional[dict]:
        """
        Loads a common function by its application ID and function ID.
        It checks the cache first, and if not found, queries the database,
        compiles the code, and caches the result.
        """
        cache_key = code_cache._make_key(app_id, function_id, "common")

        # Attempt to retrieve from cache first.
        if cached_code := code_cache.get(cache_key):
            return cached_code

        # If not in cache, query the database for a common function.
        func = await Function.find_one(
            Function.app_id == app_id,
            Function.function_id == function_id,
            Function.status == FunctionStatus.PUBLISHED,
            Function.function_type == FunctionType.COMMON,
        )
        if not func:
            return None

        # Compile the code.
        compiled = self._compile_code(func.code, cache_key)

        # Cache the compiled code and return.
        code_cache.set(cache_key, compiled)
        return compiled

    def _compile_code(self, code: str, module_key: str) -> dict:
        """
        Compiles the provided Python code string into an executable function.
        Injects custom functions like 'minio_open' into the execution namespace.
        """
        try:
            # Use an independent namespace and inject custom functions.
            namespace = {
                "minio_open": minio_open,
            }
            exec(code, namespace)
            return {
                "handler": namespace["handler"],
                "dependencies": namespace.get("__dependencies__", []),
            }
        except Exception as e:
            raise RuntimeError(
                f"Code compilation failed for module '{module_key}': {e}"
            )
