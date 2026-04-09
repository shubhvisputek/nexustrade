"""Tests for data routing."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

from nexustrade.core.exceptions import DataProviderError
from nexustrade.core.interfaces import DataProviderInterface
from nexustrade.core.models import OHLCV, Quote
from nexustrade.data.router import DataRouter


UTC_NOW = datetime.now(timezone.utc)


def make_ohlcv(symbol: str = "AAPL", source: str = "test") -> OHLCV:
    return OHLCV(
        timestamp=UTC_NOW, open=185.0, high=186.0, low=184.0,
        close=185.5, volume=1_000_000, symbol=symbol,
        timeframe="1d", source=source,
    )


def make_quote(symbol: str = "AAPL", source: str = "test") -> Quote:
    return Quote(
        symbol=symbol, bid=185.0, ask=185.10, last=185.05,
        volume=1_000_000, timestamp=UTC_NOW, source=source,
    )


class MockProvider(DataProviderInterface):
    """Test provider that can be configured to succeed or fail."""

    def __init__(self, name: str, healthy: bool = True, data: list | None = None):
        self._name = name
        self._healthy = healthy
        self._data = data

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity", "crypto"]

    async def get_ohlcv(self, symbol, timeframe, start, end) -> list[OHLCV]:
        if self._data is not None:
            return self._data
        return [make_ohlcv(symbol, self._name)]

    async def get_quote(self, symbol) -> Quote:
        return make_quote(symbol, self._name)

    async def health_check(self) -> bool:
        return self._healthy


class FailingProvider(DataProviderInterface):
    @property
    def name(self) -> str:
        return "failing"

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity"]

    async def get_ohlcv(self, symbol, timeframe, start, end):
        raise ConnectionError("Provider down")

    async def get_quote(self, symbol):
        raise ConnectionError("Provider down")

    async def health_check(self) -> bool:
        return True


class TestDataRouter:
    async def test_healthy_provider_selected(self):
        router = DataRouter()
        provider = MockProvider("openbb")
        router.register_provider(provider)
        router.configure_routing({"us_equity": ["openbb"]})

        start = UTC_NOW - timedelta(days=30)
        result = await router.get_ohlcv("AAPL", "1d", start, UTC_NOW)
        assert len(result) == 1
        assert result[0].source == "openbb"

    async def test_unhealthy_provider_skipped(self):
        router = DataRouter()
        unhealthy = MockProvider("primary", healthy=False)
        healthy = MockProvider("fallback", healthy=True)
        router.register_provider(unhealthy)
        router.register_provider(healthy)
        router.configure_routing({"us_equity": ["primary", "fallback"]})

        start = UTC_NOW - timedelta(days=30)
        result = await router.get_ohlcv("AAPL", "1d", start, UTC_NOW)
        assert result[0].source == "fallback"

    async def test_failing_provider_falls_back(self):
        router = DataRouter()
        failing = FailingProvider()
        good = MockProvider("backup")
        router.register_provider(failing)
        router.register_provider(good)
        router.configure_routing({"us_equity": ["failing", "backup"]})

        start = UTC_NOW - timedelta(days=30)
        result = await router.get_ohlcv("AAPL", "1d", start, UTC_NOW)
        assert result[0].source == "backup"

    async def test_all_providers_fail_raises(self):
        router = DataRouter()
        router.register_provider(FailingProvider())
        router.configure_routing({"us_equity": ["failing"]})

        start = UTC_NOW - timedelta(days=30)
        with pytest.raises(DataProviderError, match="All providers failed"):
            await router.get_ohlcv("AAPL", "1d", start, UTC_NOW)

    async def test_quote_routing(self):
        router = DataRouter()
        router.register_provider(MockProvider("openbb"))
        router.configure_routing({"us_equity": ["openbb"]})

        quote = await router.get_quote("AAPL")
        assert quote.symbol == "AAPL"
        assert quote.source == "openbb"

    async def test_crypto_symbol_detection(self):
        router = DataRouter()
        router.register_provider(MockProvider("ccxt"))
        router.configure_routing({"crypto": ["ccxt"]})

        start = UTC_NOW - timedelta(days=7)
        result = await router.get_ohlcv("BTC/USDT", "1h", start, UTC_NOW)
        assert result[0].source == "ccxt"

    async def test_forex_symbol_detection(self):
        router = DataRouter()
        router.register_provider(MockProvider("openbb"))
        router.configure_routing({"forex": ["openbb"]})

        start = UTC_NOW - timedelta(days=7)
        result = await router.get_ohlcv("EUR/USD", "4h", start, UTC_NOW)
        assert result[0].source == "openbb"

    async def test_explicit_symbol_market_mapping(self):
        router = DataRouter()
        router.register_provider(MockProvider("broker"))
        router.configure_routing({"india_equity": ["broker"]})
        router.set_symbol_market("RELIANCE", "india_equity")

        start = UTC_NOW - timedelta(days=30)
        result = await router.get_ohlcv("RELIANCE", "1d", start, UTC_NOW)
        assert result[0].source == "broker"

    async def test_empty_result_tries_next_provider(self):
        router = DataRouter()
        empty_provider = MockProvider("empty", data=[])
        good_provider = MockProvider("good")
        router.register_provider(empty_provider)
        router.register_provider(good_provider)
        router.configure_routing({"us_equity": ["empty", "good"]})

        start = UTC_NOW - timedelta(days=30)
        result = await router.get_ohlcv("AAPL", "1d", start, UTC_NOW)
        assert result[0].source == "good"

    async def test_news_returns_empty_on_no_providers(self):
        router = DataRouter()
        result = await router.get_news("AAPL")
        assert result == []

    async def test_fundamentals_returns_empty_on_no_providers(self):
        router = DataRouter()
        result = await router.get_fundamentals("AAPL")
        assert result == {}
