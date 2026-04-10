"""Paper trading backend — simulates order execution locally.

All trades are filled immediately at ``current_price * (1 + slippage)``
with a configurable commission.  No external services required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from nexustrade.core.interfaces import BrokerBackendInterface
from nexustrade.core.models import Fill, Order, OrderSide, OrderStatus, Position


class PaperBackend(BrokerBackendInterface):
    """In-memory paper-trading broker.

    Parameters
    ----------
    initial_cash:
        Starting cash balance.
    slippage_pct:
        Proportional slippage applied to each fill price (0.001 = 0.1 %).
    commission_pct:
        Proportional commission on the notional value (0.0005 = 0.05 %).
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        slippage_pct: float = 0.001,
        commission_pct: float = 0.0005,
    ) -> None:
        self._initial_cash = initial_cash
        self._cash = initial_cash
        self._slippage_pct = slippage_pct
        self._commission_pct = commission_pct

        # symbol -> Position
        self._positions: dict[str, Position] = {}
        # order_id -> Order (pending orders only)
        self._pending_orders: dict[str, Order] = {}
        # completed fills
        self._trade_history: list[Fill] = []

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "paper"

    @property
    def is_paper(self) -> bool:
        return True

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity", "india_equity", "crypto", "forex"]

    # -- required interface methods ------------------------------------------

    async def place_order(self, order: Order) -> Fill:
        """Execute *order* immediately with simulated slippage and commission."""
        order_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC)

        # Determine base price
        base_price = order.price if order.price is not None else 0.0
        if base_price <= 0:
            raise RuntimeError(
                "Paper backend requires order.price to be set"
                " (simulated current price)"
            )

        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price = base_price * (1.0 + self._slippage_pct)
        else:
            fill_price = base_price * (1.0 - self._slippage_pct)

        notional = fill_price * order.quantity
        commission = notional * self._commission_pct

        # Validate cash for buys
        if order.side == OrderSide.BUY:
            total_cost = notional + commission
            if total_cost > self._cash:
                raise RuntimeError(
                    f"Insufficient cash: need {total_cost:.2f}, have {self._cash:.2f}"
                )
            self._cash -= total_cost
        else:
            # Sells add cash (minus commission)
            self._cash += notional - commission

        # Update positions
        self._update_position(order, fill_price)

        slippage_amount = abs(fill_price - base_price) * order.quantity

        fill = Fill(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            filled_qty=order.quantity,
            avg_price=fill_price,
            timestamp=now,
            broker="paper",
            status=OrderStatus.FILLED,
            fees=commission,
            slippage=slippage_amount,
            latency_ms=0.0,
            metadata={"simulated": True},
        )
        self._trade_history.append(fill)
        return fill

    async def cancel_order(self, order_id: str) -> bool:
        """Remove a pending order.  Returns ``True`` if found and cancelled."""
        return self._pending_orders.pop(order_id, None) is not None

    async def get_positions(self) -> list[Position]:
        """Return all open positions (non-zero quantity)."""
        return [p for p in self._positions.values() if p.quantity != 0]

    async def get_account(self) -> dict[str, Any]:
        """Return account summary."""
        positions_value = sum(
            p.quantity * p.current_price for p in self._positions.values()
        )
        total_value = self._cash + positions_value
        total_pnl = total_value - self._initial_cash
        return {
            "cash": self._cash,
            "positions_value": positions_value,
            "total_value": total_value,
            "total_pnl": total_pnl,
            "initial_cash": self._initial_cash,
            "num_positions": len(await self.get_positions()),
            "num_trades": len(self._trade_history),
        }

    async def get_order_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent fills as dicts."""
        return [f.to_dict() for f in self._trade_history[-limit:]]

    # -- internals -----------------------------------------------------------

    def _update_position(self, order: Order, fill_price: float) -> None:
        """Create or update the position for *order.symbol*."""
        symbol = order.symbol
        qty = order.quantity if order.side == OrderSide.BUY else -order.quantity

        if symbol in self._positions:
            pos = self._positions[symbol]
            old_qty = pos.quantity
            new_qty = old_qty + qty

            if new_qty == 0:
                # Position closed
                realized = (fill_price - pos.avg_entry_price) * abs(qty)
                if order.side == OrderSide.BUY:
                    # Closing a short
                    realized = (pos.avg_entry_price - fill_price) * abs(qty)
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=0,
                    avg_entry_price=0.0,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    realized_pnl=pos.realized_pnl + realized,
                    broker="paper",
                    market="",
                )
            elif (old_qty > 0 and new_qty > 0) or (old_qty < 0 and new_qty < 0):
                # Adding to position — update avg entry
                if (old_qty > 0 and qty > 0) or (old_qty < 0 and qty < 0):
                    # Same direction: weighted average
                    total_cost = pos.avg_entry_price * abs(old_qty) + fill_price * abs(qty)
                    new_avg = total_cost / abs(new_qty)
                else:
                    # Partial close
                    new_avg = pos.avg_entry_price
                unrealized = (fill_price - new_avg) * new_qty
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=new_qty,
                    avg_entry_price=new_avg,
                    current_price=fill_price,
                    unrealized_pnl=unrealized,
                    realized_pnl=pos.realized_pnl,
                    broker="paper",
                    market="",
                )
            else:
                # Flipping direction — close old, open new remainder
                realized = (fill_price - pos.avg_entry_price) * abs(old_qty)
                if old_qty < 0:
                    realized = (pos.avg_entry_price - fill_price) * abs(old_qty)
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=new_qty,
                    avg_entry_price=fill_price,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    realized_pnl=pos.realized_pnl + realized,
                    broker="paper",
                    market="",
                )
        else:
            # New position
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=qty,
                avg_entry_price=fill_price,
                current_price=fill_price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                broker="paper",
                market="",
            )
