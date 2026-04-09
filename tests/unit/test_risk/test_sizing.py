"""Tests for position sizing models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nexustrade.core.models import (
    CompositeSignal,
    PortfolioState,
    RiskAssessment,
    SignalDirection,
)
from nexustrade.risk.sizing.cvar import CVaRModel
from nexustrade.risk.sizing.fixed_fraction import FixedFractionModel
from nexustrade.risk.sizing.kelly import KellyCriterionModel
from nexustrade.risk.sizing.max_drawdown import MaxDrawdownModel
from nexustrade.risk.sizing.volatility import VolatilityModel


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


def _make_market_data(
    current_price: float = 150.0,
    atr: float = 3.0,
) -> dict:
    return {"current_price": current_price, "atr": atr}


class TestKellyCriterion:
    @pytest.mark.asyncio
    async def test_known_inputs_expected_size(self):
        model = KellyCriterionModel()
        signal = _make_signal(confidence=0.70)
        portfolio = _make_portfolio(total_value=100_000.0)
        market_data = _make_market_data(current_price=150.0, atr=3.0)
        config = {"half_kelly": True, "max_kelly_fraction": 0.25}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert result.approved is True
        assert result.position_size > 0
        assert result.stop_loss_price < 150.0  # BUY signal
        assert result.take_profit_price > 150.0
        assert result.sizing_model == "kelly"

    @pytest.mark.asyncio
    async def test_low_confidence_rejected(self):
        """Very low confidence => negative Kelly fraction => rejected."""
        model = KellyCriterionModel()
        signal = _make_signal(confidence=0.20)
        portfolio = _make_portfolio()
        market_data = _make_market_data()
        config = {"half_kelly": True}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert result.approved is False
        assert result.position_size == 0

    @pytest.mark.asyncio
    async def test_returns_valid_risk_assessment(self):
        model = KellyCriterionModel()
        signal = _make_signal(confidence=0.80)
        portfolio = _make_portfolio()
        market_data = _make_market_data()
        config = {}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert isinstance(result, RiskAssessment)
        assert result.symbol == "AAPL"
        assert result.risk_reward_ratio > 0


class TestCVaR:
    @pytest.mark.asyncio
    async def test_known_inputs_within_bounds(self):
        model = CVaRModel()
        signal = _make_signal()
        portfolio = _make_portfolio(total_value=100_000.0)
        market_data = _make_market_data(current_price=150.0, atr=3.0)
        config = {"max_loss_pct": 0.02, "max_position_pct": 0.20}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert result.approved is True
        # Position value should not exceed 20% of portfolio
        assert result.position_size * 150.0 <= 100_000.0 * 0.20 + 150.0

    @pytest.mark.asyncio
    async def test_returns_valid_risk_assessment(self):
        model = CVaRModel()
        signal = _make_signal()
        portfolio = _make_portfolio()
        market_data = _make_market_data()
        config = {}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert isinstance(result, RiskAssessment)
        assert result.sizing_model == "cvar"


class TestFixedFraction:
    @pytest.mark.asyncio
    async def test_simple_calculation(self):
        model = FixedFractionModel()
        signal = _make_signal()
        portfolio = _make_portfolio(total_value=100_000.0)
        market_data = _make_market_data(current_price=100.0, atr=2.0)
        config = {"risk_pct": 0.01, "atr_stop_multiple": 2.0, "atr_tp_multiple": 3.0, "max_position_pct": 1.0}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert result.approved is True
        # risk_dollars = 100000 * 0.01 = 1000
        # risk_per_share = 2.0 * 2.0 = 4.0
        # position_size = floor(1000 / 4.0) = 250
        assert result.position_size == 250.0
        assert result.stop_loss_price == 96.0  # 100 - 4
        assert result.take_profit_price == 106.0  # 100 + 6
        assert result.sizing_model == "fixed_fraction"

    @pytest.mark.asyncio
    async def test_returns_valid_risk_assessment(self):
        model = FixedFractionModel()
        signal = _make_signal()
        portfolio = _make_portfolio()
        market_data = _make_market_data()
        config = {}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert isinstance(result, RiskAssessment)


class TestVolatility:
    @pytest.mark.asyncio
    async def test_atr_based_sizing(self):
        model = VolatilityModel()
        signal = _make_signal()
        portfolio = _make_portfolio(total_value=100_000.0)
        market_data = _make_market_data(current_price=100.0, atr=2.0)
        config = {"risk_pct": 0.01, "atr_multiple": 2.0, "max_position_pct": 1.0}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert result.approved is True
        # risk_per_share = 2.0 * 2.0 = 4.0
        # risk_dollars = 100000 * 0.01 = 1000
        # position_size = floor(1000 / 4.0) = 250
        assert result.position_size == 250.0

    @pytest.mark.asyncio
    async def test_returns_valid_risk_assessment(self):
        model = VolatilityModel()
        signal = _make_signal()
        portfolio = _make_portfolio()
        market_data = _make_market_data()
        config = {}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert isinstance(result, RiskAssessment)
        assert result.sizing_model == "volatility"


class TestMaxDrawdown:
    @pytest.mark.asyncio
    async def test_drawdown_budget_limits_size(self):
        model = MaxDrawdownModel()
        signal = _make_signal()
        # Already in drawdown: daily_pnl = -5000 on 100k portfolio = 5%
        portfolio = _make_portfolio(total_value=100_000.0, daily_pnl=-5000.0)
        market_data = _make_market_data(current_price=100.0, atr=2.0)
        config = {"max_drawdown_pct": 0.10, "atr_stop_multiple": 2.0, "max_position_pct": 2.0}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert result.approved is True
        # remaining budget = 10% - 5% = 5% => $5000 max loss
        # risk_per_share = 2.0 * 2.0 = 4.0
        # position_size = floor(5000 / 4.0) = 1250
        assert result.position_size == 1250.0

    @pytest.mark.asyncio
    async def test_drawdown_budget_exhausted(self):
        model = MaxDrawdownModel()
        signal = _make_signal()
        # daily_pnl = -10000 on 100k = 10%, max_drawdown = 10%
        portfolio = _make_portfolio(total_value=100_000.0, daily_pnl=-10_000.0)
        market_data = _make_market_data()
        config = {"max_drawdown_pct": 0.10}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert result.approved is False

    @pytest.mark.asyncio
    async def test_returns_valid_risk_assessment(self):
        model = MaxDrawdownModel()
        signal = _make_signal()
        portfolio = _make_portfolio()
        market_data = _make_market_data()
        config = {}

        result = await model.calculate_position_size(portfolio, signal, market_data, config)

        assert isinstance(result, RiskAssessment)
        assert result.sizing_model == "max_drawdown"
