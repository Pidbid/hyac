# app/code_loader.py
import ast
import inspect
from typing import Optional, Tuple
import httpx
from loguru import logger
from types import SimpleNamespace

from core.cache import code_cache
from core.runtime_client import get_runtime_client
from models.functions_model import Function, FunctionType


class CodeLoader:
    """
    Handles loading, compiling, and caching of serverless function code.
    """

    async def load_function_by_ids(
        self, app_id: str, function_id: str
    ) -> Optional[Tuple[str, Function, inspect.Signature]]:
        """
        Loads a function by its application ID and function ID.
        It first checks the cache, and if not found, queries the database,
        parses the handler signature without executing user code in this process.
        Returns a tuple of (source_code, function_document, signature).
        """
        cache_key = code_cache._make_key(app_id, function_id)

        # Attempt to retrieve from cache first.
        if cached_data := code_cache.get(cache_key):
            return cached_data

        try:
            function_data = await get_runtime_client().get_function(function_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        func_doc = Function.model_validate(function_data)
        if func_doc.function_type != FunctionType.ENDPOINT:
            return None

        signature = self._inspect_handler_signature(func_doc.code)

        data_to_cache = (func_doc.code, func_doc, signature)
        code_cache.set(cache_key, data_to_cache)
        return data_to_cache

    async def load_common_function_by_name(
        self, app_id: str, function_name: str
    ) -> Optional[str]:
        """
        Loads a common function by its application ID and function name.
        It checks the cache first, and if not found, queries the database,
        validates the source without executing it, and caches the source.
        """
        cache_key = code_cache._make_key(app_id, function_name, "common")

        # Attempt to retrieve from cache first.
        if cached_code := code_cache.get(cache_key):
            return cached_code

        functions = await get_runtime_client().get_functions(FunctionType.COMMON.value)
        func = next(
            (
                Function.model_validate(item)
                for item in functions
                if item.get("function_name") == function_name
            ),
            None,
        )
        if not func:
            return None

        ast.parse(func.code)

        code_cache.set(cache_key, func.code)
        return func.code

    def _inspect_handler_signature(self, code: str) -> inspect.Signature:
        """Extract a handler signature from the AST without running module code."""
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            raise RuntimeError(f"Code syntax is invalid: {exc}") from exc

        handler = next(
            (
                node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "handler"
            ),
            None,
        )
        if handler is None:
            raise RuntimeError("Function source must define a top-level handler")

        parameters = [
            inspect.Parameter(arg.arg, inspect.Parameter.POSITIONAL_ONLY)
            for arg in handler.args.posonlyargs
        ]
        parameters.extend(
            inspect.Parameter(arg.arg, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            for arg in handler.args.args
        )
        if handler.args.vararg:
            parameters.append(
                inspect.Parameter(
                    handler.args.vararg.arg,
                    inspect.Parameter.VAR_POSITIONAL,
                )
            )
        parameters.extend(
            inspect.Parameter(arg.arg, inspect.Parameter.KEYWORD_ONLY)
            for arg in handler.args.kwonlyargs
        )
        if handler.args.kwarg:
            parameters.append(
                inspect.Parameter(
                    handler.args.kwarg.arg,
                    inspect.Parameter.VAR_KEYWORD,
                )
            )
        return inspect.Signature(parameters)

    async def load_all_common_functions(self, app_id: str) -> SimpleNamespace:
        """
        Loads all common functions for a given application.
        It returns a namespace where values are source strings compiled only by a child worker.
        """
        common_sources = {}
        function_data = await get_runtime_client().get_functions(
            FunctionType.COMMON.value
        )
        for item in function_data:
            func = Function.model_validate(item)
            cache_key = code_cache._make_key(app_id, func.function_name, "common")

            # Try to get from cache first
            if cached_source := code_cache.get(cache_key):
                common_sources[func.function_name] = cached_source
                continue

            try:
                ast.parse(func.code)
                code_cache.set(cache_key, func.code)
                common_sources[func.function_name] = func.code
            except Exception as e:
                logger.error(
                    f"Failed to parse common function {func.function_name} for app {app_id}: {e}"
                )

        return SimpleNamespace(**common_sources)
