"""Portfolio endpoints — read account, positions, and trade history
from :class:`RuntimeState`.

Falls back to a sensible empty snapshot when no orchestrator has been
started yet (so the dashboard can render before the first tick).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from nexustrade.runtime.state import get_runtime_state

router = APIRouter()
logger = logging.getLogger(__name__)


def _empty_account() -> dict[str, Any]:
    return {
        "cash": 0.0,
        "positions_value": 0.0,
        "total_value": 0.0,
        "total_pnl": 0.0,
        "daily_pnl": 0.0,
        "initial_cash": 0.0,
        "num_positions": 0,
        "num_trades": 0,
    }


@router.get("")
async def get_portfolio() -> dict[str, Any]:
    """Return the current portfolio state."""
    state = get_runtime_state()
    account = state.account or _empty_account()
    return {
        **account,
        "positions": [_position_dict(p) for p in state.positions],
        "open_orders": [_order_dict(o) for o in state.open_orders],
    }


@router.get("/positions")
async def get_positions() -> list[dict[str, Any]]:
    state = get_runtime_state()
    return [_position_dict(p) for p in state.positions]


@router.get("/history")
async def get_trade_history(limit: int = 200) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.fills)[-limit:]
    return [asdict(f) for f in items]


@router.get("/equity")
async def get_equity_curve(limit: int = 4096) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.equity_curve)[-limit:]
    return [asdict(p) for p in items]


def _position_dict(p: Any) -> dict[str, Any]:
    if hasattr(p, "to_dict"):
        return p.to_dict()
    if hasattr(p, "__dataclass_fields__"):
        return asdict(p)
    if isinstance(p, dict):
        return p
    return {"raw": str(p)}


def _order_dict(o: Any) -> dict[str, Any]:
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if hasattr(o, "__dataclass_fields__"):
        return asdict(o)
    if isinstance(o, dict):
        return o
    return {"raw": str(o)}
