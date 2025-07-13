# core/cache.py
import time
from typing import Any, Optional
from models.functions_model import Function


class CodeCache:
    """
    A simple in-memory cache with a Time-To-Live (TTL) and max size.
    """

    def __init__(self, max_size: int = 512, ttl: int = 3600):
        """
        Initializes the cache.

        Args:
            max_size: The maximum number of items in the cache.
            ttl: The time-to-live for cache entries, in seconds.
        """
        self._cache = {}
        self.max_size = max_size
        self.ttl = ttl  # Time-to-live in seconds

    def _make_key(
        self, app_name: str, function_id: str, suffix: Optional[str] = None
    ) -> str:
        """
        Creates a unique cache key from the app name and function ID.
        An optional suffix can be added for different cache types (e.g., 'common').
        """
        key = f"{app_name}::{function_id}"
        if suffix:
            key += f"::{suffix}"
        return key

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieves an item from the cache if it exists and has not expired.
        """
        entry = self._cache.get(key)
        if entry and (entry["expire_at"] > time.time()):
            return entry["data"]
        return None

    def set(self, key: str, data: Any):
        """
        Adds an item to the cache. If the cache is full, it evicts the oldest item.
        """
        if len(self._cache) >= self.max_size:
            self._evict()
        self._cache[key] = {"data": data, "expire_at": time.time() + self.ttl}

    def _evict(self):
        """
        Evicts the oldest item from the cache (FIFO strategy).
        """
        oldest_key = next(iter(self._cache))
        del self._cache[oldest_key]

    def invalidate(self, app_name: str, function_id: str):
        """
        Removes a specific item and all its variants from the cache.
        """
        prefix = self._make_key(app_name, function_id)
        keys_to_delete = [key for key in self._cache if key.startswith(prefix)]
        for key in keys_to_delete:
            self._cache.pop(key, None)

    def clear_app_cache(self, app_id: str):
        """
        Removes all cache entries associated with a specific app_id.
        """
        keys_to_delete = [key for key in self._cache if key.startswith(f"{app_id}::")]
        for key in keys_to_delete:
            del self._cache[key]


# Global instance of the code cache, with a 2-hour TTL.
code_cache = CodeCache(max_size=1024, ttl=7200)
