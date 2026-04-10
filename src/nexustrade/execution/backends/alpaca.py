"""Alpaca broker backend.

Wraps the ``alpaca-py`` SDK for US-equity order execution.
Falls back gracefully when ``alpaca-py`` is not installed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from nexustrade.core.interfaces import BrokerBackendInterface
from nexustrade.core.models import Fill, Order, OrderSide, OrderStatus, Position

logger = logging.getLogger(__name__)

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide as AlpacaSide
    from alpaca.trading.enums import TimeInForce
    from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

    _HAS_ALPACA = True
except ImportError:  # pragma: no cover
    _HAS_ALPACA = False


class AlpacaBackend(BrokerBackendInterface):
    """Alpaca US-equity broker backend.

    Parameters
    ----------
    api_key:
        Alpaca API key.
    secret_key:
        Alpaca secret key.
    paper:
        Use paper-trading endpoint when ``True`` (default).
    """

    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        paper: bool = True,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._paper = paper
        self._client: Any = None

        if _HAS_ALPACA and api_key:
            self._client = TradingClient(
                api_key=api_key,
                secret_key=secret_key,
                paper=paper,
            )

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "alpaca"

    @property
    def is_paper(self) -> bool:
        return self._paper

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity"]

    # -- required interface methods ------------------------------------------

    async def place_order(self, order: Order) -> Fill:
        """Submit an order via Alpaca and return the fill."""
        self._ensure_client()

        alpaca_side = AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL

        tif_map = {
            "GTC": TimeInForce.GTC,
            "DAY": TimeInForce.DAY,
            "IOC": TimeInForce.IOC,
        }
        tif = tif_map.get(order.time_in_force.upper(), TimeInForce.GTC)

        if order.order_type.value == "market":
            request = MarketOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=alpaca_side,
                time_in_force=tif,
            )
        else:
            request = LimitOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=alpaca_side,
                time_in_force=tif,
                limit_price=order.price,
            )

        result = await asyncio.to_thread(self._client.submit_order, request)

        return Fill(
            order_id=str(result.id),
            symbol=order.symbol,
            side=order.side,
            filled_qty=float(result.filled_qty or order.quantity),
            avg_price=float(result.filled_avg_price or order.price or 0.0),
            timestamp=datetime.now(UTC),
            broker="alpaca",
            status=self._map_status(str(result.status)),
            fees=0.0,
            slippage=0.0,
            metadata={"alpaca_order_id": str(result.id)},
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order on Alpaca."""
        self._ensure_client()
        try:
            await asyncio.to_thread(self._client.cancel_order_by_id, order_id)
            return True
        except Exception:
            logger.exception("Failed to cancel Alpaca order %s", order_id)
            return False

    async def get_positions(self) -> list[Position]:
        """Fetch all open positions from Alpaca."""
        self._ensure_client()
        raw = await asyncio.to_thread(self._client.get_all_positions)
        positions: list[Position] = []
        for p in raw:
            positions.append(
                Position(
                    symbol=p.symbol,
                    quantity=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    unrealized_pnl=float(p.unrealized_pl),
                    realized_pnl=0.0,
                    broker="alpaca",
                    market="us_equity",
                )
            )
        return positions

    async def get_account(self) -> dict[str, Any]:
        """Return Alpaca account summary."""
        self._ensure_client()
        acct = await asyncio.to_thread(self._client.get_account)
        return {
            "cash": float(acct.cash),
            "equity": float(acct.equity),
            "buying_power": float(acct.buying_power),
            "portfolio_value": float(acct.portfolio_value),
            "broker": "alpaca",
            "paper": self._paper,
        }

    async def health_check(self) -> bool:
        """Check Alpaca connectivity."""
        if not self._client:
            return False
        try:
            await asyncio.to_thread(self._client.get_account)
            return True
        except Exception:
            return False

    # -- internals -----------------------------------------------------------

    def _ensure_client(self) -> None:
        if not _HAS_ALPACA:
            raise RuntimeError(
                "alpaca-py is not installed. "
                "Install with: pip install alpaca-py"
            )
        if not self._client:
            raise RuntimeError(
                "Alpaca client not initialized — provide api_key and secret_key"
            )

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "filled": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIAL,
            "canceled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "new": OrderStatus.PENDING,
            "accepted": OrderStatus.PENDING,
            "pending_new": OrderStatus.PENDING,
        }
        return mapping.get(status.lower(), OrderStatus.PENDING)
