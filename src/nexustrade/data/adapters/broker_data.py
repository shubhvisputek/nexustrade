"""Broker data adapter for OpenAlgo-powered Indian broker data feeds.

Provides OHLCV and quote data from Indian exchanges (NSE/BSE) via the
OpenAlgo REST API running on localhost (or a remote instance).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from nexustrade.core.interfaces import DataProviderInterface
from nexustrade.core.models import OHLCV, Quote

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False


class BrokerDataAdapter(DataProviderInterface):
    """Indian market data via the OpenAlgo REST API.

    Parameters
    ----------
    host:
        Base URL of the OpenAlgo instance (e.g. ``"http://localhost:5000"``).
    api_key:
        OpenAlgo API key for authentication.
    """

    def __init__(
        self,
        host: str = "http://localhost:5000",
        api_key: str = "",
    ) -> None:
        if not _HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is not installed. Install it with: pip install httpx"
            )
        self._host = host.rstrip("/")
        self._api_key = api_key

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "broker_data"

    @property
    def supported_markets(self) -> list[str]:
        return ["india_equity", "india_fno"]

    # -- required methods ----------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCV]:
        """Fetch historical OHLCV data from OpenAlgo.

        Calls ``GET {host}/api/v1/history`` with query parameters.
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "exchange": "NSE",
            "timeframe": timeframe,
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
        }
        data = await self._get("/api/v1/history", params)
        if data is None:
            return []

        bars: list[OHLCV] = []
        records = data if isinstance(data, list) else data.get("data", [])
        for row in records:
            ts = row.get("timestamp") or row.get("date") or row.get("time")
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
            elif isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts / 1000, tz=UTC)
            else:
                continue

            bar = OHLCV(
                timestamp=dt,
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0)),
                symbol=symbol,
                timeframe=timeframe,
                source="broker_data:openalgo",
            )
            bars.append(bar)

        return bars

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch the latest quote from OpenAlgo.

        Calls ``GET {host}/api/v1/quote`` with query parameters.
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "exchange": "NSE",
        }
        data = await self._get("/api/v1/quote", params)
        if data is None:
            raise ConnectionError(
                f"Failed to fetch quote for {symbol} from OpenAlgo"
            )

        quote_data = data if not isinstance(data, dict) else data.get("data", data)
        return Quote(
            symbol=symbol,
            bid=float(quote_data.get("bid", 0)),
            ask=float(quote_data.get("ask", 0)),
            last=float(quote_data.get("ltp", 0) or quote_data.get("last", 0)),
            volume=float(quote_data.get("volume", 0)),
            timestamp=datetime.now(UTC),
            source="broker_data:openalgo",
        )

    # -- optional overrides --------------------------------------------------

    async def health_check(self) -> bool:
        """Check if the OpenAlgo instance is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._host}/")
                return resp.status_code == 200
        except Exception:
            logger.warning("OpenAlgo health check failed at %s", self._host)
            return False

    # -- internal helpers ----------------------------------------------------

    async def _get(
        self, path: str, params: dict[str, Any]
    ) -> Any | None:
        """Execute an authenticated GET request against OpenAlgo."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self._host}{path}",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "OpenAlgo request failed: %s %s -> %s",
                exc.request.method,
                exc.request.url,
                exc.response.status_code,
            )
            return None
        except httpx.ConnectError:
            logger.error(
                "Cannot connect to OpenAlgo at %s", self._host
            )
            return None
        except Exception:
            logger.exception("Unexpected error calling OpenAlgo")
            return None
