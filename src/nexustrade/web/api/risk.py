"""Risk endpoints — assessments, circuit breaker, kill switch."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from nexustrade.runtime.state import get_runtime_state

router = APIRouter()


@router.get("")
async def risk_status() -> dict[str, Any]:
    state = get_runtime_state()
    return {
        "kill_switch_engaged": state.kill_switch_engaged,
        "is_paused": state.is_paused,
        **state.risk_status,
    }


@router.get("/assessments")
async def risk_assessments(
    limit: int = 200, symbol: str | None = None
) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.risk_assessments)
    if symbol:
        s = symbol.upper()
        items = [a for a in items if a.symbol.upper() == s]
    return [asdict(a) for a in items[-limit:]]
