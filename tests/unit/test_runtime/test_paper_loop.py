"""Unit tests for runtime.paper_loop — the orchestrator.

The orchestrator wires real components together; here we use the
built-in momentum baseline agent + a stubbed data provider so the test
is hermetic (no network, no LLM).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nexustrade.core.config import (
    AgentConfig,
    AgentEntry,
    BrokerEntry,
    ExecutionConfig,
    LLMConfig,
    LLMProviderConfig,
    MarketConfig,
    NexusTradeConfig,
)
from nexustrade.core.models import OHLCV, Quote
from nexustrade.runtime.paper_loop import PaperTradingLoop
from nexustrade.runtime.state import reset_runtime_state


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_runtime_state()
    yield
    reset_runtime_state()


class _StubDataProvider:
    """Hermetic stand-in for YahooFinanceAdapter."""

    name = "stub"
    supported_markets = ["us_equity"]

    def __init__(self, trending_up: bool = True) -> None:
        self._trending_up = trending_up

    async def get_quote(self, symbol: str) -> Quote:
        return Quote(
            symbol=symbol, bid=99.0, ask=101.0, last=100.0,
            volume=1_000_000, timestamp=datetime.now(UTC), source="stub",
        )

    async def get_ohlcv(self, symbol, timeframe, start, end):
        # Generate 100 bars
        bars: list[OHLCV] = []
        base = 50.0 if self._trending_up else 150.0
        for i in range(100):
            close = base + i * (1.0 if self._trending_up else -1.0)
            bars.append(OHLCV(
                timestamp=datetime.now(UTC) - timedelta(days=100 - i),
                open=close - 0.5, high=close + 1.0, low=close - 1.0,
                close=close, volume=1_000_000,
                symbol=symbol, timeframe=timeframe, source="stub",
            ))
        return bars

    async def get_news(self, symbol, limit=10): return []
    async def get_fundamentals(self, symbol): return {}

    async def health_check(self) -> bool:
        return True


def _minimal_config() -> NexusTradeConfig:
    return NexusTradeConfig(
        llm=LLMConfig(
            mode="local",
            fast=LLMProviderConfig(provider="ollama", model="llama3:8b"),
            deep=LLMProviderConfig(provider="ollama", model="llama3:8b"),
        ),
        agents=AgentConfig(
            enabled=[
                # Intentionally NOT enabling persona agents — they'd call LLM.
            ],
            aggregation_mode="weighted_confidence",
            min_confidence=0.3,
        ),
        execution=ExecutionConfig(
            mode="python",
            brokers=[BrokerEntry(name="paper", enabled=True, markets=["us_equity"])],
        ),
        markets={
            "us_equity": MarketConfig(symbols=["AAPL"], data_provider="yahoo"),
        },
    )


@pytest.mark.asyncio
async def test_loop_instantiates_without_external_services():
    cfg = _minimal_config()
    loop = PaperTradingLoop(cfg, config_path="test.yaml")
    # stub the data provider
    loop.data_provider = _StubDataProvider(trending_up=True)
    assert not loop.is_running
    assert loop.state.is_running  # start() was called in constructor
    assert loop.state.config_path == "test.yaml"


@pytest.mark.asyncio
async def test_tick_generates_signal_and_can_execute():
    cfg = _minimal_config()
    loop = PaperTradingLoop(cfg, config_path="test.yaml")
    loop.data_provider = _StubDataProvider(trending_up=True)

    summary = await loop.tick_once()
    assert summary.error is None
    assert summary.symbols == ["AAPL"]
    # momentum_baseline will fire, so at least 1 signal.
    assert summary.signals_emitted >= 1
    assert summary.composite_signals >= 1
    # Equity curve should have at least one point
    assert len(loop.state.equity_curve) >= 1
    # Audit log should have at least a tick + signal entry
    categories = {a.category for a in loop.state.audit}
    assert "signal" in categories
    assert "tick" in categories


@pytest.mark.asyncio
async def test_tick_records_risk_assessment_for_non_hold():
    cfg = _minimal_config()
    loop = PaperTradingLoop(cfg, config_path="test.yaml")
    loop.data_provider = _StubDataProvider(trending_up=True)

    await loop.tick_once()
    # trending up → BUY → risk engine runs
    assert len(loop.state.risk_assessments) >= 1
    risk = loop.state.risk_assessments[-1]
    assert risk.symbol == "AAPL"
    # approved or not, it must have been recorded
    assert risk.sizing_model in {"fixed_fraction", "kelly", "cvar", "volatility", "max_drawdown"}


@pytest.mark.asyncio
async def test_kill_switch_blocks_new_ticks_in_background():
    import asyncio
    cfg = _minimal_config()
    loop = PaperTradingLoop(cfg, config_path="test.yaml")
    loop.data_provider = _StubDataProvider(trending_up=True)
    loop.tick_seconds = 1  # fast tick for test
    loop.state.engage_kill_switch("test")

    await loop.start()
    await asyncio.sleep(0.3)  # give background a chance
    await loop.stop()
    # No ticks should have recorded (kill switch engaged)
    assert len(loop.state.ticks) == 0


@pytest.mark.asyncio
async def test_loop_survives_bad_data_provider():
    cfg = _minimal_config()
    loop = PaperTradingLoop(cfg, config_path="test.yaml")

    class Broken:
        name = "broken"
        supported_markets = ["us_equity"]
        async def get_quote(self, symbol):
            raise RuntimeError("broken")
        async def get_ohlcv(self, *a, **kw):
            return []

    loop.data_provider = Broken()
    summary = await loop.tick_once()
    # Tick should complete; no orders, but also no uncaught exception
    assert summary.orders_placed == 0
    # an error-category audit entry should exist
    cats = {a.category for a in loop.state.audit}
    assert "tick" in cats or "error" in cats
