"""Order endpoints — list and submit manual orders.

Replaces the dashboard's old call to a non-existent ``/webhook/order``
route. Manual orders go through the same risk-aware execution path as
orchestrated orders.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nexustrade.runtime.paper_loop import submit_manual_order
from nexustrade.runtime.state import get_runtime_state

router = APIRouter()
logger = logging.getLogger(__name__)


class ManualOrderPayload(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell|BUY|SELL)$")
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    market: str = "us_equity"


@router.get("")
async def list_orders(limit: int = 200) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.orders)[-limit:]
    return [asdict(o) for o in items]


@router.get("/fills")
async def list_fills(limit: int = 200) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.fills)[-limit:]
    return [asdict(f) for f in items]


@router.post("/manual")
async def submit_order(payload: ManualOrderPayload) -> dict[str, Any]:
    """Submit a manual order via the running paper broker."""
    try:
        result = await submit_manual_order(
            symbol=payload.symbol.upper(),
            side=payload.side.lower(),
            quantity=payload.quantity,
            price=payload.price,
            market=payload.market,
        )
        return {"status": "filled", **result}
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
