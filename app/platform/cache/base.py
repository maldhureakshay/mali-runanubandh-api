"""
Cache Abstraction Base.

Defines the abstract CacheProvider interface that all cache backends must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheProvider(ABC):
    """
    Abstract base class for platform caching providers.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from the cache. Returns None if key is expired or missing.
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Store a value in the cache with an optional TTL (in seconds).
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Remove a key from the cache. Returns True if key existed and was deleted.
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache and is not expired.
        """
        pass

    @abstractmethod
    async def clear(self) -> bool:
        """
        Evict all keys from the cache.
        """
        pass
