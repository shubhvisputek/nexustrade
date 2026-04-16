"""NexusTrade FastAPI application.

Aggregates every API router, exposes the Prometheus ``/metrics`` scrape
endpoint, and adds CORS so the Streamlit dashboard can talk to it from
either the same container or a different origin during development.

When the env var ``NEXUSTRADE_AUTOSTART_LOOP`` is set, the FastAPI
``lifespan`` boots the paper-trading orchestrator at startup using
``NEXUSTRADE_CONFIG`` (defaults to ``config/demo.yaml``). This is what
makes the Hugging Face Spaces demo "just work" — visitors hit the URL
and the loop is already ticking with mock data.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from nexustrade.web.api.agents import router as agents_router
from nexustrade.web.api.audit import router as audit_router
from nexustrade.web.api.backtest import router as backtest_router
from nexustrade.web.api.config import router as config_router
from nexustrade.web.api.health import router as health_router
from nexustrade.web.api.markets import router as markets_router
from nexustrade.web.api.orders import router as orders_router
from nexustrade.web.api.portfolio import router as portfolio_router
from nexustrade.web.api.risk import router as risk_router
from nexustrade.web.api.runtime import router as runtime_router
from nexustrade.web.api.signals import router as signals_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — optionally autostart the paper trading loop."""
    autostart = os.environ.get("NEXUSTRADE_AUTOSTART_LOOP", "").lower() in {
        "1", "true", "yes", "on"
    }
    config_path = os.environ.get("NEXUSTRADE_CONFIG", "config/demo.yaml")

    if autostart:
        try:
            from nexustrade.core.config import load_config
            from nexustrade.runtime.paper_loop import get_or_create_loop

            cfg = load_config(config_path)
            loop = await get_or_create_loop(cfg, config_path=config_path)
            await loop.start()
            logger.info(
                "Auto-started paper trading loop with config: %s", config_path
            )
        except Exception:
            logger.exception(
                "Failed to autostart loop with config: %s", config_path
            )
    yield

    # Shutdown — stop the loop cleanly.
    try:
        from nexustrade.runtime.paper_loop import get_running_loop

        loop = get_running_loop()
        if loop is not None and loop.is_running:
            await loop.stop()
            logger.info("Stopped paper trading loop on shutdown")
    except Exception:
        logger.exception("Failed to stop loop on shutdown")


app = FastAPI(
    title="NexusTrade API",
    version="0.2.0",
    description="Unified open-source LLM trading platform — REST API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers -------------------------------------------------------------

app.include_router(health_router, tags=["health"])
app.include_router(signals_router, prefix="/signals", tags=["signals"])
app.include_router(portfolio_router, prefix="/portfolio", tags=["portfolio"])
app.include_router(config_router, prefix="/config", tags=["config"])
app.include_router(runtime_router, prefix="/runtime", tags=["runtime"])
app.include_router(orders_router, prefix="/orders", tags=["orders"])
app.include_router(agents_router, prefix="/agents", tags=["agents"])
app.include_router(risk_router, prefix="/risk", tags=["risk"])
app.include_router(audit_router, prefix="/audit", tags=["audit"])
app.include_router(backtest_router, prefix="/backtest", tags=["backtest"])
app.include_router(markets_router, prefix="/markets", tags=["markets"])


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": "NexusTrade API",
        "version": app.version,
        "docs": "/docs",
        "metrics": "/metrics",
    }


@app.get("/metrics", tags=["observability"])
async def prometheus_metrics() -> PlainTextResponse:
    """Prometheus metrics scraping endpoint."""
    from nexustrade.core.metrics import MetricsCollector

    return PlainTextResponse(
        MetricsCollector.get().get_metrics_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
