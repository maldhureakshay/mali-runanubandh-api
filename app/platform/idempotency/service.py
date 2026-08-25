"""
Idempotency Service.

Provides mechanisms to verify and cache request payloads to prevent double submissions.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from app.platform.cache.base import CacheProvider

logger = logging.getLogger(__name__)


class IdempotencyService:
    """
    Service to register, lock, and retrieve duplicate request payloads by key.
    """

    def __init__(self, cache: CacheProvider) -> None:
        """
        Constructor injects CacheProvider.
        """
        self._cache = cache

    async def get_response(self, key: str) -> Optional[Tuple[int, Dict[str, str], Any]]:
        """
        Retrieve cached response for a given key.
        Returns: Tuple of (status_code, headers, body) or None if missing.
        """
        cache_key = f"idempotency:{key}"
        data = await self._cache.get(cache_key)
        if not data:
            return None
        return data  # Contains (status_code, headers, body)

    async def start_request(self, key: str) -> bool:
        """
        Mark an idempotency key as in-progress.
        Returns True if successful, False if the key is already locked or completed.
        """
        cache_key = f"idempotency:{key}"
        if await self._cache.exists(cache_key):
            return False

        # Lock key as PENDING (indicated by status_code = 0) with a 30 second timeout
        await self._cache.set(cache_key, (0, {}, "PENDING"), ttl=30)
        return True

    async def save_response(
        self,
        key: str,
        status_code: int,
        headers: Dict[str, str],
        body: Any,
        ttl: int = 86400
    ) -> None:
        """
        Cache the final response associated with the idempotency key.
        Defaults to a 24 hour TTL.
        """
        cache_key = f"idempotency:{key}"
        # Filter headers to keep only standard/safe metadata
        filtered_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ("content-length", "date", "server", "set-cookie")
        }
        await self._cache.set(cache_key, (status_code, filtered_headers, body), ttl=ttl)
        logger.info("Saved idempotency response for key: %s (status: %d)", key, status_code)
