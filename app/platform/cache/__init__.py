"""
Caching module.

Exposes caching abstractions and providers.
"""

from app.platform.cache.base import CacheProvider
from app.platform.cache.memory import MemoryCacheProvider
