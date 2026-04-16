"""Agents endpoints — registered agents and reasoning traces."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from nexustrade.runtime.state import get_runtime_state

router = APIRouter()


@router.get("")
async def list_agents() -> list[dict[str, Any]]:
    state = get_runtime_state()
    return list(state.agents)


@router.get("/reasoning")
async def list_reasoning(
    limit: int = 200, symbol: str | None = None, agent: str | None = None
) -> list[dict[str, Any]]:
    """Return recent agent reasoning traces, optionally filtered."""
    state = get_runtime_state()
    items = list(state.signals)
    if symbol:
        s = symbol.upper()
        items = [t for t in items if t.symbol.upper() == s]
    if agent:
        a = agent.lower()
        items = [t for t in items if t.agent_name.lower() == a]
    return [asdict(t) for t in items[-limit:]]


@router.get("/composites")
async def list_composites(limit: int = 100, symbol: str | None = None) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.composite_signals)
    if symbol:
        s = symbol.upper()
        items = [t for t in items if t.symbol.upper() == s]
    return [asdict(t) for t in items[-limit:]]
