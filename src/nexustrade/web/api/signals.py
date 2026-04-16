"""Agent signal endpoints — read recent reasoning traces from RuntimeState.

For backwards compatibility this module also exposes :func:`store_signal`,
which is now a thin shim that records into the runtime state's signal
buffer.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from nexustrade.runtime.state import ReasoningTrace, get_runtime_state

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def get_signals(limit: int = 100) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.signals)[-limit:]
    return [asdict(s) for s in items]


@router.get("/{symbol}")
async def get_signals_by_symbol(symbol: str, limit: int = 100) -> list[dict[str, Any]]:
    state = get_runtime_state()
    s = symbol.upper()
    items = [t for t in state.signals if t.symbol.upper() == s][-limit:]
    return [asdict(t) for t in items]


def store_signal(signal_dict: dict[str, Any]) -> None:
    """Backwards-compatible shim — write into the runtime state buffer."""
    state = get_runtime_state()
    trace = ReasoningTrace(
        timestamp=signal_dict.get("timestamp") or "",
        symbol=signal_dict.get("symbol", ""),
        agent_name=signal_dict.get("agent_name", "unknown"),
        agent_type=signal_dict.get("agent_type", "generic"),
        direction=signal_dict.get("direction", "hold"),
        confidence=float(signal_dict.get("confidence", 0.0)),
        reasoning=signal_dict.get("reasoning", ""),
        metadata=signal_dict.get("metadata", {}) or {},
    )
    state.signals.append(trace)
