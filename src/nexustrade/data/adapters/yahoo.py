"""Yahoo Finance data adapter.

Wraps the ``yfinance`` library to provide OHLCV bars, quotes, news,
and fundamental data for US equities, crypto pairs, and forex.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from nexustrade.core.interfaces import DataProviderInterface
from nexustrade.core.models import OHLCV, NewsItem, Quote

logger = logging.getLogger(__name__)

# Attempt to import yfinance; adapter degrades gracefully if absent.
try:
    import yfinance as yf

    _YF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YF_AVAILABLE = False
    yf = None  # type: ignore[assignment]

# Map NexusTrade canonical timeframes to yfinance interval strings.
_TIMEFRAME_MAP: dict[str, str] = {
    "1m": "1m",
    "2m": "2m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "1h",  # yfinance has no 4h; we'll resample if needed
    "1d": "1d",
    "1w": "1wk",
    "1M": "1mo",
}


class YahooFinanceAdapter(DataProviderInterface):
    """Data provider backed by Yahoo Finance (via ``yfinance``)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    # -- identity ------------------------------------------------------------

    @property
    def name(self) -> str:
        return "yahoo"

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity", "crypto", "forex"]

    # -- required ------------------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCV]:
        """Download OHLCV bars from Yahoo Finance."""
        if not _YF_AVAILABLE:
            logger.warning("yfinance is not installed; returning empty OHLCV")
            return []

        interval = _TIMEFRAME_MAP.get(timeframe, "1d")

        def _download() -> list[OHLCV]:
            try:
                df = yf.download(
                    symbol,
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    interval=interval,
                    progress=False,
                    auto_adjust=True,
                )
                if df is None or df.empty:
                    return []

                # yfinance >= 0.2.31 returns multi-level columns for
                # single-ticker downloads.  Flatten them.
                if isinstance(df.columns, __import__('pandas').MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                bars: list[OHLCV] = []
                for ts, row in df.iterrows():
                    o = float(row["Open"])
                    h = float(row["High"])
                    l_ = float(row["Low"])
                    c = float(row["Close"])
                    v = float(row["Volume"])

                    # Ensure UTC-aware timestamp
                    bar_ts = ts.to_pydatetime()  # type: ignore[union-attr]
                    if bar_ts.tzinfo is None:
                        bar_ts = bar_ts.replace(tzinfo=timezone.utc)
                    else:
                        bar_ts = bar_ts.astimezone(timezone.utc)

                    bars.append(
                        OHLCV(
                            timestamp=bar_ts,
                            open=o,
                            high=h,
                            low=l_,
                            close=c,
                            volume=v,
                            symbol=symbol,
                            timeframe=timeframe,
                            source=self.name,
                        )
                    )
                return bars
            except Exception:
                logger.exception("Yahoo OHLCV download failed for %s", symbol)
                return []

        return await asyncio.to_thread(_download)

    async def get_quote(self, symbol: str) -> Quote:
        """Return the latest quote for *symbol*."""
        if not _YF_AVAILABLE:
            logger.warning("yfinance is not installed; returning stub Quote")
            return self._empty_quote(symbol)

        def _fetch_quote() -> Quote:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}

                bid = float(info.get("bid", 0.0) or 0.0)
                ask = float(info.get("ask", 0.0) or 0.0)
                last = float(
                    info.get("regularMarketPrice")
                    or info.get("currentPrice")
                    or info.get("previousClose")
                    or 0.0
                )
                volume = float(
                    info.get("regularMarketVolume")
                    or info.get("volume")
                    or 0.0
                )

                return Quote(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    last=last,
                    volume=volume,
                    timestamp=datetime.now(timezone.utc),
                    source=self.name,
                )
            except Exception:
                logger.exception("Yahoo quote fetch failed for %s", symbol)
                return self._empty_quote(symbol)

        return await asyncio.to_thread(_fetch_quote)

    # -- optional overrides --------------------------------------------------

    async def get_news(
        self,
        symbol: str,
        limit: int = 10,
    ) -> list[NewsItem]:
        """Return recent news items from Yahoo Finance."""
        if not _YF_AVAILABLE:
            return []

        def _fetch_news() -> list[NewsItem]:
            try:
                ticker = yf.Ticker(symbol)
                raw_news = ticker.news or []
                items: list[NewsItem] = []
                for article in raw_news[:limit]:
                    pub_ts = article.get("providerPublishTime")
                    if pub_ts is not None:
                        ts = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
                    else:
                        ts = datetime.now(timezone.utc)

                    items.append(
                        NewsItem(
                            timestamp=ts,
                            headline=article.get("title", ""),
                            source=article.get("publisher", "yahoo"),
                            symbols=[symbol],
                            url=article.get("link"),
                        )
                    )
                return items
            except Exception:
                logger.exception("Yahoo news fetch failed for %s", symbol)
                return []

        return await asyncio.to_thread(_fetch_news)

    async def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Return fundamental data from Yahoo Finance."""
        if not _YF_AVAILABLE:
            return {}

        def _fetch_fundamentals() -> dict[str, Any]:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                # Extract a curated subset of fundamentals.
                keys = [
                    "trailingPE",
                    "forwardPE",
                    "trailingEps",
                    "forwardEps",
                    "totalRevenue",
                    "revenueGrowth",
                    "grossMargins",
                    "operatingMargins",
                    "profitMargins",
                    "returnOnEquity",
                    "debtToEquity",
                    "currentRatio",
                    "bookValue",
                    "priceToBook",
                    "marketCap",
                    "enterpriseValue",
                    "dividendYield",
                    "payoutRatio",
                    "beta",
                    "fiftyTwoWeekHigh",
                    "fiftyTwoWeekLow",
                    "sector",
                    "industry",
                    "longBusinessSummary",
                ]
                return {k: info.get(k) for k in keys if info.get(k) is not None}
            except Exception:
                logger.exception("Yahoo fundamentals fetch failed for %s", symbol)
                return {}

        return await asyncio.to_thread(_fetch_fundamentals)

    async def health_check(self) -> bool:
        """Verify that yfinance can reach Yahoo servers."""
        if not _YF_AVAILABLE:
            return False

        def _check() -> bool:
            try:
                ticker = yf.Ticker("AAPL")
                info = ticker.info
                return info is not None and len(info) > 0
            except Exception:
                return False

        return await asyncio.to_thread(_check)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _empty_quote(symbol: str) -> Quote:
        return Quote(
            symbol=symbol,
            bid=0.0,
            ask=0.0,
            last=0.0,
            volume=0.0,
            timestamp=datetime.now(timezone.utc),
            source="yahoo",
        )
