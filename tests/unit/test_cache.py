"""Tests for data caching."""

import time
import pytest
from unittest.mock import patch

from nexustrade.data.cache import DataCache


class TestMemoryCache:
    async def test_set_and_get(self):
        cache = DataCache(enabled=True)
        await cache.set("ohlcv_1d", "AAPL", [{"close": 185.0}])
        result = await cache.get("ohlcv_1d", "AAPL")
        assert result == [{"close": 185.0}]

    async def test_same_request_twice_uses_cache(self):
        cache = DataCache(enabled=True)
        await cache.set("ohlcv_1d", "AAPL", [{"close": 185.0}])

        # Second call should return cached value
        result = await cache.get("ohlcv_1d", "AAPL")
        assert result is not None

    async def test_different_symbols_separate(self):
        cache = DataCache(enabled=True)
        await cache.set("ohlcv_1d", "AAPL", [{"close": 185.0}])
        await cache.set("ohlcv_1d", "MSFT", [{"close": 420.0}])

        assert (await cache.get("ohlcv_1d", "AAPL"))[0]["close"] == 185.0
        assert (await cache.get("ohlcv_1d", "MSFT"))[0]["close"] == 420.0

    async def test_ttl_expiration(self):
        cache = DataCache(enabled=True, ttl_seconds={"ohlcv_1d": 1})
        await cache.set("ohlcv_1d", "AAPL", [{"close": 185.0}])

        # Before expiry
        result = await cache.get("ohlcv_1d", "AAPL")
        assert result is not None

        # After expiry
        time.sleep(1.1)
        result = await cache.get("ohlcv_1d", "AAPL")
        assert result is None

    async def test_zero_ttl_no_cache(self):
        cache = DataCache(enabled=True, ttl_seconds={"quote": 0})
        await cache.set("quote", "AAPL", {"last": 185.0})
        result = await cache.get("quote", "AAPL")
        assert result is None  # Should not cache quotes

    async def test_cache_disabled(self):
        cache = DataCache(enabled=False)
        await cache.set("ohlcv_1d", "AAPL", [{"close": 185.0}])
        result = await cache.get("ohlcv_1d", "AAPL")
        assert result is None

    async def test_lru_eviction(self):
        cache = DataCache(enabled=True, max_memory_items=3)
        await cache.set("ohlcv_1d", "A", "a")
        await cache.set("ohlcv_1d", "B", "b")
        await cache.set("ohlcv_1d", "C", "c")
        await cache.set("ohlcv_1d", "D", "d")  # Should evict A

        assert await cache.get("ohlcv_1d", "A") is None
        assert await cache.get("ohlcv_1d", "D") == "d"

    async def test_invalidate(self):
        cache = DataCache(enabled=True)
        await cache.set("ohlcv_1d", "AAPL", [{"close": 185.0}])
        await cache.invalidate("ohlcv_1d", "AAPL")
        result = await cache.get("ohlcv_1d", "AAPL")
        assert result is None

    async def test_clear(self):
        cache = DataCache(enabled=True)
        await cache.set("ohlcv_1d", "AAPL", [{"close": 185.0}])
        await cache.set("ohlcv_1d", "MSFT", [{"close": 420.0}])
        await cache.clear()
        assert await cache.get("ohlcv_1d", "AAPL") is None
        assert await cache.get("ohlcv_1d", "MSFT") is None

    async def test_extra_kwargs_differentiate_keys(self):
        cache = DataCache(enabled=True)
        await cache.set("ohlcv_1h", "AAPL", "hourly", timeframe="1h")
        await cache.set("ohlcv_1d", "AAPL", "daily", timeframe="1d")

        assert await cache.get("ohlcv_1h", "AAPL", timeframe="1h") == "hourly"
        assert await cache.get("ohlcv_1d", "AAPL", timeframe="1d") == "daily"


class TestDiskCache:
    async def test_disk_cache(self, tmp_path):
        cache = DataCache(
            enabled=True, disk_cache_dir=str(tmp_path),
            ttl_seconds={"ohlcv_1d": 3600},
        )
        await cache.set("ohlcv_1d", "AAPL", [{"close": 185.0}])

        # Create new cache instance (simulates restart — memory empty)
        cache2 = DataCache(
            enabled=True, disk_cache_dir=str(tmp_path),
            ttl_seconds={"ohlcv_1d": 3600},
        )
        result = await cache2.get("ohlcv_1d", "AAPL")
        assert result == [{"close": 185.0}]

    async def test_disk_cache_expiry(self, tmp_path):
        cache = DataCache(
            enabled=True, disk_cache_dir=str(tmp_path),
            ttl_seconds={"ohlcv_1d": 1},
        )
        await cache.set("ohlcv_1d", "AAPL", [{"close": 185.0}])
        time.sleep(1.1)

        cache2 = DataCache(
            enabled=True, disk_cache_dir=str(tmp_path),
            ttl_seconds={"ohlcv_1d": 1},
        )
        result = await cache2.get("ohlcv_1d", "AAPL")
        assert result is None


class TestCacheToggle:
    async def test_enable_disable(self):
        cache = DataCache(enabled=True)
        await cache.set("ohlcv_1d", "AAPL", "data")
        assert await cache.get("ohlcv_1d", "AAPL") == "data"

        cache.enabled = False
        assert await cache.get("ohlcv_1d", "AAPL") is None

        cache.enabled = True
        assert await cache.get("ohlcv_1d", "AAPL") == "data"  # Still in memory
