"""TradingView webhook relay backend.

Generates TradingView-compatible alert JSON payloads.  This is *not* a
full broker — it formats the payload that TradingView Pine Script alerts
would send to a webhook endpoint.  Actual execution happens when the
TradingView alert fires and hits the :mod:`nexustrade.execution.webhooks`
receiver.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from nexustrade.core.interfaces import BrokerBackendInterface
from nexustrade.core.models import Fill, Order, OrderSide, OrderStatus, Position


class TradingViewBackend(BrokerBackendInterface):
    """TradingView alert-payload generator.

    Orders are formatted as TV alert JSON and marked as
    ``pending_tv_execution``.  They are **not** sent anywhere — a
    separate webhook receiver handles the actual execution when
    TradingView fires the alert.

    Parameters
    ----------
    passphrase:
        Shared secret for webhook authentication.
    """

    def __init__(self, passphrase: str = "") -> None:
        self._passphrase = passphrase
        self._pending: dict[str, dict[str, Any]] = {}

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "tradingview"

    @property
    def is_paper(self) -> bool:
        return True  # TV relay is not a real broker

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity", "india_equity", "crypto", "forex"]

    # -- required interface methods ------------------------------------------

    async def place_order(self, order: Order) -> Fill:
        """Generate a TradingView alert payload for the order."""
        order_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc)

        alert_payload = {
            "passphrase": self._passphrase,
            "ticker": order.symbol,
            "action": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "price": order.price,
            "stop_price": order.stop_price,
            "time_in_force": order.time_in_force,
            "strategy": order.strategy_name,
            "order_id": order_id,
            "timestamp": now.isoformat(),
        }

        self._pending[order_id] = alert_payload

        return Fill(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            filled_qty=0.0,  # Not filled yet
            avg_price=order.price or 0.0,
            timestamp=now,
            broker="tradingview",
            status=OrderStatus.PENDING,
            fees=0.0,
            metadata={
                "tv_alert_payload": alert_payload,
                "pending_tv_execution": True,
            },
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Remove a pending TV alert."""
        return self._pending.pop(order_id, None) is not None

    async def get_positions(self) -> list[Position]:
        """TV relay does not track positions."""
        return []

    async def get_account(self) -> dict[str, Any]:
        """TV relay has no account info."""
        return {
            "broker": "tradingview",
            "note": "TradingView relay — no account data available",
            "pending_alerts": len(self._pending),
        }

    # -- TV-specific helpers -------------------------------------------------

    def get_alert_json(self, order_id: str) -> str:
        """Return the TradingView alert payload as a JSON string."""
        if order_id not in self._pending:
            raise KeyError(f"No pending alert for order_id={order_id}")
        return json.dumps(self._pending[order_id])

    def get_all_pending(self) -> dict[str, dict[str, Any]]:
        """Return all pending alert payloads."""
        return dict(self._pending)
