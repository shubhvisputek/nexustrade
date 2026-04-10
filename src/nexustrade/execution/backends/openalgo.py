"""OpenAlgo broker backend.

Communicates with a local OpenAlgo instance over HTTP for Indian broker
order execution (Zerodha, Dhan, Angel One, etc.).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from nexustrade.core.interfaces import BrokerBackendInterface
from nexustrade.core.models import Fill, Order, OrderStatus, Position

logger = logging.getLogger(__name__)


class OpenAlgoBackend(BrokerBackendInterface):
    """OpenAlgo HTTP client backend for Indian brokers.

    Parameters
    ----------
    host:
        OpenAlgo server URL (e.g. ``http://localhost:5000``).
    api_key:
        OpenAlgo API key.
    """

    def __init__(
        self,
        host: str = "http://localhost:5000",
        api_key: str = "",
    ) -> None:
        self._host = host.rstrip("/")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._host,
            timeout=30.0,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "openalgo"

    @property
    def is_paper(self) -> bool:
        return False

    @property
    def supported_markets(self) -> list[str]:
        return ["india_equity"]

    # -- required interface methods ------------------------------------------

    async def place_order(self, order: Order) -> Fill:
        """Submit an order through OpenAlgo."""
        payload = {
            "symbol": order.symbol,
            "action": order.side.value.upper(),
            "exchange": order.metadata.get("exchange", "NSE"),
            "pricetype": order.order_type.value.upper(),
            "product": order.metadata.get("product", "MIS"),
            "quantity": str(int(order.quantity)),
        }
        if order.price is not None:
            payload["price"] = str(order.price)

        try:
            resp = await self._client.post("/api/v1/placeorder", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OpenAlgo place_order failed: {exc}") from exc

        order_id = data.get("orderid", data.get("order_id", "unknown"))
        status_str = data.get("status", "pending")

        return Fill(
            order_id=str(order_id),
            symbol=order.symbol,
            side=order.side,
            filled_qty=order.quantity,
            avg_price=order.price or 0.0,
            timestamp=datetime.now(UTC),
            broker="openalgo",
            status=self._map_status(status_str),
            fees=0.0,
            metadata={"openalgo_response": data},
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order through OpenAlgo."""
        try:
            resp = await self._client.post(
                "/api/v1/cancelorder",
                json={"orderid": order_id},
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError:
            logger.exception("Failed to cancel OpenAlgo order %s", order_id)
            return False

    async def get_positions(self) -> list[Position]:
        """Fetch position book from OpenAlgo."""
        try:
            resp = await self._client.get("/api/v1/positionbook")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OpenAlgo get_positions failed: {exc}") from exc

        positions: list[Position] = []
        for item in data.get("data", data.get("positions", [])):
            qty = float(item.get("quantity", item.get("netqty", 0)))
            if qty == 0:
                continue
            positions.append(
                Position(
                    symbol=item.get("symbol", item.get("tradingsymbol", "")),
                    quantity=qty,
                    avg_entry_price=float(item.get("averageprice", item.get("buyavgprice", 0))),
                    current_price=float(item.get("ltp", item.get("lastprice", 0))),
                    unrealized_pnl=float(item.get("pnl", item.get("unrealised", 0))),
                    broker="openalgo",
                    market="india_equity",
                )
            )
        return positions

    async def get_account(self) -> dict[str, Any]:
        """Fetch fund/margin information from OpenAlgo."""
        try:
            resp = await self._client.get("/api/v1/funds")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OpenAlgo get_account failed: {exc}") from exc

        return {
            "broker": "openalgo",
            "cash": float(data.get("availablecash", data.get("cash", 0))),
            "margin_used": float(data.get("marginused", data.get("utiliseddebits", 0))),
            "raw": data,
        }

    async def health_check(self) -> bool:
        """Check if the OpenAlgo instance is reachable."""
        try:
            resp = await self._client.get("/")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        s = status.lower()
        if s in ("complete", "filled", "success"):
            return OrderStatus.FILLED
        if s in ("cancelled", "canceled"):
            return OrderStatus.CANCELLED
        if s in ("rejected",):
            return OrderStatus.REJECTED
        return OrderStatus.PENDING
