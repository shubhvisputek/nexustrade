"""Configuration endpoints — surface the active config and accept
runtime updates with deep-merge semantics.

The active config is the snapshot stored in :class:`RuntimeState` (set
by the orchestrator at startup) when available; otherwise a minimal
default. Updates are deep-merged so callers can patch nested keys
without clobbering siblings.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nexustrade.runtime.state import get_runtime_state

router = APIRouter()
logger = logging.getLogger(__name__)

_SENSITIVE_PATTERNS = re.compile(
    r"(api_key|secret|password|token|passphrase|credential)", re.IGNORECASE
)


def _sanitize(config: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in config.items():
        if _SENSITIVE_PATTERNS.search(str(key)):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize(value)
        else:
            sanitized[key] = value
    return sanitized


_DEFAULT_CONFIG: dict[str, Any] = {
    "version": "0.1.0",
    "llm": {"mode": "local", "provider": "ollama", "model": "llama3:8b"},
    "execution": {"mode": "paper"},
    "risk": {"max_position_pct": 0.05, "max_loss_pct": 0.02},
    "agents": {"enabled": [], "aggregation_mode": "weighted_confidence"},
    "markets": {},
    "notifications": {"channels": [], "events": {}},
}


def _get_active_config() -> dict[str, Any]:
    state = get_runtime_state()
    if state.config_snapshot:
        return state.config_snapshot
    return copy.deepcopy(_DEFAULT_CONFIG)


def _set_active_config(cfg: dict[str, Any]) -> None:
    state = get_runtime_state()
    state.config_snapshot = cfg


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _has_sensitive_keys(payload: dict[str, Any]) -> bool:
    for k, v in payload.items():
        if _SENSITIVE_PATTERNS.search(str(k)):
            return True
        if isinstance(v, dict) and _has_sensitive_keys(v):
            return True
    return False


class ConfigUpdate(BaseModel):
    config: dict[str, Any]


@router.get("")
async def get_config() -> dict[str, Any]:
    return _sanitize(_get_active_config())


@router.put("")
async def update_config(payload: ConfigUpdate) -> dict[str, Any]:
    """Deep-merge the provided config into the active config.

    Sensitive keys are rejected outright.
    """
    if _has_sensitive_keys(payload.config):
        raise HTTPException(
            status_code=400,
            detail="Cannot set sensitive keys via API. Use environment variables.",
        )
    merged = _deep_merge(_get_active_config(), payload.config)
    _set_active_config(merged)
    state = get_runtime_state()
    state.record_audit("config", "info", f"Config patched: {list(payload.config.keys())}")
    logger.info("Config updated: %s", list(payload.config.keys()))
    return _sanitize(merged)


@router.get("/raw")
async def get_raw_config() -> dict[str, Any]:
    """Return the active config WITHOUT redaction.

    Use only on trusted networks; sensitive keys are never written by
    update endpoints, but environment-derived keys may still be present.
    """
    return _get_active_config()
