"""Unit tests for the Interactive Brokers backend.

All IB interactions are mocked — no real TWS/Gateway connection required.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from nexustrade.core.models import (
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)


# ---------------------------------------------------------------------------
# Helpers to build mock IB objects
# ---------------------------------------------------------------------------

def _mock_order_status(
    status: str = "Filled",
    filled: float = 10.0,
    avg_fill_price: float = 150.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        filled=filled,
        avgFillPrice=avg_fill_price,
    )


def _mock_trade(
    order_id: int = 42,
    status: str = "Filled",
    filled: float = 10.0,
    avg_fill_price: float = 150.0,
    symbol: str = "AAPL",
) -> SimpleNamespace:
    return SimpleNamespace(
        order=SimpleNamespace(orderId=order_id, action="BUY", totalQuantity=10.0),
        contract=SimpleNamespace(symbol=symbol, secType="STK"),
        orderStatus=_mock_order_status(status, filled, avg_fill_price),
    )


def _mock_position(
    symbol: str = "AAPL",
    position: float = 100.0,
    avg_cost: float = 145.50,
    sec_type: str = "STK",
) -> SimpleNamespace:
    return SimpleNamespace(
        contract=SimpleNamespace(symbol=symbol, secType=sec_type),
        position=position,
        avgCost=avg_cost,
    )


def _mock_account_item(tag: str, value: str) -> SimpleNamespace:
    return SimpleNamespace(tag=tag, value=value)


def _sample_order(**overrides: Any) -> Order:
    defaults = dict(
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
    )
    defaults.update(overrides)
    return Order(**defaults)


# ---------------------------------------------------------------------------
# Fake ib_insync module for import mocking
# ---------------------------------------------------------------------------

def _build_fake_ib_module() -> MagicMock:
    """Return a mock module that looks enough like ib_insync for our imports."""
    mod = MagicMock()
    mod.IB = MagicMock
    mod.MarketOrder = MagicMock
    mod.LimitOrder = MagicMock
    mod.StopOrder = MagicMock
    mod.StopLimitOrder = MagicMock
    mod.Trade = MagicMock
    mod.Stock = MagicMock
    mod.Forex = MagicMock
    mod.Future = MagicMock
    mod.Option = MagicMock
    return mod


# ---------------------------------------------------------------------------
# Tests: graceful degradation when ib_insync is not installed
# ---------------------------------------------------------------------------

class TestIBBackendNoLibrary:
    """Tests for when ib_insync is NOT installed."""

    def test_instantiation_without_library(self) -> None:
        """IBBackend can be created even when ib_insync is missing."""
        # We import the module fresh to test the _HAS_IB = False path.
        from nexustrade.execution.backends.ib import IBBackend

        backend = IBBackend()
        assert backend.name == "ib"
        assert backend.is_paper is True
        assert "us_equity" in backend.supported_markets

    def test_health_check_false_when_not_connected(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend

        backend = IBBackend()
        result = asyncio.get_event_loop().run_until_complete(backend.health_check())
        # Either _HAS_IB is False or _ib is None — both return False
        assert result is False


# ---------------------------------------------------------------------------
# Tests: with mocked ib_insync
# ---------------------------------------------------------------------------

@pytest.fixture()
def ib_backend():
    """Create an IBBackend with a mocked IB connection."""
    from nexustrade.execution.backends import ib as ib_mod

    # Ensure the module thinks ib_insync is installed.
    original_has_ib = ib_mod._HAS_IB
    ib_mod._HAS_IB = True

    # Provide mock contract/order constructors so place_order works
    # without the real ib_insync package installed.
    mock_stock = MagicMock(name="Stock")
    mock_forex = MagicMock(name="Forex")
    mock_future = MagicMock(name="Future")
    mock_option = MagicMock(name="Option")
    mock_market_order = MagicMock(name="MarketOrder")
    mock_limit_order = MagicMock(name="LimitOrder")
    mock_stop_order = MagicMock(name="StopOrder")
    mock_stop_limit_order = MagicMock(name="StopLimitOrder")

    originals = {
        "Stock": ib_mod.Stock,
        "Forex": ib_mod.Forex,
        "Future": ib_mod.Future,
        "Option": ib_mod.Option,
        "MarketOrder": ib_mod.MarketOrder,
        "LimitOrder": ib_mod.LimitOrder,
        "StopOrder": ib_mod.StopOrder,
        "StopLimitOrder": ib_mod.StopLimitOrder,
    }

    ib_mod.Stock = mock_stock
    ib_mod.Forex = mock_forex
    ib_mod.Future = mock_future
    ib_mod.Option = mock_option
    ib_mod.MarketOrder = mock_market_order
    ib_mod.LimitOrder = mock_limit_order
    ib_mod.StopOrder = mock_stop_order
    ib_mod.StopLimitOrder = mock_stop_limit_order

    backend = ib_mod.IBBackend(host="127.0.0.1", port=7497, client_id=1, paper=True)

    # Create a mock IB instance and inject it.
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    backend._ib = mock_ib

    yield backend

    ib_mod._HAS_IB = original_has_ib
    for attr, val in originals.items():
        setattr(ib_mod, attr, val)


class TestIBBackendProperties:

    def test_name(self, ib_backend: Any) -> None:
        assert ib_backend.name == "ib"

    def test_is_paper(self, ib_backend: Any) -> None:
        assert ib_backend.is_paper is True

    def test_supported_markets(self, ib_backend: Any) -> None:
        markets = ib_backend.supported_markets
        assert "us_equity" in markets
        assert "forex" in markets
        assert "options" in markets
        assert "commodity" in markets

    def test_default_port_paper(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        b = IBBackend(paper=True)
        assert b._port == 7497

    def test_default_port_live(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        b = IBBackend(paper=False)
        assert b._port == 7496

    def test_custom_port(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        b = IBBackend(port=9999)
        assert b._port == 9999


class TestPlaceOrder:

    @pytest.mark.asyncio
    async def test_place_market_order(self, ib_backend: Any) -> None:
        mock_trade = _mock_trade(order_id=101, status="Filled", filled=10.0, avg_fill_price=155.0)
        ib_backend._ib.placeOrder.return_value = mock_trade
        ib_backend._ib.sleep.return_value = None

        order = _sample_order()
        fill = await ib_backend.place_order(order)

        assert isinstance(fill, Fill)
        assert fill.order_id == "101"
        assert fill.symbol == "AAPL"
        assert fill.side == OrderSide.BUY
        assert fill.filled_qty == 10.0
        assert fill.avg_price == 155.0
        assert fill.broker == "ib"
        assert fill.status == OrderStatus.FILLED
        assert fill.metadata["ib_order_id"] == "101"

    @pytest.mark.asyncio
    async def test_place_limit_order(self, ib_backend: Any) -> None:
        mock_trade = _mock_trade(order_id=102, status="Filled", filled=5.0, avg_fill_price=149.50)
        ib_backend._ib.placeOrder.return_value = mock_trade
        ib_backend._ib.sleep.return_value = None

        order = _sample_order(order_type=OrderType.LIMIT, price=150.0, quantity=5.0)
        fill = await ib_backend.place_order(order)

        assert fill.order_id == "102"
        assert fill.filled_qty == 5.0
        assert fill.avg_price == 149.50

    @pytest.mark.asyncio
    async def test_place_stop_order(self, ib_backend: Any) -> None:
        mock_trade = _mock_trade(order_id=103, status="Filled", filled=10.0, avg_fill_price=145.0)
        ib_backend._ib.placeOrder.return_value = mock_trade
        ib_backend._ib.sleep.return_value = None

        order = _sample_order(order_type=OrderType.STOP, stop_price=145.0)
        fill = await ib_backend.place_order(order)

        assert fill.order_id == "103"
        assert fill.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_place_stop_limit_order(self, ib_backend: Any) -> None:
        mock_trade = _mock_trade(order_id=104, status="Filled", filled=10.0, avg_fill_price=146.0)
        ib_backend._ib.placeOrder.return_value = mock_trade
        ib_backend._ib.sleep.return_value = None

        order = _sample_order(
            order_type=OrderType.STOP_LIMIT,
            price=147.0,
            stop_price=145.0,
        )
        fill = await ib_backend.place_order(order)

        assert fill.order_id == "104"
        assert fill.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_place_sell_order(self, ib_backend: Any) -> None:
        mock_trade = _mock_trade(order_id=105, status="Filled", filled=10.0, avg_fill_price=160.0)
        ib_backend._ib.placeOrder.return_value = mock_trade
        ib_backend._ib.sleep.return_value = None

        order = _sample_order(side=OrderSide.SELL)
        fill = await ib_backend.place_order(order)

        assert fill.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_place_order_pending_status(self, ib_backend: Any) -> None:
        mock_trade = _mock_trade(order_id=106, status="Submitted", filled=0.0, avg_fill_price=0.0)
        ib_backend._ib.placeOrder.return_value = mock_trade
        ib_backend._ib.sleep.return_value = None

        order = _sample_order()
        fill = await ib_backend.place_order(order)

        assert fill.status == OrderStatus.PENDING
        assert fill.filled_qty == 10.0  # falls back to order.quantity


class TestCancelOrder:

    @pytest.mark.asyncio
    async def test_cancel_existing_order(self, ib_backend: Any) -> None:
        trade = _mock_trade(order_id=42)
        ib_backend._ib.openTrades.return_value = [trade]
        ib_backend._ib.cancelOrder.return_value = None

        result = await ib_backend.cancel_order("42")
        assert result is True
        ib_backend._ib.cancelOrder.assert_called_once_with(trade.order)

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self, ib_backend: Any) -> None:
        ib_backend._ib.openTrades.return_value = []

        result = await ib_backend.cancel_order("999")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_order_exception(self, ib_backend: Any) -> None:
        ib_backend._ib.openTrades.side_effect = RuntimeError("connection lost")

        result = await ib_backend.cancel_order("42")
        assert result is False


class TestGetPositions:

    @pytest.mark.asyncio
    async def test_get_positions(self, ib_backend: Any) -> None:
        ib_backend._ib.positions.return_value = [
            _mock_position("AAPL", 100.0, 145.50, "STK"),
            _mock_position("EURUSD", 50000.0, 1.085, "CASH"),
        ]

        positions = await ib_backend.get_positions()

        assert len(positions) == 2
        assert isinstance(positions[0], Position)
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 100.0
        assert positions[0].avg_entry_price == 145.50
        assert positions[0].broker == "ib"
        assert positions[0].market == "us_equity"

        assert positions[1].symbol == "EURUSD"
        assert positions[1].market == "forex"

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, ib_backend: Any) -> None:
        ib_backend._ib.positions.return_value = []

        positions = await ib_backend.get_positions()
        assert positions == []


class TestGetAccount:

    @pytest.mark.asyncio
    async def test_get_account(self, ib_backend: Any) -> None:
        ib_backend._ib.accountSummary.return_value = [
            _mock_account_item("TotalCashValue", "100000.00"),
            _mock_account_item("NetLiquidation", "250000.00"),
            _mock_account_item("BuyingPower", "400000.00"),
            _mock_account_item("GrossPositionValue", "150000.00"),
        ]

        account = await ib_backend.get_account()

        assert account["broker"] == "ib"
        assert account["paper"] is True
        assert account["cash"] == 100000.0
        assert account["equity"] == 250000.0
        assert account["buying_power"] == 400000.0
        assert account["portfolio_value"] == 150000.0


class TestModifyOrder:

    @pytest.mark.asyncio
    async def test_modify_order_price(self, ib_backend: Any) -> None:
        trade = _mock_trade(order_id=42)
        ib_backend._ib.openTrades.return_value = [trade]
        ib_backend._ib.placeOrder.return_value = trade

        result = await ib_backend.modify_order("42", {"price": 160.0})
        assert result is True
        assert trade.order.lmtPrice == 160.0

    @pytest.mark.asyncio
    async def test_modify_order_not_found(self, ib_backend: Any) -> None:
        ib_backend._ib.openTrades.return_value = []

        result = await ib_backend.modify_order("999", {"price": 160.0})
        assert result is False


class TestGetOrderHistory:

    @pytest.mark.asyncio
    async def test_get_order_history(self, ib_backend: Any) -> None:
        trades = [_mock_trade(order_id=1), _mock_trade(order_id=2)]
        ib_backend._ib.trades.return_value = trades

        history = await ib_backend.get_order_history(limit=10)
        assert len(history) == 2
        assert history[0]["order_id"] == "1"
        assert history[1]["order_id"] == "2"


class TestHealthCheck:

    @pytest.mark.asyncio
    async def test_health_check_connected(self, ib_backend: Any) -> None:
        ib_backend._ib.isConnected.return_value = True
        assert await ib_backend.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self, ib_backend: Any) -> None:
        ib_backend._ib.isConnected.return_value = False
        assert await ib_backend.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_no_ib_object(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        backend = IBBackend()
        assert await backend.health_check() is False


class TestEnsureReady:

    def test_ensure_ready_not_connected(self, ib_backend: Any) -> None:
        ib_backend._ib.isConnected.return_value = False
        with pytest.raises(RuntimeError, match="Not connected to IB"):
            ib_backend._ensure_ready()

    def test_ensure_ready_no_ib_object(self, ib_backend: Any) -> None:
        ib_backend._ib = None
        with pytest.raises(RuntimeError, match="Not connected to IB"):
            ib_backend._ensure_ready()


class TestEnsureInstalled:

    def test_ensure_installed_raises_when_missing(self) -> None:
        from nexustrade.execution.backends import ib as ib_mod
        original = ib_mod._HAS_IB
        try:
            ib_mod._HAS_IB = False
            backend = ib_mod.IBBackend()
            with pytest.raises(RuntimeError, match="Neither ib_insync nor ib_async is installed"):
                backend._ensure_installed()
        finally:
            ib_mod._HAS_IB = original


class TestStatusMapping:

    def test_filled(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        assert IBBackend._map_status("Filled") == OrderStatus.FILLED

    def test_cancelled(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        assert IBBackend._map_status("Cancelled") == OrderStatus.CANCELLED

    def test_inactive(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        assert IBBackend._map_status("Inactive") == OrderStatus.REJECTED

    def test_submitted(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        assert IBBackend._map_status("Submitted") == OrderStatus.PENDING

    def test_unknown_defaults_pending(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        assert IBBackend._map_status("SomethingNew") == OrderStatus.PENDING


class TestDetectMarket:

    def test_stock(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        c = SimpleNamespace(secType="STK")
        assert IBBackend._detect_market(c) == "us_equity"

    def test_forex(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        c = SimpleNamespace(secType="CASH")
        assert IBBackend._detect_market(c) == "forex"

    def test_option(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        c = SimpleNamespace(secType="OPT")
        assert IBBackend._detect_market(c) == "options"

    def test_future(self) -> None:
        from nexustrade.execution.backends.ib import IBBackend
        c = SimpleNamespace(secType="FUT")
        assert IBBackend._detect_market(c) == "commodity"
