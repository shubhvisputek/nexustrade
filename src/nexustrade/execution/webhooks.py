"""TradingView webhook receiver.

Provides a FastAPI router that accepts incoming TradingView alert
webhooks, validates the shared passphrase, and routes the order to
the appropriate broker backend.
"""

from __future__ import annotations

import logging
from typing import Any

from nexustrade.core.interfaces import BrokerBackendInterface
from nexustrade.core.models import Order, OrderSide, OrderType

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, HTTPException, Request

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


def create_webhook_router(
    passphrase: str,
    brokers: dict[str, BrokerBackendInterface],
    default_broker: str = "paper",
) -> Any:
    """Create and return a FastAPI router for TradingView webhooks.

    Parameters
    ----------
    passphrase:
        Shared secret that must match the ``passphrase`` field in the
        incoming JSON payload.
    brokers:
        Mapping of broker name to backend instance.
    default_broker:
        Broker to use when the payload does not specify one.

    Returns
    -------
    fastapi.APIRouter
        Mount this on a FastAPI app with ``app.include_router(router)``.
    """
    if not _HAS_FASTAPI:
        raise RuntimeError(
            "FastAPI is not installed. Install with: pip install fastapi"
        )

    router = APIRouter(tags=["webhooks"])

    @router.post("/webhook")
    async def receive_webhook(request: Request) -> dict[str, Any]:
        """Receive and process a TradingView alert webhook.

        Expects a JSON body with at least:
        - ``passphrase``: shared secret
        - ``ticker``: symbol
        - ``action``: ``"buy"`` or ``"sell"``

        Optional fields:
        - ``order_type``: ``"market"`` (default), ``"limit"``, etc.
        - ``quantity``: number of shares/contracts (default: 1)
        - ``price``: limit price
        - ``broker``: which broker backend to use
        """
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        # Validate passphrase
        incoming_passphrase = payload.get("passphrase", "")
        if incoming_passphrase != passphrase:
            raise HTTPException(status_code=401, detail="Invalid passphrase")

        # Parse order from payload
        ticker = payload.get("ticker", "")
        action = payload.get("action", "").lower()
        if not ticker or action not in ("buy", "sell"):
            raise HTTPException(
                status_code=400,
                detail="Missing or invalid ticker/action",
            )

        order_type_str = payload.get("order_type", "market").lower()
        try:
            order_type = OrderType(order_type_str)
        except ValueError:
            order_type = OrderType.MARKET

        order = Order(
            symbol=ticker,
            side=OrderSide.BUY if action == "buy" else OrderSide.SELL,
            order_type=order_type,
            quantity=float(payload.get("quantity", 1)),
            price=float(payload["price"]) if payload.get("price") else None,
            strategy_name=payload.get("strategy", "tradingview_webhook"),
            metadata={"source": "tradingview_webhook", "raw_payload": payload},
        )

        # Route to broker
        broker_name = payload.get("broker", default_broker)
        broker = brokers.get(broker_name)
        if broker is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown broker: {broker_name}",
            )

        try:
            fill = await broker.place_order(order)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        logger.info(
            "Webhook order executed: %s %s %s @ %s via %s",
            fill.side.value,
            fill.filled_qty,
            fill.symbol,
            fill.avg_price,
            broker_name,
        )

        return {
            "status": "ok",
            "order_id": fill.order_id,
            "symbol": fill.symbol,
            "side": fill.side.value,
            "filled_qty": fill.filled_qty,
            "avg_price": fill.avg_price,
            "broker": broker_name,
        }

    return router
