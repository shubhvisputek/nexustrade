"""NexusTrade FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI

from nexustrade.web.api.config import router as config_router
from nexustrade.web.api.health import router as health_router
from nexustrade.web.api.portfolio import router as portfolio_router
from nexustrade.web.api.signals import router as signals_router

app = FastAPI(
    title="NexusTrade API",
    version="0.1.0",
    description="Unified open-source LLM trading platform REST API.",
)

app.include_router(health_router, tags=["health"])
app.include_router(signals_router, prefix="/signals", tags=["signals"])
app.include_router(portfolio_router, prefix="/portfolio", tags=["portfolio"])
app.include_router(config_router, prefix="/config", tags=["config"])
