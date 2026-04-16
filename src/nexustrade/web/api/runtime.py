"""Runtime control endpoints — start/stop/tick the paper trading loop.

Lets the dashboard kick the orchestrator on demand. In production the
loop typically runs as a long-running background task spawned from the
``nexus paper`` CLI; in the HF Spaces demo we expose start/stop and a
manual ``/tick`` button so visitors can trigger one cycle without
waiting for the scheduler.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nexustrade.runtime.paper_loop import (
    get_or_create_loop,
    get_running_loop,
)
from nexustrade.runtime.state import get_runtime_state

router = APIRouter()
logger = logging.getLogger(__name__)


class StartPayload(BaseModel):
    config_path: str = "config/demo.yaml"


@router.get("")
async def runtime_snapshot() -> dict[str, Any]:
    """Return a top-level snapshot of the runtime state."""
    state = get_runtime_state()
    snapshot = state.snapshot()
    snapshot["loop_running"] = bool(get_running_loop() and get_running_loop().is_running)
    return snapshot


@router.post("/start")
async def runtime_start(payload: StartPayload) -> dict[str, Any]:
    """Boot the paper-trading loop with the given config."""
    from nexustrade.core.config import load_config

    try:
        cfg = load_config(payload.config_path)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"Config not found: {payload.config_path}") from exc
    except Exception as exc:
        raise HTTPException(400, f"Invalid config: {exc}") from exc

    loop = await get_or_create_loop(cfg, config_path=payload.config_path)
    if not loop.is_running:
        await loop.start()
    return {"status": "started", "config_path": payload.config_path}


@router.post("/stop")
async def runtime_stop() -> dict[str, Any]:
    loop = get_running_loop()
    if loop is None:
        raise HTTPException(400, "Loop is not running")
    await loop.stop()
    return {"status": "stopped"}


@router.post("/pause")
async def runtime_pause(reason: str = "manual") -> dict[str, Any]:
    state = get_runtime_state()
    state.pause(reason=reason)
    return {"status": "paused", "reason": reason}


@router.post("/resume")
async def runtime_resume() -> dict[str, Any]:
    state = get_runtime_state()
    state.resume()
    return {"status": "resumed"}


@router.post("/kill-switch")
async def runtime_kill_switch(reason: str = "manual") -> dict[str, Any]:
    """Engage the kill switch — pauses the loop and blocks all orders."""
    state = get_runtime_state()
    state.engage_kill_switch(reason=reason)
    return {"status": "kill_switch_engaged", "reason": reason}


@router.post("/kill-switch/release")
async def runtime_kill_switch_release() -> dict[str, Any]:
    state = get_runtime_state()
    state.disengage_kill_switch()
    return {"status": "kill_switch_released"}


@router.post("/tick")
async def runtime_tick() -> dict[str, Any]:
    """Run one orchestrator tick on demand."""
    loop = get_running_loop()
    if loop is None:
        raise HTTPException(400, "Loop is not running. POST /runtime/start first.")
    summary = await loop.tick_once()
    return {
        "correlation_id": summary.correlation_id,
        "symbols": summary.symbols,
        "signals_emitted": summary.signals_emitted,
        "composite_signals": summary.composite_signals,
        "orders_placed": summary.orders_placed,
        "orders_blocked": summary.orders_blocked,
        "duration_ms": summary.duration_ms,
        "error": summary.error,
    }


@router.get("/ticks")
async def runtime_ticks(limit: int = 50) -> list[dict[str, Any]]:
    state = get_runtime_state()
    items = list(state.ticks)[-limit:]
    return [_asdict(t) for t in items]


def _asdict(obj: Any) -> dict[str, Any]:
    from dataclasses import asdict, is_dataclass

    if is_dataclass(obj):
        return asdict(obj)
    return dict(obj)
