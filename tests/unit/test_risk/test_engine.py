"""Tests for the risk engine (full pipeline)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nexustrade.core.models import (
    CompositeSignal,
    PortfolioState,
    RiskAssessment,
    SignalDirection,
)
from nexustrade.risk.circuit_breaker import CircuitBreaker
from nexustrade.risk.debate import RiskDebate
from nexustrade.risk.engine import RiskEngine
from nexustrade.risk.pre_trade import PreTradeValidator
from nexustrade.risk.sizing.fixed_fraction import FixedFractionModel


pytestmark = pytest.mark.unit


def _make_signal(
    symbol: str = "AAPL",
    direction: SignalDirection = SignalDirection.BUY,
    confidence: float = 0.75,
) -> CompositeSignal:
    return CompositeSignal(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        contributing_signals=[],
        aggregation_mode="mean",
        reasoning="Test signal",
        timestamp=datetime.now(timezone.utc),
    )


def _make_portfolio(
    total_value: float = 100_000.0,
    daily_pnl: float = 0.0,
) -> PortfolioState:
    return PortfolioState(
        cash=total_value,
        positions=[],
        total_value=total_value,
        daily_pnl=daily_pnl,
        total_pnl=0.0,
        open_orders=[],
    )


class TestRiskEngine:
    @pytest.mark.asyncio
    async def test_full_pipeline_approved(self):
        """Composite signal through risk engine results in approved trade with stop-loss."""
        engine = RiskEngine(
            sizing_model=FixedFractionModel(),
            circuit_breaker=CircuitBreaker({"max_daily_loss_pct": 0.05}),
            debate=RiskDebate(),
            config={"risk_pct": 0.01, "atr_stop_multiple": 2.0, "atr_tp_multiple": 3.0},
        )

        signal = _make_signal(confidence=0.80)
        portfolio = _make_portfolio(total_value=100_000.0)
        market_data = {"current_price": 100.0, "atr": 2.0}

        result = await engine.assess(signal, portfolio, market_data)

        assert isinstance(result, RiskAssessment)
        assert result.approved is True
        assert result.position_size > 0
        assert result.stop_loss_price < 100.0  # BUY => stop below
        assert result.take_profit_price > 100.0
        assert result.risk_reward_ratio > 0
        assert result.max_loss_amount > 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks(self):
        """Circuit breaker triggers => trade rejected."""
        engine = RiskEngine(
            circuit_breaker=CircuitBreaker({"max_daily_loss_pct": 0.03}),
            config={},
        )

        signal = _make_signal()
        # -4% daily loss triggers 3% circuit breaker
        portfolio = _make_portfolio(total_value=100_000.0, daily_pnl=-4000.0)
        market_data = {"current_price": 100.0}

        result = await engine.assess(signal, portfolio, market_data)

        assert result.approved is False
        assert any("Circuit breaker" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_sell_signal_stop_above(self):
        """SELL signal => stop-loss above current price."""
        engine = RiskEngine(
            sizing_model=FixedFractionModel(),
            config={"risk_pct": 0.01, "atr_stop_multiple": 2.0, "atr_tp_multiple": 3.0},
        )

        signal = _make_signal(direction=SignalDirection.SELL, confidence=0.70)
        portfolio = _make_portfolio()
        market_data = {"current_price": 100.0, "atr": 2.0}

        result = await engine.assess(signal, portfolio, market_data)

        assert result.approved is True
        assert result.stop_loss_price > 100.0  # SELL => stop above
        assert result.take_profit_price < 100.0

    @pytest.mark.asyncio
    async def test_debate_summary_included(self):
        """Risk debate summary is included in the assessment."""
        engine = RiskEngine(
            debate=RiskDebate(),
            config={"risk_pct": 0.01},
        )

        signal = _make_signal(confidence=0.80)
        portfolio = _make_portfolio()
        market_data = {"current_price": 100.0, "atr": 2.0}

        result = await engine.assess(signal, portfolio, market_data)

        assert result.risk_debate_summary is not None
        assert len(result.risk_debate_summary) > 0

    @pytest.mark.asyncio
    async def test_respect_debate_rejection(self):
        """When respect_debate=True and debate rejects, trade is rejected."""
        engine = RiskEngine(
            debate=RiskDebate(),
            config={"respect_debate": True, "min_debate_score": 0.99, "risk_pct": 0.01},
        )

        # Even a decent signal will fail a very high debate threshold
        signal = _make_signal(confidence=0.60)
        portfolio = _make_portfolio()
        market_data = {"current_price": 100.0, "atr": 2.0}

        result = await engine.assess(signal, portfolio, market_data)

        assert result.approved is False
        assert any("debate rejected" in w.lower() for w in result.warnings)
