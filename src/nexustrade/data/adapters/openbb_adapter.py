"""OpenBB Platform data adapter.

Wraps the ``openbb`` SDK to provide OHLCV bars, quotes, news,
fundamentals, and technical indicators across multiple asset classes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from nexustrade.core.interfaces import DataProviderInterface
from nexustrade.core.models import OHLCV, NewsItem, Quote, TechnicalIndicators

logger = logging.getLogger(__name__)

# Attempt to import openbb; adapter degrades gracefully if absent.
try:
    from openbb import obb  # type: ignore[import-untyped]

    _OBB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OBB_AVAILABLE = False
    obb = None  # type: ignore[assignment]


class OpenBBAdapter(DataProviderInterface):
    """Data provider backed by the OpenBB Platform.

    Parameters
    ----------
    config:
        Optional configuration dict.  Recognised keys:

        * ``sub_provider`` -- upstream data vendor for OpenBB to use
          (e.g. ``"fmp"``, ``"polygon"``, ``"yfinance"``).  Falls back
          to OpenBB's default when omitted.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._sub_provider: str | None = self._config.get("sub_provider")

    # -- identity ------------------------------------------------------------

    @property
    def name(self) -> str:
        return "openbb"

    @property
    def supported_markets(self) -> list[str]:
        return [
            "us_equity",
            "india_equity",
            "forex",
            "crypto",
            "options",
            "commodity",
        ]

    # -- required ------------------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCV]:
        """Download OHLCV bars via OpenBB."""
        if not _OBB_AVAILABLE:
            logger.warning("openbb is not installed; returning empty OHLCV")
            return []

        def _download() -> list[OHLCV]:
            try:
                kwargs: dict[str, Any] = {
                    "symbol": symbol,
                    "start_date": start.strftime("%Y-%m-%d"),
                    "end_date": end.strftime("%Y-%m-%d"),
                }
                if self._sub_provider:
                    kwargs["provider"] = self._sub_provider

                result = obb.equity.price.historical(**kwargs)
                df = result.to_dataframe()  # type: ignore[union-attr]

                if df is None or df.empty:
                    return []

                bars: list[OHLCV] = []
                for idx, row in df.iterrows():
                    # OpenBB typically returns a DatetimeIndex or a 'date' col
                    if hasattr(idx, "to_pydatetime"):
                        bar_ts = idx.to_pydatetime()
                    elif isinstance(idx, datetime):
                        bar_ts = idx
                    else:
                        # idx might be an integer; fall back to 'date' column
                        raw_date = row.get("date", idx)
                        if isinstance(raw_date, str):
                            bar_ts = datetime.fromisoformat(raw_date)
                        elif hasattr(raw_date, "to_pydatetime"):
                            bar_ts = raw_date.to_pydatetime()
                        else:
                            bar_ts = datetime.now(timezone.utc)

                    if bar_ts.tzinfo is None:
                        bar_ts = bar_ts.replace(tzinfo=timezone.utc)
                    else:
                        bar_ts = bar_ts.astimezone(timezone.utc)

                    bars.append(
                        OHLCV(
                            timestamp=bar_ts,
                            open=float(row.get("open", 0.0)),
                            high=float(row.get("high", 0.0)),
                            low=float(row.get("low", 0.0)),
                            close=float(row.get("close", 0.0)),
                            volume=float(row.get("volume", 0.0)),
                            symbol=symbol,
                            timeframe=timeframe,
                            source=self.name,
                        )
                    )
                return bars
            except Exception:
                logger.exception("OpenBB OHLCV fetch failed for %s", symbol)
                return []

        return await asyncio.to_thread(_download)

    async def get_quote(self, symbol: str) -> Quote:
        """Return the latest quote via OpenBB."""
        if not _OBB_AVAILABLE:
            logger.warning("openbb is not installed; returning stub Quote")
            return self._empty_quote(symbol)

        def _fetch_quote() -> Quote:
            try:
                kwargs: dict[str, Any] = {"symbol": symbol}
                if self._sub_provider:
                    kwargs["provider"] = self._sub_provider

                result = obb.equity.price.quote(**kwargs)
                data = result.to_dataframe()  # type: ignore[union-attr]

                if data is None or data.empty:
                    return self._empty_quote(symbol)

                row = data.iloc[0]
                last = float(
                    row.get("last_price")
                    or row.get("price")
                    or row.get("close")
                    or 0.0
                )
                bid = float(row.get("bid", 0.0) or 0.0)
                ask = float(row.get("ask", 0.0) or 0.0)
                volume = float(row.get("volume", 0.0) or 0.0)

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
                logger.exception("OpenBB quote fetch failed for %s", symbol)
                return self._empty_quote(symbol)

        return await asyncio.to_thread(_fetch_quote)

    # -- optional overrides --------------------------------------------------

    async def get_news(
        self,
        symbol: str,
        limit: int = 10,
    ) -> list[NewsItem]:
        """Return recent news items via OpenBB."""
        if not _OBB_AVAILABLE:
            return []

        def _fetch_news() -> list[NewsItem]:
            try:
                kwargs: dict[str, Any] = {"symbols": symbol, "limit": limit}
                if self._sub_provider:
                    kwargs["provider"] = self._sub_provider

                try:
                    result = obb.news.company(**kwargs)
                except (AttributeError, TypeError):
                    # Fall back to world news filtered by symbol
                    result = obb.news.world(**kwargs)

                df = result.to_dataframe()  # type: ignore[union-attr]
                if df is None or df.empty:
                    return []

                items: list[NewsItem] = []
                for _, row in df.iterrows():
                    raw_date = row.get("date") or row.get("published")
                    if isinstance(raw_date, str):
                        ts = datetime.fromisoformat(raw_date)
                    elif hasattr(raw_date, "to_pydatetime"):
                        ts = raw_date.to_pydatetime()
                    elif isinstance(raw_date, datetime):
                        ts = raw_date
                    else:
                        ts = datetime.now(timezone.utc)

                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)

                    items.append(
                        NewsItem(
                            timestamp=ts,
                            headline=str(row.get("title", "")),
                            source=str(row.get("source", "openbb")),
                            symbols=[symbol],
                            body=str(row.get("text", "")) or None,
                            url=str(row.get("url", "")) or None,
                        )
                    )
                return items[:limit]
            except Exception:
                logger.exception("OpenBB news fetch failed for %s", symbol)
                return []

        return await asyncio.to_thread(_fetch_news)

    async def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Return fundamental data via OpenBB."""
        if not _OBB_AVAILABLE:
            return {}

        def _fetch_fundamentals() -> dict[str, Any]:
            try:
                kwargs: dict[str, Any] = {"symbol": symbol}
                if self._sub_provider:
                    kwargs["provider"] = self._sub_provider

                result = obb.equity.fundamental.overview(**kwargs)
                df = result.to_dataframe()  # type: ignore[union-attr]

                if df is None or df.empty:
                    return {}

                row = df.iloc[0]
                return {
                    k: v
                    for k, v in row.to_dict().items()
                    if v is not None and str(v) != "nan"
                }
            except Exception:
                logger.exception(
                    "OpenBB fundamentals fetch failed for %s", symbol
                )
                return {}

        return await asyncio.to_thread(_fetch_fundamentals)

    async def get_technicals(
        self,
        symbol: str,
        timeframe: str,
    ) -> TechnicalIndicators | None:
        """Attempt to retrieve technical indicators via OpenBB.

        OpenBB's technical analysis module availability depends on the
        installed extensions.  Returns ``None`` if unavailable.
        """
        if not _OBB_AVAILABLE:
            return None

        def _fetch_technicals() -> TechnicalIndicators | None:
            try:
                # Fetch recent OHLCV first, then compute indicators
                hist_kwargs: dict[str, Any] = {"symbol": symbol}
                if self._sub_provider:
                    hist_kwargs["provider"] = self._sub_provider

                result = obb.equity.price.historical(**hist_kwargs)
                df = result.to_dataframe()  # type: ignore[union-attr]

                if df is None or df.empty:
                    return None

                # Use openbb's technical analysis if available
                indicators: dict[str, float | None] = {}
                ta = getattr(obb, "technical", None)
                if ta is not None:
                    try:
                        rsi_result = ta.rsi(data=df)
                        rsi_df = rsi_result.to_dataframe()
                        if not rsi_df.empty:
                            indicators["rsi"] = float(rsi_df.iloc[-1].get("RSI_14", 0))
                    except Exception:
                        pass

                    try:
                        macd_result = ta.macd(data=df)
                        macd_df = macd_result.to_dataframe()
                        if not macd_df.empty:
                            last_row = macd_df.iloc[-1]
                            indicators["macd"] = float(last_row.get("MACD_12_26_9", 0))
                            indicators["macd_signal"] = float(
                                last_row.get("MACDs_12_26_9", 0)
                            )
                            indicators["macd_histogram"] = float(
                                last_row.get("MACDh_12_26_9", 0)
                            )
                    except Exception:
                        pass

                return TechnicalIndicators(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=datetime.now(timezone.utc),
                    rsi=indicators.get("rsi"),
                    macd=indicators.get("macd"),
                    macd_signal=indicators.get("macd_signal"),
                    macd_histogram=indicators.get("macd_histogram"),
                    source=self.name,
                )
            except Exception:
                logger.exception(
                    "OpenBB technicals fetch failed for %s", symbol
                )
                return None

        return await asyncio.to_thread(_fetch_technicals)

    async def health_check(self) -> bool:
        """Verify that OpenBB SDK is reachable."""
        if not _OBB_AVAILABLE:
            return False

        def _check() -> bool:
            try:
                result = obb.equity.price.quote(symbol="AAPL")
                return result is not None
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
            source="openbb",
        )
