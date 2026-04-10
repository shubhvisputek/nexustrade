"""Smart data routing — selects the best provider per market/data-type.

Reads routing config (market → provider priority list), checks provider
health, and falls back on failure.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from nexustrade.core.exceptions import DataProviderError
from nexustrade.core.interfaces import DataProviderInterface
from nexustrade.core.models import OHLCV, NewsItem, Quote, TechnicalIndicators

logger = logging.getLogger(__name__)


class DataRouter:
    """Routes data requests to the best available provider.

    Uses a priority list per market. On failure or unhealthy provider,
    automatically falls back to the next provider in the list.
    """

    def __init__(self) -> None:
        self._providers: dict[str, DataProviderInterface] = {}
        self._routing: dict[str, list[str]] = {}  # market → [provider names]
        self._symbol_market: dict[str, str] = {}  # symbol → market

    def register_provider(self, provider: DataProviderInterface) -> None:
        """Register a data provider instance."""
        self._providers[provider.name] = provider
        logger.info("Registered data provider: %s", provider.name)

    def configure_routing(
        self,
        routing: dict[str, list[str]],
        symbol_market_map: dict[str, str] | None = None,
    ) -> None:
        """Set the market → provider priority routing table."""
        self._routing = routing
        if symbol_market_map:
            self._symbol_market = symbol_market_map

    def set_symbol_market(self, symbol: str, market: str) -> None:
        """Map a symbol to its market for routing."""
        self._symbol_market[symbol] = market

    def _get_market_for_symbol(self, symbol: str) -> str:
        """Infer market from symbol format or lookup table."""
        if symbol in self._symbol_market:
            return self._symbol_market[symbol]
        # Heuristic: crypto has /, forex has 3/3 format
        if "/" in symbol:
            parts = symbol.split("/")
            if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
                # Could be forex (EUR/USD) or crypto (BTC/USD)
                if parts[1] in ("USDT", "BUSD", "USDC", "BTC", "ETH"):
                    return "crypto"
                return "forex"
            return "crypto"
        return "us_equity"  # default

    def _get_providers_for_symbol(self, symbol: str) -> list[DataProviderInterface]:
        """Get ordered list of providers for a symbol."""
        market = self._get_market_for_symbol(symbol)
        provider_names = self._routing.get(market, [])

        providers = []
        for name in provider_names:
            if name in self._providers:
                providers.append(self._providers[name])

        if not providers:
            # Fallback: try all providers
            providers = list(self._providers.values())

        return providers

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCV]:
        """Fetch OHLCV data, trying providers in priority order."""
        for provider in self._get_providers_for_symbol(symbol):
            try:
                if not await provider.health_check():
                    logger.warning("Provider %s unhealthy, skipping", provider.name)
                    continue
                result = await provider.get_ohlcv(symbol, timeframe, start, end)
                if result:
                    logger.debug(
                        "Got %d bars for %s from %s", len(result), symbol, provider.name
                    )
                    return result
            except Exception:
                logger.exception("Provider %s failed for %s", provider.name, symbol)
                continue

        raise DataProviderError(
            f"All providers failed to fetch OHLCV for {symbol}"
        )

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch real-time quote, trying providers in priority order."""
        for provider in self._get_providers_for_symbol(symbol):
            try:
                if not await provider.health_check():
                    continue
                return await provider.get_quote(symbol)
            except Exception:
                logger.exception("Provider %s failed quote for %s", provider.name, symbol)
                continue

        raise DataProviderError(f"All providers failed to fetch quote for {symbol}")

    async def get_news(self, symbol: str, limit: int = 20) -> list[NewsItem]:
        """Fetch news, trying providers that support it."""
        for provider in self._get_providers_for_symbol(symbol):
            try:
                result = await provider.get_news(symbol, limit)
                if result:
                    return result
            except Exception:
                continue
        return []

    async def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Fetch fundamentals from first available provider."""
        for provider in self._get_providers_for_symbol(symbol):
            try:
                result = await provider.get_fundamentals(symbol)
                if result:
                    return result
            except Exception:
                continue
        return {}

    async def get_technicals(
        self, symbol: str, timeframe: str = "1d"
    ) -> TechnicalIndicators | None:
        """Fetch technical indicators from first available provider."""
        for provider in self._get_providers_for_symbol(symbol):
            try:
                result = await provider.get_technicals(symbol, timeframe)
                if result:
                    return result
            except Exception:
                continue
        return None

    async def get_chart_image(self, symbol: str, timeframe: str) -> bytes | None:
        """Fetch chart image from first available provider."""
        for provider in self._get_providers_for_symbol(symbol):
            try:
                result = await provider.get_chart_image(symbol, timeframe)
                if result:
                    return result
            except Exception:
                continue
        return None

    @property
    def providers(self) -> dict[str, DataProviderInterface]:
        return dict(self._providers)
