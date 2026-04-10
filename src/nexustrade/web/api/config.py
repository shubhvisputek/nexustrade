"""Configuration endpoints.

Exposes the current NexusTrade configuration (sanitized) and allows
runtime updates validated by Pydantic.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Patterns that indicate sensitive values (API keys, secrets, passwords)
_SENSITIVE_PATTERNS = re.compile(
    r"(api_key|secret|password|token|passphrase|credential)", re.IGNORECASE
)


def _sanitize(config: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask values whose keys look like secrets."""
    sanitized: dict[str, Any] = {}
    for key, value in config.items():
        if _SENSITIVE_PATTERNS.search(key):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize(value)
        else:
            sanitized[key] = value
    return sanitized


# In-memory config store (loaded from YAML in production)
_current_config: dict[str, Any] = {
    "version": "0.1.0",
    "llm": {"mode": "local", "provider": "ollama", "model": "llama3:8b"},
    "execution": {"mode": "paper"},
    "risk": {"max_position_pct": 0.05, "max_loss_pct": 0.02},
}


class ConfigUpdate(BaseModel):
    """Partial config update payload."""

    config: dict[str, Any]


@router.get("")
async def get_config() -> dict[str, Any]:
    """Return the current configuration with sensitive values redacted."""
    return _sanitize(_current_config)


@router.put("")
async def update_config(payload: ConfigUpdate) -> dict[str, Any]:
    """Update configuration at runtime.

    Merges the provided keys into the current config.
    Sensitive keys are rejected to prevent accidental exposure.
    """
    for key in payload.config:
        if _SENSITIVE_PATTERNS.search(key):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot set sensitive key '{key}' via API. Use .env instead.",
            )

    # Shallow merge (top-level keys only for safety)
    _current_config.update(payload.config)
    logger.info("Config updated: %s", list(payload.config.keys()))
    return _sanitize(_current_config)
