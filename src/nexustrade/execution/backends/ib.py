"""Interactive Brokers backend.

Wraps the ``ib_insync`` (or ``ib_async``) library for TWS/Gateway connectivity.
Falls back gracefully when neither package is installed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from nexustrade.core.interfaces import BrokerBackendInterface
from nexustrade.core.models import Fill, Order, OrderSide, OrderStatus, OrderType, Position

logger = logging.getLogger(__name__)

# Try ib_insync first, then the newer ib_async fork.
try:
    from ib_insync import (  # type: ignore[import-untyped]
        IB, MarketOrder, LimitOrder, StopOrder, StopLimitOrder,
        Trade as IBTrade,
        Stock, Forex, Future, Option,
    )

    _HAS_IB = True
    _IB_PACKAGE = "ib_insync"
except ImportError:
    try:
        from ib_async import (  # type: ignore[import-untyped]
            IB, MarketOrder, LimitOrder, StopOrder, StopLimitOrder,
            Trade as IBTrade,
            Stock, Forex, Future, Option,
        )

        _HAS_IB = True
        _IB_PACKAGE = "ib_async"
    except ImportError:
        _HAS_IB = False
        _IB_PACKAGE = None
        # Provide stubs so the class body can reference the names at type-check
        # time without guarding every usage.
        IB = None  # type: ignore[assignment,misc]
        MarketOrder = LimitOrder = StopOrder = StopLimitOrder = None  # type: ignore[assignment,misc]
        IBTrade = Stock = Forex = Future = Option = None  # type: ignore[assignment,misc]


# Default ports for TWS / IB Gateway
_PORTS = {
    "tws_paper": 7497,
    "tws_live": 7496,
    "gateway_paper": 4002,
    "gateway_live": 4001,
}


class IBBackend(BrokerBackendInterface):
    """Interactive Brokers broker backend.

    Parameters
    ----------
    host:
        TWS/Gateway hostname.  Default ``"127.0.0.1"``.
    port:
        TWS/Gateway port.  Auto-selected based on *paper* if not given.
    client_id:
        IB API client ID.  Default ``1``.
    paper:
        If ``True`` (default), connect to the paper-trading port.
    timeout:
        Connection timeout in seconds.  Default ``10``.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int | None = None,
        client_id: int = 1,
        paper: bool = True,
        timeout: int = 10,
    ) -> None:
        self._host = host
        self._client_id = client_id
        self._paper = paper
        self._timeout = timeout
        self._ib: Any = None

        # Pick a sensible default port when the caller doesn't supply one.
        if port is not None:
            self._port = port
        else:
            self._port = _PORTS["tws_paper"] if paper else _PORTS["tws_live"]

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "ib"

    @property
    def is_paper(self) -> bool:
        return self._paper

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity", "forex", "options", "commodity"]

    # -- connection management -----------------------------------------------

    async def connect(self) -> None:
        """Establish a connection to TWS / IB Gateway."""
        self._ensure_installed()
        if self._ib is not None and self._ib.isConnected():
            return

        self._ib = IB()
        await asyncio.to_thread(
            self._ib.connect,
            self._host,
            self._port,
            clientId=self._client_id,
            timeout=self._timeout,
        )
        logger.info(
            "Connected to IB on %s:%s (client_id=%s, paper=%s)",
            self._host,
            self._port,
            self._client_id,
            self._paper,
        )

    async def disconnect(self) -> None:
        """Cleanly disconnect from TWS / IB Gateway."""
        if self._ib is not None and self._ib.isConnected():
            await asyncio.to_thread(self._ib.disconnect)
            logger.info("Disconnected from IB")

    # -- required interface methods ------------------------------------------

    async def place_order(self, order: Order) -> Fill:
        """Submit an order via IB and return the fill."""
        self._ensure_ready()
        start_ts = time.monotonic()

        # Build the IB contract -- default to US equity via SMART routing.
        market = order.metadata.get("market", "us_equity") if order.metadata else "us_equity"
        contract = self._make_contract(order.symbol, market)

        # Build the IB order object.
        ib_action = "BUY" if order.side == OrderSide.BUY else "SELL"
        ib_order = self._make_ib_order(order, ib_action)

        # Submit via ib_insync (blocking call wrapped in a thread).
        trade: Any = await asyncio.to_thread(
            self._ib.placeOrder, contract, ib_order
        )

        # Wait briefly for the order to fill (up to 5 seconds).
        filled = await self._wait_for_fill(trade, timeout=5.0)

        latency_ms = (time.monotonic() - start_ts) * 1000.0

        # Map IB status to NexusTrade status.
        status = self._map_status(trade.orderStatus.status if trade.orderStatus else "")
        filled_qty = float(trade.orderStatus.filled) if trade.orderStatus else 0.0
        avg_price = float(trade.orderStatus.avgFillPrice) if trade.orderStatus else 0.0

        if filled_qty == 0.0:
            filled_qty = order.quantity
        if avg_price == 0.0 and order.price is not None:
            avg_price = order.price

        return Fill(
            order_id=str(trade.order.orderId) if trade.order else "unknown",
            symbol=order.symbol,
            side=order.side,
            filled_qty=filled_qty,
            avg_price=avg_price,
            timestamp=datetime.now(timezone.utc),
            broker="ib",
            status=status,
            fees=0.0,  # IB commissions are reported asynchronously
            slippage=0.0,
            latency_ms=latency_ms,
            metadata={
                "ib_order_id": str(trade.order.orderId) if trade.order else None,
                "ib_status": trade.orderStatus.status if trade.orderStatus else None,
            },
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order on IB."""
        self._ensure_ready()
        try:
            # Find the trade matching this order ID.
            open_trades = self._ib.openTrades()
            for trade in open_trades:
                if str(trade.order.orderId) == order_id:
                    await asyncio.to_thread(self._ib.cancelOrder, trade.order)
                    return True
            logger.warning("IB order %s not found among open trades", order_id)
            return False
        except Exception:
            logger.exception("Failed to cancel IB order %s", order_id)
            return False

    async def get_positions(self) -> list[Position]:
        """Fetch all open positions from IB."""
        self._ensure_ready()
        raw = await asyncio.to_thread(self._ib.positions)
        positions: list[Position] = []
        for p in raw:
            symbol = p.contract.symbol if p.contract else "UNKNOWN"
            qty = float(p.position)
            avg_cost = float(p.avgCost)

            # IB reports avgCost per share for stocks, per unit for forex.
            positions.append(
                Position(
                    symbol=symbol,
                    quantity=qty,
                    avg_entry_price=avg_cost,
                    current_price=avg_cost,  # IB doesn't include live price here
                    unrealized_pnl=0.0,  # requires market data subscription
                    realized_pnl=0.0,
                    broker="ib",
                    market=self._detect_market(p.contract) if p.contract else "us_equity",
                )
            )
        return positions

    async def get_account(self) -> dict[str, Any]:
        """Return IB account summary."""
        self._ensure_ready()
        summary = await asyncio.to_thread(self._ib.accountSummary)

        result: dict[str, Any] = {
            "broker": "ib",
            "paper": self._paper,
        }
        for item in summary:
            tag = item.tag
            try:
                value = float(item.value)
            except (ValueError, TypeError):
                value = item.value
            result[tag] = value

        # Map common tags to a consistent format.
        result.setdefault("cash", result.get("TotalCashValue", 0.0))
        result.setdefault("equity", result.get("NetLiquidation", 0.0))
        result.setdefault("buying_power", result.get("BuyingPower", 0.0))
        result.setdefault("portfolio_value", result.get("GrossPositionValue", 0.0))

        return result

    async def modify_order(
        self,
        order_id: str,
        updates: dict[str, Any],
    ) -> bool:
        """Modify a live order on IB."""
        self._ensure_ready()
        try:
            open_trades = self._ib.openTrades()
            for trade in open_trades:
                if str(trade.order.orderId) == order_id:
                    ib_order = trade.order
                    if "price" in updates:
                        ib_order.lmtPrice = updates["price"]
                    if "quantity" in updates:
                        ib_order.totalQuantity = updates["quantity"]
                    if "stop_price" in updates:
                        ib_order.auxPrice = updates["stop_price"]
                    await asyncio.to_thread(
                        self._ib.placeOrder, trade.contract, ib_order
                    )
                    return True
            logger.warning("IB order %s not found for modification", order_id)
            return False
        except Exception:
            logger.exception("Failed to modify IB order %s", order_id)
            return False

    async def get_order_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent order history from IB."""
        self._ensure_ready()
        trades = self._ib.trades()
        history: list[dict[str, Any]] = []
        for trade in trades[:limit]:
            history.append({
                "order_id": str(trade.order.orderId) if trade.order else None,
                "symbol": trade.contract.symbol if trade.contract else None,
                "action": trade.order.action if trade.order else None,
                "quantity": float(trade.order.totalQuantity) if trade.order else 0.0,
                "status": trade.orderStatus.status if trade.orderStatus else None,
                "filled_qty": float(trade.orderStatus.filled) if trade.orderStatus else 0.0,
                "avg_price": float(trade.orderStatus.avgFillPrice) if trade.orderStatus else 0.0,
            })
        return history

    async def health_check(self) -> bool:
        """Check IB connectivity."""
        if not _HAS_IB:
            return False
        if self._ib is None:
            return False
        try:
            return self._ib.isConnected()
        except Exception:
            return False

    # -- internals -----------------------------------------------------------

    def _ensure_installed(self) -> None:
        """Raise if ib_insync / ib_async is not installed."""
        if not _HAS_IB:
            raise RuntimeError(
                "Neither ib_insync nor ib_async is installed. "
                "Install with: pip install ib_insync  (or: pip install ib_async)"
            )

    def _ensure_ready(self) -> None:
        """Raise if the library is missing or we are not connected."""
        self._ensure_installed()
        if self._ib is None or not self._ib.isConnected():
            raise RuntimeError(
                "Not connected to IB. Call `await backend.connect()` first, "
                "and ensure TWS or IB Gateway is running."
            )

    def _make_contract(self, symbol: str, market: str) -> Any:
        """Create an ib_insync Contract for the given symbol and market."""
        if market == "forex":
            # Forex symbols are like "EUR/USD" — take the base currency.
            pair = symbol.replace("/", "")
            return Forex(pair)
        elif market == "options":
            # Options need full specification; for now create a basic stock option.
            return Option(symbol, exchange="SMART")
        elif market == "commodity":
            return Future(symbol, exchange="NYMEX")
        else:
            # Default: US equity via SMART routing.
            return Stock(symbol, "SMART", "USD")

    @staticmethod
    def _make_ib_order(order: Order, action: str) -> Any:
        """Map a NexusTrade Order to an ib_insync order object."""
        if order.order_type == OrderType.MARKET:
            return MarketOrder(action, order.quantity)
        elif order.order_type == OrderType.LIMIT:
            return LimitOrder(action, order.quantity, order.price or 0.0)
        elif order.order_type == OrderType.STOP:
            return StopOrder(action, order.quantity, order.stop_price or order.price or 0.0)
        elif order.order_type == OrderType.STOP_LIMIT:
            return StopLimitOrder(
                action,
                order.quantity,
                order.price or 0.0,
                order.stop_price or 0.0,
            )
        else:
            raise ValueError(f"Unsupported order type: {order.order_type}")

    async def _wait_for_fill(self, trade: Any, timeout: float = 5.0) -> Any:
        """Wait up to *timeout* seconds for the trade to fill."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if trade.orderStatus and trade.orderStatus.status in (
                "Filled",
                "Cancelled",
                "Inactive",
            ):
                break
            await asyncio.sleep(0.1)
            await asyncio.to_thread(self._ib.sleep, 0)  # pump IB event loop
        return trade

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Inactive": OrderStatus.REJECTED,
            "PreSubmitted": OrderStatus.PENDING,
            "Submitted": OrderStatus.PENDING,
            "PendingSubmit": OrderStatus.PENDING,
            "PendingCancel": OrderStatus.PENDING,
            "ApiPending": OrderStatus.PENDING,
            "ApiCancelled": OrderStatus.CANCELLED,
        }
        return mapping.get(status, OrderStatus.PENDING)

    @staticmethod
    def _detect_market(contract: Any) -> str:
        """Best-effort market detection from an IB contract."""
        sec_type = getattr(contract, "secType", "STK")
        if sec_type == "CASH":
            return "forex"
        elif sec_type == "OPT":
            return "options"
        elif sec_type == "FUT":
            return "commodity"
        return "us_equity"
