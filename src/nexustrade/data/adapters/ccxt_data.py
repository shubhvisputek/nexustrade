"""CCXT data adapter for cryptocurrency market data.

Wraps the CCXT library to provide unified access to 100+ crypto exchanges.
CCXT is an optional dependency — the adapter gracefully handles its absence.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from nexustrade.core.interfaces import DataProviderInterface
from nexustrade.core.models import OHLCV, Quote

logger = logging.getLogger(__name__)

try:
    import ccxt as _ccxt

    _CCXT_AVAILABLE = True
except ImportError:
    _ccxt = None  # type: ignore[assignment]
    _CCXT_AVAILABLE = False


class CCXTDataAdapter(DataProviderInterface):
    """Cryptocurrency data adapter powered by CCXT.

    Parameters
    ----------
    exchange_id:
        CCXT exchange identifier (e.g. ``"binance"``, ``"coinbase"``).
    config:
        Extra kwargs forwarded to the CCXT exchange constructor
        (API keys, sandbox mode, rate-limit overrides, etc.).
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        config: dict[str, Any] | None = None,
    ) -> None:
        if not _CCXT_AVAILABLE:
            raise ImportError(
                "ccxt is not installed. Install it with: pip install ccxt"
            )
        self._exchange_id = exchange_id
        self._config = config or {}
        exchange_class = getattr(_ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unknown CCXT exchange: {exchange_id}")
        self._exchange = exchange_class(self._config)

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "ccxt"

    @property
    def supported_markets(self) -> list[str]:
        return ["crypto"]

    # -- required methods ----------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCV]:
        """Fetch OHLCV bars from the exchange.

        CCXT returns rows as ``[timestamp_ms, open, high, low, close, volume]``.
        We convert each row into a canonical :class:`OHLCV` model.
        """
        since_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        all_bars: list[OHLCV] = []
        current_since = since_ms

        while current_since < end_ms:
            raw = await asyncio.to_thread(
                self._exchange.fetch_ohlcv,
                symbol,
                timeframe,
                current_since,
                500,  # default page size
            )
            if not raw:
                break

            for row in raw:
                ts_ms, o, h, l, c, v = row[:6]
                if ts_ms > end_ms:
                    break
                bar = OHLCV(
                    timestamp=datetime.fromtimestamp(
                        ts_ms / 1000, tz=timezone.utc
                    ),
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(v),
                    symbol=symbol,
                    timeframe=timeframe,
                    source=f"ccxt:{self._exchange_id}",
                )
                all_bars.append(bar)

            # Move the cursor past the last bar we received.
            last_ts = raw[-1][0]
            if last_ts <= current_since:
                break  # no progress — avoid infinite loop
            current_since = last_ts + 1

        return all_bars

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch the latest ticker for *symbol* and convert to :class:`Quote`."""
        ticker = await asyncio.to_thread(
            self._exchange.fetch_ticker, symbol
        )
        return Quote(
            symbol=symbol,
            bid=float(ticker.get("bid") or 0.0),
            ask=float(ticker.get("ask") or 0.0),
            last=float(ticker.get("last") or 0.0),
            volume=float(ticker.get("baseVolume") or 0.0),
            timestamp=datetime.fromtimestamp(
                (ticker.get("timestamp") or 0) / 1000, tz=timezone.utc
            ),
            source=f"ccxt:{self._exchange_id}",
        )

    # -- optional overrides --------------------------------------------------

    async def health_check(self) -> bool:
        """Check if the exchange API is reachable."""
        try:
            await asyncio.to_thread(self._exchange.fetch_time)
            return True
        except Exception:
            logger.warning(
                "CCXT health check failed for %s", self._exchange_id
            )
            return False
