"""Health check endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Return overall service health status."""
    services: dict[str, str] = {}

    # Check Redis
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url("redis://localhost:6379")
        await r.ping()
        services["redis"] = "ok"
        await r.aclose()
    except Exception:
        services["redis"] = "unavailable"

    # Check LLM (Ollama)
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            services["llm"] = "ok" if resp.status_code == 200 else "error"
    except Exception:
        services["llm"] = "unavailable"

    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"
    return {"status": overall, "services": services}


@router.get("/health/redis")
async def health_redis() -> dict[str, str]:
    """Check Redis connectivity."""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url("redis://localhost:6379")
        await r.ping()
        await r.aclose()
        return {"redis": "ok"}
    except Exception as exc:
        return {"redis": "unavailable", "error": str(exc)}


@router.get("/health/llm")
async def health_llm() -> dict[str, str]:
    """Check LLM (Ollama) availability."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                return {"llm": "ok"}
            return {"llm": "error", "status_code": str(resp.status_code)}
    except Exception as exc:
        return {"llm": "unavailable", "error": str(exc)}
