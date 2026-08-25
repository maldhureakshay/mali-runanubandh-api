"""
Memory Cache Provider.

In-memory implementation of the CacheProvider interface. Enforces TTL-based eviction.
"""

import asyncio
import time
from typing import Any, Dict, Optional, Tuple

from app.platform.cache.base import CacheProvider


class MemoryCacheProvider(CacheProvider):
    """
    In-memory, async-locked cache provider.
    """

    def __init__(self) -> None:
        """
        Initialize store and lock.
        """
        self._store: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expire_at)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value. Evicts key if it is expired.
        """
        async with self._lock:
            if key not in self._store:
                return None

            value, expire_at = self._store[key]
            if expire_at is not None and time.time() > expire_at:
                del self._store[key]
                return None

            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Store value. Sets expiration timestamp if TTL is specified.
        """
        async with self._lock:
            expire_at = (time.time() + ttl) if ttl is not None else None
            self._store[key] = (value, expire_at)
            return True

    async def delete(self, key: str) -> bool:
        """
        Delete key.
        """
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        """
        Check existence.
        """
        async with self._lock:
            if key not in self._store:
                return False
            _, expire_at = self._store[key]
            if expire_at is not None and time.time() > expire_at:
                del self._store[key]
                return False
            return True

    async def clear(self) -> bool:
        """
        Clear all keys.
        """
        async with self._lock:
            self._store.clear()
            return True
