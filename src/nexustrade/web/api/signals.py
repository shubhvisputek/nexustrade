"""Agent signal endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory signal store (replaced by Redis in production)
_recent_signals: list[dict[str, Any]] = []


def store_signal(signal_dict: dict[str, Any]) -> None:
    """Store a signal in the in-memory buffer (called by the agent pipeline)."""
    _recent_signals.append(signal_dict)
    # Keep only the last 500 signals
    if len(_recent_signals) > 500:
        _recent_signals.pop(0)


@router.get("")
async def get_signals(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent agent signals."""
    return _recent_signals[-limit:]


@router.get("/{symbol}")
async def get_signals_by_symbol(symbol: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent agent signals filtered by symbol."""
    filtered = [
        s for s in _recent_signals
        if s.get("symbol", "").upper() == symbol.upper()
        or s.get("metadata", {}).get("symbol", "").upper() == symbol.upper()
    ]
    return filtered[-limit:]
