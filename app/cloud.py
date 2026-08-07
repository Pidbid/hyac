from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from context import FunctionContext


class CloudFacade:
    """Stable resource facade exposed to user functions as `ctx.cloud`."""

    def __init__(self, context: "FunctionContext"):
        self._context = context

    def database(self, sync: bool = False) -> Any:
        """Return the current app database client.

        Args:
            sync: When true, return the synchronous PyMongo database. Otherwise,
                return the asynchronous PyMongo database.
        """
        if sync:
            return self._context.pymongo_db
        return self._context.async_db

    def storage(self) -> Any:
        """Return the current app object-storage context."""
        return self._context.s3

    def env(self) -> Any:
        """Return the current app environment manager."""
        return self._context.env

    def logger(self) -> Any:
        """Return the current function logger."""
        return self._context.logger

    def notification(self) -> Any:
        """Return the current app notification manager."""
        return self._context.notification

    def common(self) -> Any:
        """Return the loaded common function namespace."""
        return self._context.common
