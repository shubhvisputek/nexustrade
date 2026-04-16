"""Market data endpoints — quotes and bars."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException

from nexustrade.runtime.state import get_runtime_state

router = APIRouter()


@router.get("/{symbol}/quote")
async def get_quote(symbol: str, provider: str = "yahoo") -> dict[str, Any]:
    state = get_runtime_state()
    cached = state.latest_quote.get(symbol.upper())
    if cached:
        return cached

    # Fetch fresh
    if provider == "yahoo":
        from nexustrade.data.adapters.yahoo import YahooFinanceAdapter
        adapter = YahooFinanceAdapter({})
    else:
        raise HTTPException(400, f"Unknown provider: {provider}")
    try:
        q = await adapter.get_quote(symbol.upper())
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    if q.last <= 0:
        raise HTTPException(404, f"No quote available for {symbol}")
    payload = q.to_dict()
    state.update_quote(symbol.upper(), payload)
    return payload


@router.get("/{symbol}/bars")
async def get_bars(
    symbol: str,
    timeframe: str = "1d",
    days: int = 90,
    provider: str = "yahoo",
) -> list[dict[str, Any]]:
    if provider == "yahoo":
        from nexustrade.data.adapters.yahoo import YahooFinanceAdapter
        adapter = YahooFinanceAdapter({})
    else:
        raise HTTPException(400, f"Unknown provider: {provider}")
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    try:
        bars = await adapter.get_ohlcv(symbol.upper(), timeframe, start, end)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return [b.to_dict() for b in bars]
