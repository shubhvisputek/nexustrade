"""Tests for circuit breaker."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from nexustrade.core.models import Fill, OrderSide, OrderStatus, PortfolioState
from nexustrade.risk.circuit_breaker import CircuitBreaker


pytestmark = pytest.mark.unit


def _make_portfolio(
    daily_pnl: float = 0.0,
    total_value: float = 100_000.0,
    num_positions: int = 0,
) -> PortfolioState:
    from nexustrade.core.models import Position

    positions = [
        Position(
            symbol=f"SYM{i}",
            quantity=100,
            avg_entry_price=100.0,
            current_price=100.0,
            unrealized_pnl=0.0,
        )
        for i in range(num_positions)
    ]
    return PortfolioState(
        cash=total_value - num_positions * 10000,
        positions=positions,
        total_value=total_value,
        daily_pnl=daily_pnl,
        total_pnl=0.0,
        open_orders=[],
    )


def _make_fill(pnl: float = -100.0) -> Fill:
    from datetime import datetime, timezone

    return Fill(
        order_id="test-001",
        symbol="AAPL",
        side=OrderSide.SELL,
        filled_qty=100,
        avg_price=150.0,
        timestamp=datetime.now(timezone.utc),
        broker="paper",
        status=OrderStatus.FILLED,
        metadata={"realized_pnl": pnl},
    )


class TestCircuitBreaker:
    def test_normal_conditions_can_trade(self):
        cb = CircuitBreaker({"max_daily_loss_pct": 0.03, "max_consecutive_losses": 5})
        portfolio = _make_portfolio()

        can_trade, reason = cb.check(portfolio)

        assert can_trade is True
        assert reason is None

    def test_daily_loss_limit_blocks(self):
        cb = CircuitBreaker({"max_daily_loss_pct": 0.03})
        # daily_pnl = -4000 on 100k = 4% > 3%
        portfolio = _make_portfolio(daily_pnl=-4000.0, total_value=100_000.0)

        can_trade, reason = cb.check(portfolio)

        assert can_trade is False
        assert reason is not None
        assert "Daily loss" in reason

    def test_consecutive_losses_blocks(self):
        cb = CircuitBreaker({"max_consecutive_losses": 3})

        # Simulate 3 consecutive losses
        for _ in range(3):
            cb.update(_make_fill(pnl=-100.0))

        portfolio = _make_portfolio()
        can_trade, reason = cb.check(portfolio)

        assert can_trade is False
        assert "Consecutive losses" in reason

    def test_win_resets_consecutive_losses(self):
        cb = CircuitBreaker({"max_consecutive_losses": 5})

        # 2 losses then a win
        cb.update(_make_fill(pnl=-100.0))
        cb.update(_make_fill(pnl=-100.0))
        cb.update(_make_fill(pnl=200.0))

        portfolio = _make_portfolio()
        can_trade, reason = cb.check(portfolio)

        assert can_trade is True

    def test_cooldown_then_unblocked(self):
        cb = CircuitBreaker({
            "max_daily_loss_pct": 0.03,
            "cooldown_minutes": 0.001,  # ~0.06 seconds
        })
        # Trigger the breaker
        portfolio = _make_portfolio(daily_pnl=-5000.0, total_value=100_000.0)
        can_trade, _ = cb.check(portfolio)
        assert can_trade is False

        # Wait for cooldown (use mock to avoid actual sleep)
        with patch("time.monotonic", return_value=time.monotonic() + 1.0):
            can_trade, reason = cb.check(_make_portfolio())
            assert can_trade is True

    def test_manual_reset(self):
        cb = CircuitBreaker({"max_consecutive_losses": 2})

        # Trigger
        cb.update(_make_fill(pnl=-100.0))
        cb.update(_make_fill(pnl=-100.0))

        portfolio = _make_portfolio()
        can_trade, _ = cb.check(portfolio)
        assert can_trade is False

        # Reset
        cb.reset()
        can_trade, reason = cb.check(portfolio)
        assert can_trade is True
        assert reason is None

    def test_too_many_open_positions(self):
        cb = CircuitBreaker({"max_open_positions": 5})
        portfolio = _make_portfolio(num_positions=6)

        can_trade, reason = cb.check(portfolio)

        assert can_trade is False
        assert "Too many open positions" in reason
