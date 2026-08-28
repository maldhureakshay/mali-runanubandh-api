"""
Rate Limiter.

Implements an in-memory sliding window rate limiter.
Configured for per-IP, per-user, and per-endpoint tracking.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class InMemRateLimiter:
    """
    Sliding window log rate limiter using memory-backed timestamps.
    """

    def __init__(self, default_limit: int = 100, default_window: int = 60) -> None:
        """
        Initialize defaults and in-memory log registry.
        """
        self._default_limit = default_limit
        self._default_window = default_window
        self._requests: Dict[str, List[float]] = {}  # identifier -> list of request timestamps
        self._lock = asyncio.Lock()

    async def is_rate_limited(
        self,
        key: str,
        limit: Optional[int] = None,
        window: Optional[int] = None
    ) -> bool:
        """
        Check if the request key has exceeded its allowed quota.
        """
        target_limit = limit if limit is not None else self._default_limit
        target_window = window if window is not None else self._default_window
        
        async with self._lock:
            now = time.time()
            cutoff = now - target_window
            
            # Initialize or clean old logs
            if key not in self._requests:
                self._requests[key] = []
            
            # Evict timestamps older than current window
            self._requests[key] = [ts for ts in self._requests[key] if ts > cutoff]
            
            if len(self._requests[key]) >= target_limit:
                logger.warning("Rate limit exceeded for key: %s (limit: %d/%ds)", key, target_limit, target_window)
                return True
                
            # Log current request timestamp
            self._requests[key].append(now)
            return False

    async def clear(self) -> None:
        """
        Clear all rate limit entries.
        """
        async with self._lock:
            self._requests.clear()
