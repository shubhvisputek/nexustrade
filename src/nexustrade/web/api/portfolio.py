"""Portfolio endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory state (replaced by real broker + Redis in production)
_portfolio_state: dict[str, Any] = {
    "cash": 100_000.0,
    "positions": [],
    "total_value": 100_000.0,
    "daily_pnl": 0.0,
    "total_pnl": 0.0,
    "open_orders": [],
}

_trade_history: list[dict[str, Any]] = []


@router.get("")
async def get_portfolio() -> dict[str, Any]:
    """Return the current portfolio state."""
    return _portfolio_state


@router.get("/positions")
async def get_positions() -> list[dict[str, Any]]:
    """Return current open positions."""
    return _portfolio_state.get("positions", [])


@router.get("/history")
async def get_trade_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return trade execution history."""
    return _trade_history[-limit:]
