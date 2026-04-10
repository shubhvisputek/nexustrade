"""Tests for pre-trade validation."""

from __future__ import annotations

import pytest

from nexustrade.core.models import Order, OrderSide, OrderType, PortfolioState, Position
from nexustrade.risk.pre_trade import PreTradeValidator


pytestmark = pytest.mark.unit


def _make_portfolio(
    cash: float = 100_000.0,
    positions: list[Position] | None = None,
    total_value: float = 100_000.0,
    circuit_breaker_active: bool = False,
) -> PortfolioState:
    return PortfolioState(
        cash=cash,
        positions=positions or [],
        total_value=total_value,
        daily_pnl=0.0,
        total_pnl=0.0,
        open_orders=[],
        circuit_breaker_active=circuit_breaker_active,
    )


def _make_order(
    symbol: str = "AAPL",
    quantity: float = 100,
    price: float = 150.0,
    side: OrderSide = OrderSide.BUY,
) -> Order:
    return Order(
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        price=price,
    )


def _make_position(
    symbol: str = "AAPL",
    quantity: float = 50,
    avg_entry: float = 145.0,
    current: float = 150.0,
) -> Position:
    return Position(
        symbol=symbol,
        quantity=quantity,
        avg_entry_price=avg_entry,
        current_price=current,
        unrealized_pnl=(current - avg_entry) * quantity,
    )


class TestPreTradeValidator:
    def test_valid_order_approved(self):
        validator = PreTradeValidator({"max_position_pct": 0.20, "max_open_positions": 10})
        order = _make_order(quantity=10, price=150.0)
        portfolio = _make_portfolio()
        market_data = {"current_price": 150.0}

        approved, warnings = validator.validate(order, portfolio, market_data)

        assert approved is True
        assert len(warnings) == 0

    def test_max_position_size_exceeded(self):
        validator = PreTradeValidator({"max_position_pct": 0.10})
        # Order value = 500 * 150 = 75000, which is 75% of 100k
        order = _make_order(quantity=500, price=150.0)
        portfolio = _make_portfolio(total_value=100_000.0)
        market_data = {"current_price": 150.0}

        approved, warnings = validator.validate(order, portfolio, market_data)

        assert approved is False
        assert any("exceeds max" in w for w in warnings)

    def test_max_open_positions_exceeded(self):
        validator = PreTradeValidator({"max_open_positions": 2})
        positions = [
            _make_position(symbol="AAPL"),
            _make_position(symbol="GOOGL"),
        ]
        order = _make_order(symbol="MSFT", quantity=10)
        portfolio = _make_portfolio(positions=positions)
        market_data = {"current_price": 150.0}

        approved, warnings = validator.validate(order, portfolio, market_data)

        assert approved is False
        assert any("Max open positions" in w for w in warnings)

    def test_adding_to_existing_position_allowed(self):
        """Adding to an existing position should not trigger max open positions."""
        validator = PreTradeValidator({"max_open_positions": 2, "max_position_pct": 0.50})
        positions = [
            _make_position(symbol="AAPL"),
            _make_position(symbol="GOOGL"),
        ]
        order = _make_order(symbol="AAPL", quantity=10)
        portfolio = _make_portfolio(positions=positions)
        market_data = {"current_price": 150.0}

        approved, warnings = validator.validate(order, portfolio, market_data)

        assert approved is True

    def test_circuit_breaker_active_rejected(self):
        validator = PreTradeValidator({})
        order = _make_order(quantity=10)
        portfolio = _make_portfolio(circuit_breaker_active=True)
        market_data = {"current_price": 150.0}

        approved, warnings = validator.validate(order, portfolio, market_data)

        assert approved is False
        assert any("Circuit breaker" in w for w in warnings)

    def test_zero_quantity_rejected(self):
        validator = PreTradeValidator({})
        order = _make_order(quantity=0)
        portfolio = _make_portfolio()
        market_data = {"current_price": 150.0}

        approved, warnings = validator.validate(order, portfolio, market_data)

        assert approved is False
        assert any("positive" in w for w in warnings)
