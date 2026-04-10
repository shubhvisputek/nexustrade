"""3-level data cache: memory LRU → Redis → disk.

Configurable TTL per data type. Cache can be disabled via config.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DataCache:
    """Three-level cache for market data.

    Level 1: In-memory LRU cache (fastest, limited size)
    Level 2: Redis cache (fast, shared across processes)
    Level 3: Disk cache (slowest, unlimited size)

    Each level has configurable TTL per data type.
    """

    def __init__(
        self,
        enabled: bool = True,
        ttl_seconds: dict[str, int] | None = None,
        max_memory_items: int = 1000,
        disk_cache_dir: str | None = None,
        redis_client: Any = None,
    ) -> None:
        self._enabled = enabled
        self._ttl = ttl_seconds or {
            "quote": 0,
            "ohlcv_1m": 60,
            "ohlcv_1h": 300,
            "ohlcv_1d": 3600,
            "fundamentals": 86400,
            "news": 300,
        }
        self._max_memory = max_memory_items
        self._memory: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._redis = redis_client
        self._disk_dir = Path(disk_cache_dir) if disk_cache_dir else None
        if self._disk_dir:
            self._disk_dir.mkdir(parents=True, exist_ok=True)

    def _make_key(self, data_type: str, symbol: str, **kwargs: Any) -> str:
        """Create a unique cache key from parameters."""
        parts = [data_type, symbol]
        for k, v in sorted(kwargs.items()):
            parts.append(f"{k}={v}")
        raw = ":".join(parts)
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_ttl(self, data_type: str) -> int:
        """Get TTL in seconds for a data type."""
        return self._ttl.get(data_type, 300)

    def _is_expired(self, cached_at: float, data_type: str) -> bool:
        """Check if a cached value has expired."""
        ttl = self._get_ttl(data_type)
        if ttl == 0:
            return True  # No cache for this type
        return (time.time() - cached_at) > ttl

    # --- Public API ---

    async def get(
        self, data_type: str, symbol: str, **kwargs: Any
    ) -> Any | None:
        """Get a value from cache, checking all levels."""
        if not self._enabled:
            return None

        ttl = self._get_ttl(data_type)
        if ttl == 0:
            return None

        key = self._make_key(data_type, symbol, **kwargs)

        # Level 1: Memory
        value = self._get_memory(key, data_type)
        if value is not None:
            logger.debug("Cache HIT (memory): %s %s", data_type, symbol)
            return value

        # Level 2: Redis
        value = await self._get_redis(key, data_type)
        if value is not None:
            logger.debug("Cache HIT (redis): %s %s", data_type, symbol)
            self._set_memory(key, value)
            return value

        # Level 3: Disk
        value = self._get_disk(key, data_type)
        if value is not None:
            logger.debug("Cache HIT (disk): %s %s", data_type, symbol)
            self._set_memory(key, value)
            return value

        logger.debug("Cache MISS: %s %s", data_type, symbol)
        return None

    async def set(
        self, data_type: str, symbol: str, value: Any, **kwargs: Any
    ) -> None:
        """Store a value in all cache levels."""
        if not self._enabled:
            return

        ttl = self._get_ttl(data_type)
        if ttl == 0:
            return

        key = self._make_key(data_type, symbol, **kwargs)

        # Level 1: Memory
        self._set_memory(key, value)

        # Level 2: Redis
        await self._set_redis(key, value, ttl)

        # Level 3: Disk
        self._set_disk(key, value)

    async def invalidate(
        self, data_type: str, symbol: str, **kwargs: Any
    ) -> None:
        """Remove a value from all cache levels."""
        key = self._make_key(data_type, symbol, **kwargs)

        if key in self._memory:
            del self._memory[key]

        if self._redis:
            try:
                await self._redis.delete(f"nexus:cache:{key}")
            except Exception:
                pass

        if self._disk_dir:
            disk_path = self._disk_dir / f"{key}.json"
            disk_path.unlink(missing_ok=True)

    async def clear(self) -> None:
        """Clear all cache levels."""
        self._memory.clear()
        # Redis and disk clearing would be done here

    # --- Level 1: Memory ---

    def _get_memory(self, key: str, data_type: str) -> Any | None:
        if key not in self._memory:
            return None
        cached_at, value = self._memory[key]
        if self._is_expired(cached_at, data_type):
            del self._memory[key]
            return None
        self._memory.move_to_end(key)
        return value

    def _set_memory(self, key: str, value: Any) -> None:
        self._memory[key] = (time.time(), value)
        self._memory.move_to_end(key)
        while len(self._memory) > self._max_memory:
            self._memory.popitem(last=False)

    # --- Level 2: Redis ---

    async def _get_redis(self, key: str, data_type: str) -> Any | None:
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(f"nexus:cache:{key}")
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.debug("Redis cache read failed for %s", key)
            return None

    async def _set_redis(self, key: str, value: Any, ttl: int) -> None:
        if not self._redis:
            return
        try:
            raw = json.dumps(value, default=str)
            await self._redis.setex(f"nexus:cache:{key}", ttl, raw)
        except Exception:
            logger.debug("Redis cache write failed for %s", key)

    # --- Level 3: Disk ---

    def _get_disk(self, key: str, data_type: str) -> Any | None:
        if not self._disk_dir:
            return None
        disk_path = self._disk_dir / f"{key}.json"
        if not disk_path.exists():
            return None
        try:
            data = json.loads(disk_path.read_text())
            cached_at = data.get("_cached_at", 0)
            if self._is_expired(cached_at, data_type):
                disk_path.unlink(missing_ok=True)
                return None
            return data.get("value")
        except Exception:
            return None

    def _set_disk(self, key: str, value: Any) -> None:
        if not self._disk_dir:
            return
        disk_path = self._disk_dir / f"{key}.json"
        try:
            data = {"_cached_at": time.time(), "value": value}
            disk_path.write_text(json.dumps(data, default=str))
        except Exception:
            logger.debug("Disk cache write failed for %s", key)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
