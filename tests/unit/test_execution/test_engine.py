"""Tests for the ExecutionEngine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nexustrade.core.models import (
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from nexustrade.execution.engine import ExecutionEngine

pytestmark = pytest.mark.unit


def _make_fill(broker: str = "mock", symbol: str = "AAPL") -> Fill:
    from datetime import datetime, timezone

    return Fill(
        order_id="test123",
        symbol=symbol,
        side=OrderSide.BUY,
        filled_qty=10,
        avg_price=150.0,
        timestamp=datetime.now(timezone.utc),
        broker=broker,
        status=OrderStatus.FILLED,
    )


def _make_order(symbol: str = "AAPL") -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        price=150.0,
    )


@pytest.fixture
def mock_broker() -> MagicMock:
    broker = MagicMock()
    broker.name = "mock_broker"
    broker.place_order = AsyncMock(return_value=_make_fill("mock_broker"))
    return broker


@pytest.fixture
def mock_tv_broker() -> MagicMock:
    broker = MagicMock()
    broker.name = "tradingview"
    broker.place_order = AsyncMock(return_value=_make_fill("tradingview"))
    return broker


class TestExecutionEnginePython:
    async def test_python_mode_calls_broker(
        self, mock_broker: MagicMock
    ) -> None:
        engine = ExecutionEngine(
            mode="python",
            brokers={"mock_broker": mock_broker},
            market_broker_map={"us_equity": "mock_broker"},
        )

        fill = await engine.execute(_make_order(), market="us_equity")

        assert fill.broker == "mock_broker"
        mock_broker.place_order.assert_awaited_once()

    async def test_python_mode_unknown_market_raises(
        self, mock_broker: MagicMock
    ) -> None:
        engine = ExecutionEngine(
            mode="python",
            brokers={"mock_broker": mock_broker},
            market_broker_map={"us_equity": "mock_broker"},
        )

        with pytest.raises(RuntimeError, match="No broker configured"):
            await engine.execute(_make_order(), market="unknown")


class TestExecutionEngineTradingView:
    async def test_tradingview_mode_calls_tv(
        self, mock_tv_broker: MagicMock
    ) -> None:
        engine = ExecutionEngine(
            mode="tradingview",
            brokers={"tradingview": mock_tv_broker},
        )

        fill = await engine.execute(_make_order())

        assert fill.broker == "tradingview"
        mock_tv_broker.place_order.assert_awaited_once()

    async def test_tradingview_mode_no_tv_broker_raises(self) -> None:
        engine = ExecutionEngine(
            mode="tradingview",
            brokers={},
        )

        with pytest.raises(RuntimeError, match="TradingView backend"):
            await engine.execute(_make_order())


class TestExecutionEngineBoth:
    async def test_both_mode_calls_both(
        self, mock_broker: MagicMock, mock_tv_broker: MagicMock
    ) -> None:
        engine = ExecutionEngine(
            mode="both",
            brokers={
                "mock_broker": mock_broker,
                "tradingview": mock_tv_broker,
            },
            market_broker_map={"us_equity": "mock_broker"},
        )

        fill = await engine.execute(_make_order(), market="us_equity")

        # Returns the direct broker fill
        assert fill.broker == "mock_broker"
        mock_broker.place_order.assert_awaited_once()
        mock_tv_broker.place_order.assert_awaited_once()

    async def test_both_mode_tv_failure_still_returns_broker_fill(
        self, mock_broker: MagicMock
    ) -> None:
        failing_tv = MagicMock()
        failing_tv.name = "tradingview"
        failing_tv.place_order = AsyncMock(side_effect=RuntimeError("TV down"))

        engine = ExecutionEngine(
            mode="both",
            brokers={
                "mock_broker": mock_broker,
                "tradingview": failing_tv,
            },
            market_broker_map={"us_equity": "mock_broker"},
        )

        fill = await engine.execute(_make_order(), market="us_equity")
        assert fill.broker == "mock_broker"


class TestExecutionEngineInit:
    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid execution mode"):
            ExecutionEngine(mode="invalid")

    def test_mode_property(self) -> None:
        engine = ExecutionEngine(mode="python")
        assert engine.mode == "python"

    def test_brokers_property(self, mock_broker: MagicMock) -> None:
        engine = ExecutionEngine(
            mode="python",
            brokers={"mock": mock_broker},
        )
        assert "mock" in engine.brokers
