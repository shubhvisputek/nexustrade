"""Execution engine — routes orders to the correct broker backend.

Supports three execution modes:

- ``python``: direct API execution through broker backends
- ``tradingview``: route through TradingView webhook relay
- ``both``: fire to both paths simultaneously
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nexustrade.core.interfaces import BrokerBackendInterface
from nexustrade.core.models import Fill, Order

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Route orders to the appropriate broker backend based on mode and market.

    Parameters
    ----------
    mode:
        Execution mode — ``"python"``, ``"tradingview"``, or ``"both"``.
    brokers:
        Mapping of broker name to backend instance.
    market_broker_map:
        Mapping of market type to broker name (e.g.
        ``{"us_equity": "alpaca", "crypto": "ccxt_binance"}``).
    tv_broker_name:
        Name of the TradingView backend in *brokers* dict.
    """

    def __init__(
        self,
        mode: str = "python",
        brokers: dict[str, BrokerBackendInterface] | None = None,
        market_broker_map: dict[str, str] | None = None,
        tv_broker_name: str = "tradingview",
    ) -> None:
        if mode not in ("python", "tradingview", "both"):
            raise ValueError(f"Invalid execution mode: {mode!r}. Must be 'python', 'tradingview', or 'both'")

        self._mode = mode
        self._brokers = brokers or {}
        self._market_broker_map = market_broker_map or {}
        self._tv_broker_name = tv_broker_name

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def brokers(self) -> dict[str, BrokerBackendInterface]:
        return dict(self._brokers)

    async def execute(self, order: Order, market: str = "us_equity") -> Fill:
        """Execute an order through the configured path(s).

        Parameters
        ----------
        order:
            The order to execute.
        market:
            Market type used to look up the broker (e.g. ``"us_equity"``).

        Returns
        -------
        Fill
            The fill from the primary execution path.  In ``"both"`` mode,
            the direct-broker fill is returned; the TV relay fill is
            logged but not returned.
        """
        if self._mode == "python":
            return await self._execute_python(order, market)
        elif self._mode == "tradingview":
            return await self._execute_tradingview(order)
        else:
            # "both" — fire to both paths
            return await self._execute_both(order, market)

    def get_broker(self, market: str) -> BrokerBackendInterface:
        """Look up the broker for a given market."""
        broker_name = self._market_broker_map.get(market)
        if broker_name is None:
            raise RuntimeError(f"No broker configured for market: {market}")
        broker = self._brokers.get(broker_name)
        if broker is None:
            raise RuntimeError(f"Broker '{broker_name}' not found in registered brokers")
        return broker

    # -- private -------------------------------------------------------------

    async def _execute_python(self, order: Order, market: str) -> Fill:
        """Direct broker API execution."""
        broker = self.get_broker(market)
        logger.info(
            "Executing via %s: %s %s %s",
            broker.name,
            order.side.value,
            order.quantity,
            order.symbol,
        )
        return await broker.place_order(order)

    async def _execute_tradingview(self, order: Order) -> Fill:
        """Route through TradingView webhook relay."""
        tv = self._brokers.get(self._tv_broker_name)
        if tv is None:
            raise RuntimeError(
                f"TradingView backend '{self._tv_broker_name}' not registered"
            )
        logger.info(
            "Generating TV alert: %s %s %s",
            order.side.value,
            order.quantity,
            order.symbol,
        )
        return await tv.place_order(order)

    async def _execute_both(self, order: Order, market: str) -> Fill:
        """Fire to both direct broker and TradingView relay."""
        python_coro = self._execute_python(order, market)
        tv_coro = self._execute_tradingview(order)

        results = await asyncio.gather(python_coro, tv_coro, return_exceptions=True)

        python_result = results[0]
        tv_result = results[1]

        if isinstance(tv_result, Exception):
            logger.warning("TV relay failed: %s", tv_result)
        else:
            logger.info("TV alert generated: order_id=%s", tv_result.order_id)

        if isinstance(python_result, Exception):
            raise python_result  # type: ignore[misc]

        return python_result
