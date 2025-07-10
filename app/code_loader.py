# app/code_loader.py
from typing import Optional
from loguru import logger
from types import SimpleNamespace

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
        app = await Application.find_one(
            {"app_id": {"$regex": f"^{app_id}$", "$options": "i"}}
        )
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
        Compiles the provided Python code string into an executable namespace.
        Injects custom functions like 'minio_open' into the execution namespace.
        """
        try:
            # Use an independent namespace and inject custom functions.
            namespace = {
                "minio_open": minio_open,
            }
            exec(code, namespace)
            # Return the entire namespace so all methods and classes are available
            return namespace
        except Exception as e:
            raise RuntimeError(
                f"Code compilation failed for module '{module_key}': {e}"
            )

    async def load_all_common_functions(self, app_id: str) -> SimpleNamespace:
        """
        Loads all common functions for a given application.
        It returns a dictionary where keys are function_ids and values are the compiled modules (namespaces).
        """
        common_namespaces = {}
        # Find all published common functions for the app.
        func_cursor = Function.find(
            Function.app_id == app_id,
            Function.status == FunctionStatus.PUBLISHED,
            Function.function_type == FunctionType.COMMON,
        )

        async for func in func_cursor:
            cache_key = code_cache._make_key(app_id, func.function_id, "common")

            # Try to get from cache first
            if cached_module := code_cache.get(cache_key):
                # Convert dict to namespace for attribute access
                common_namespaces[func.function_id] = SimpleNamespace(**cached_module)
                continue

            # If not in cache, compile and cache it
            try:
                compiled_namespace = self._compile_code(func.code, cache_key)
                code_cache.set(cache_key, compiled_namespace)
                # Convert dict to namespace for attribute access
                common_namespaces[func.function_id] = SimpleNamespace(
                    **compiled_namespace
                )
            except Exception as e:
                # Log the error but don't block other functions from loading
                logger.error(
                    f"Failed to compile common function {func.function_id} for app {app_id}: {e}"
                )

        # Return a namespace containing all common function namespaces
        return SimpleNamespace(**common_namespaces)
