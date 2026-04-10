"""CCXT broker backend for crypto exchange order execution.

Wraps the ``ccxt`` library for unified access to 100+ exchanges.
Falls back gracefully when ``ccxt`` is not installed.
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
    import ccxt as _ccxt

    _HAS_CCXT = True
except ImportError:  # pragma: no cover
    _HAS_CCXT = False
    _ccxt = None  # type: ignore[assignment]


class CCXTBrokerBackend(BrokerBackendInterface):
    """CCXT-based crypto-exchange broker backend.

    Parameters
    ----------
    exchange_id:
        CCXT exchange identifier (e.g. ``"binance"``, ``"kraken"``).
    api_key:
        Exchange API key.
    secret:
        Exchange API secret.
    sandbox:
        Use the exchange sandbox/testnet when ``True``.
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str = "",
        secret: str = "",
        sandbox: bool = True,
    ) -> None:
        self._exchange_id = exchange_id
        self._sandbox = sandbox
        self._exchange: Any = None

        if _HAS_CCXT:
            exchange_class = getattr(_ccxt, exchange_id, None)
            if exchange_class is None:
                raise ValueError(f"Unknown CCXT exchange: {exchange_id}")
            self._exchange = exchange_class(
                {
                    "apiKey": api_key,
                    "secret": secret,
                    "enableRateLimit": True,
                }
            )
            if sandbox:
                self._exchange.set_sandbox_mode(True)

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return f"ccxt_{self._exchange_id}"

    @property
    def is_paper(self) -> bool:
        return self._sandbox

    @property
    def supported_markets(self) -> list[str]:
        return ["crypto"]

    # -- required interface methods ------------------------------------------

    async def place_order(self, order: Order) -> Fill:
        """Submit an order to the exchange via CCXT."""
        self._ensure_exchange()

        side = "buy" if order.side == OrderSide.BUY else "sell"
        order_type = order.order_type.value  # "market", "limit", etc.

        result = await asyncio.to_thread(
            self._exchange.create_order,
            order.symbol,
            order_type,
            side,
            order.quantity,
            order.price,
        )

        return Fill(
            order_id=str(result.get("id", "")),
            symbol=order.symbol,
            side=order.side,
            filled_qty=float(result.get("filled", order.quantity)),
            avg_price=float(result.get("average", result.get("price", order.price or 0.0))),
            timestamp=datetime.now(UTC),
            broker=self.name,
            status=self._map_status(result.get("status", "open")),
            fees=float(result.get("fee", {}).get("cost", 0.0)) if result.get("fee") else 0.0,
            metadata={"ccxt_order": result},
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order on the exchange."""
        self._ensure_exchange()
        try:
            await asyncio.to_thread(self._exchange.cancel_order, order_id)
            return True
        except Exception:
            logger.exception("Failed to cancel CCXT order %s", order_id)
            return False

    async def get_positions(self) -> list[Position]:
        """Fetch open positions from the exchange."""
        self._ensure_exchange()
        try:
            raw = await asyncio.to_thread(self._exchange.fetch_positions)
        except Exception:
            # Not all exchanges support fetch_positions
            logger.warning(
                "%s does not support fetch_positions, returning balances",
                self._exchange_id,
            )
            return await self._positions_from_balance()

        positions: list[Position] = []
        for p in raw:
            qty = float(p.get("contracts", 0))
            if qty == 0:
                continue
            positions.append(
                Position(
                    symbol=p.get("symbol", ""),
                    quantity=qty,
                    avg_entry_price=float(p.get("entryPrice", 0)),
                    current_price=float(p.get("markPrice", p.get("entryPrice", 0))),
                    unrealized_pnl=float(p.get("unrealizedPnl", 0)),
                    broker=self.name,
                    market="crypto",
                )
            )
        return positions

    async def get_account(self) -> dict[str, Any]:
        """Return exchange account balance."""
        self._ensure_exchange()
        balance = await asyncio.to_thread(self._exchange.fetch_balance)
        return {
            "broker": self.name,
            "total": balance.get("total", {}),
            "free": balance.get("free", {}),
            "used": balance.get("used", {}),
        }

    async def health_check(self) -> bool:
        """Verify exchange connectivity."""
        if not self._exchange:
            return False
        try:
            await asyncio.to_thread(self._exchange.fetch_time)
            return True
        except Exception:
            return False

    # -- internals -----------------------------------------------------------

    def _ensure_exchange(self) -> None:
        if not _HAS_CCXT:
            raise RuntimeError(
                "ccxt is not installed. Install with: pip install ccxt"
            )
        if not self._exchange:
            raise RuntimeError("CCXT exchange not initialized")

    async def _positions_from_balance(self) -> list[Position]:
        """Derive positions from balance for spot exchanges."""
        balance = await asyncio.to_thread(self._exchange.fetch_balance)
        positions: list[Position] = []
        for currency, amount in balance.get("total", {}).items():
            if float(amount) > 0 and currency not in ("USDT", "USD", "BUSD", "USDC"):
                positions.append(
                    Position(
                        symbol=f"{currency}/USDT",
                        quantity=float(amount),
                        avg_entry_price=0.0,
                        current_price=0.0,
                        unrealized_pnl=0.0,
                        broker=self.name,
                        market="crypto",
                    )
                )
        return positions

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "closed": OrderStatus.FILLED,
            "open": OrderStatus.PENDING,
            "canceled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.CANCELLED,
        }
        return mapping.get(status.lower(), OrderStatus.PENDING)
