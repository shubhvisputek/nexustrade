"""Tests for the paper-trading backend."""

import pytest

from nexustrade.core.models import (
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from nexustrade.execution.backends.paper import PaperBackend


@pytest.fixture
def backend() -> PaperBackend:
    return PaperBackend(initial_cash=100_000.0, slippage_pct=0.001, commission_pct=0.0005)


def _market_buy(symbol: str = "AAPL", quantity: float = 10, price: float = 150.0) -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=quantity,
        price=price,
    )


def _market_sell(symbol: str = "AAPL", quantity: float = 10, price: float = 155.0) -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=quantity,
        price=price,
    )


@pytest.mark.unit
class TestPaperBackendProperties:
    def test_name(self, backend: PaperBackend) -> None:
        assert backend.name == "paper"

    def test_is_paper(self, backend: PaperBackend) -> None:
        assert backend.is_paper is True

    def test_supported_markets(self, backend: PaperBackend) -> None:
        markets = backend.supported_markets
        assert "us_equity" in markets
        assert "crypto" in markets
        assert "india_equity" in markets
        assert "forex" in markets


@pytest.mark.unit
class TestPaperBackendBuy:
    async def test_buy_creates_position(self, backend: PaperBackend) -> None:
        fill = await backend.place_order(_market_buy())
        assert isinstance(fill, Fill)
        assert fill.status == OrderStatus.FILLED
        assert fill.symbol == "AAPL"
        assert fill.side == OrderSide.BUY
        assert fill.filled_qty == 10
        assert fill.broker == "paper"

        positions = await backend.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 10

    async def test_buy_deducts_cash(self, backend: PaperBackend) -> None:
        await backend.place_order(_market_buy(price=100.0, quantity=10))
        account = await backend.get_account()
        # Price after slippage: 100 * 1.001 = 100.1
        # Notional: 100.1 * 10 = 1001.0
        # Commission: 1001.0 * 0.0005 = 0.5005
        # Total cost: 1001.0 + 0.5005 = 1001.5005
        assert account["cash"] < 100_000.0
        assert account["cash"] == pytest.approx(100_000.0 - 1001.0 - 0.5005, rel=1e-6)


@pytest.mark.unit
class TestPaperBackendSlippage:
    async def test_buy_slippage_increases_price(self, backend: PaperBackend) -> None:
        fill = await backend.place_order(_market_buy(price=100.0))
        # Slippage = 0.1%: 100.0 * 1.001 = 100.1
        assert fill.avg_price == pytest.approx(100.1, rel=1e-6)

    async def test_sell_slippage_decreases_price(self, backend: PaperBackend) -> None:
        # First buy to create position
        await backend.place_order(_market_buy(price=100.0))
        fill = await backend.place_order(_market_sell(price=100.0))
        # Slippage = 0.1%: 100.0 * 0.999 = 99.9
        assert fill.avg_price == pytest.approx(99.9, rel=1e-6)


@pytest.mark.unit
class TestPaperBackendCommission:
    async def test_commission_deducted(self, backend: PaperBackend) -> None:
        fill = await backend.place_order(_market_buy(price=100.0, quantity=10))
        # Notional after slippage: 100.1 * 10 = 1001.0
        # Commission: 1001.0 * 0.0005 = 0.5005
        assert fill.fees == pytest.approx(0.5005, rel=1e-4)


@pytest.mark.unit
class TestPaperBackendBuySellCycle:
    async def test_buy_sell_pnl(self, backend: PaperBackend) -> None:
        # Buy at 100 (fill at 100.1 with slippage)
        await backend.place_order(_market_buy(price=100.0, quantity=10))
        # Sell at 110 (fill at 109.89 with slippage)
        await backend.place_order(_market_sell(price=110.0, quantity=10))

        positions = await backend.get_positions()
        # Position should be closed (quantity = 0, filtered out)
        assert len(positions) == 0

        account = await backend.get_account()
        # Should have made profit (sell_price > buy_price despite slippage)
        assert account["total_pnl"] > 0

    async def test_buy_sell_cash_returns(self, backend: PaperBackend) -> None:
        await backend.place_order(_market_buy(price=100.0, quantity=10))
        await backend.place_order(_market_sell(price=100.0, quantity=10))

        account = await backend.get_account()
        # Cash should be slightly less than initial due to slippage + commission
        assert account["cash"] < 100_000.0


@pytest.mark.unit
class TestPaperBackendPositions:
    async def test_get_positions_empty(self, backend: PaperBackend) -> None:
        positions = await backend.get_positions()
        assert positions == []

    async def test_get_positions_multiple(self, backend: PaperBackend) -> None:
        await backend.place_order(_market_buy(symbol="AAPL", price=150.0))
        await backend.place_order(_market_buy(symbol="GOOG", price=100.0))

        positions = await backend.get_positions()
        assert len(positions) == 2
        symbols = {p.symbol for p in positions}
        assert symbols == {"AAPL", "GOOG"}


@pytest.mark.unit
class TestPaperBackendAccount:
    async def test_get_account_initial(self, backend: PaperBackend) -> None:
        account = await backend.get_account()
        assert account["cash"] == 100_000.0
        assert account["total_value"] == 100_000.0
        assert account["total_pnl"] == 0.0
        assert account["initial_cash"] == 100_000.0
        assert account["num_positions"] == 0

    async def test_get_account_after_trade(self, backend: PaperBackend) -> None:
        await backend.place_order(_market_buy(price=150.0, quantity=10))
        account = await backend.get_account()
        assert account["num_positions"] == 1
        assert account["num_trades"] == 1
        assert account["cash"] < 100_000.0


@pytest.mark.unit
class TestPaperBackendCancelOrder:
    async def test_cancel_nonexistent(self, backend: PaperBackend) -> None:
        result = await backend.cancel_order("nonexistent_id")
        assert result is False


@pytest.mark.unit
class TestPaperBackendErrors:
    async def test_no_price_raises(self, backend: PaperBackend) -> None:
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
        with pytest.raises(RuntimeError, match="requires order.price"):
            await backend.place_order(order)

    async def test_insufficient_cash_raises(self, backend: PaperBackend) -> None:
        order = _market_buy(price=100_000.0, quantity=100)  # Way more than 100k cash
        with pytest.raises(RuntimeError, match="Insufficient cash"):
            await backend.place_order(order)
