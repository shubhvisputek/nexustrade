"""TradingView MCP data adapter (stub).

This adapter will connect to TradingView MCP servers as an MCP client to
retrieve technical indicators, chart images, and screener results.

Currently a stub — placeholder methods return empty/None values.  Full MCP
client integration will be wired up in Phase 3.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from nexustrade.core.interfaces import DataProviderInterface
from nexustrade.core.models import OHLCV, Quote, TechnicalIndicators

logger = logging.getLogger(__name__)


class TradingViewMCPAdapter(DataProviderInterface):
    """TradingView data via MCP server connections.

    This adapter does **not** provide raw OHLCV or quote data.  Instead it
    exposes TradingView-specific capabilities: pre-computed technicals,
    chart screenshots, and screener queries.

    Parameters
    ----------
    config:
        Dictionary containing MCP server URLs and connection settings.
        Expected keys::

            {
                "technicals_url": "http://localhost:3001",
                "chart_url": "http://localhost:3002",
                "screener_url": "http://localhost:3003",
            }
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._technicals_url = self._config.get("technicals_url", "")
        self._chart_url = self._config.get("chart_url", "")
        self._screener_url = self._config.get("screener_url", "")
        logger.info(
            "TradingViewMCPAdapter initialized (stub) — "
            "full MCP client integration pending Phase 3"
        )

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "tradingview_mcp"

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity", "india_equity", "forex", "crypto"]

    # -- OHLCV / Quote — not supported ---------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCV]:
        """Not supported — TradingView MCP provides technicals, not raw bars."""
        raise NotImplementedError(
            "TradingView MCP does not provide raw OHLCV/quote data. "
            "Use get_technicals() instead."
        )

    async def get_quote(self, symbol: str) -> Quote:
        """Not supported — TradingView MCP provides technicals, not raw quotes."""
        raise NotImplementedError(
            "TradingView MCP does not provide raw OHLCV/quote data. "
            "Use get_technicals() instead."
        )

    # -- TradingView-specific methods ----------------------------------------

    async def get_technicals(
        self,
        symbol: str,
        timeframe: str,
    ) -> TechnicalIndicators | None:
        """Fetch pre-computed technical indicators from TradingView MCP.

        Stub — returns ``None`` until the MCP client is wired up.
        """
        # TODO: Call TV MCP server's get_technicals tool
        logger.debug(
            "get_technicals(%s, %s) — stub, returning None", symbol, timeframe
        )
        return None

    async def get_chart_image(
        self,
        symbol: str,
        timeframe: str,
    ) -> bytes | None:
        """Fetch a chart screenshot from TradingView MCP.

        Stub — returns ``None`` until the MCP client is wired up.
        """
        # TODO: Call chart MCP server
        logger.debug(
            "get_chart_image(%s, %s) — stub, returning None",
            symbol,
            timeframe,
        )
        return None

    async def screen(
        self,
        criteria: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a TradingView screener query.

        Stub — returns an empty list until the MCP client is wired up.
        """
        # TODO: Call screener MCP server
        logger.debug("screen(%s) — stub, returning []", criteria)
        return []

    # -- health --------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if MCP servers are reachable.

        Stub — returns ``False`` (no servers configured yet).
        """
        # Once MCP clients are integrated this will ping each server.
        return bool(
            self._technicals_url
            or self._chart_url
            or self._screener_url
        )
