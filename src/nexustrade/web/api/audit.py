"""Audit log + alerts feed endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from nexustrade.runtime.state import get_runtime_state

router = APIRouter()


@router.get("/log")
async def audit_log(
    limit: int = 500,
    category: str | None = None,
    level: str | None = None,
) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.audit)
    if category:
        items = [e for e in items if e.category == category]
    if level:
        items = [e for e in items if e.level == level]
    return [asdict(e) for e in items[-limit:]]


@router.get("/alerts")
async def alerts(limit: int = 200) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.alerts)
    return [asdict(a) for a in items[-limit:]]


@router.get("/equity")
async def equity_curve(limit: int = 4096) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.equity_curve)
    return [asdict(p) for p in items[-limit:]]
