"""Interactive Brokers backend — stub / placeholder.

Full implementation will use ``ib_insync`` for TWS/Gateway connectivity.
All methods raise ``NotImplementedError`` with a helpful message until
the adapter is completed.
"""

from __future__ import annotations

from typing import Any

from nexustrade.core.interfaces import BrokerBackendInterface
from nexustrade.core.models import Fill, Order, Position


_NOT_IMPL_MSG = (
    "Interactive Brokers backend is not yet implemented. "
    "Planned integration via ib_insync. "
    "See https://github.com/erdewit/ib_insync for the upstream project."
)


class IBBackend(BrokerBackendInterface):
    """Interactive Brokers stub backend.

    All methods raise ``NotImplementedError``.  This placeholder ensures
    the entry-point registration works and the class can be instantiated
    for config validation.
    """

    @property
    def name(self) -> str:
        return "ib"

    @property
    def is_paper(self) -> bool:
        return True

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity", "forex"]

    async def place_order(self, order: Order) -> Fill:
        raise NotImplementedError(_NOT_IMPL_MSG)

    async def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError(_NOT_IMPL_MSG)

    async def get_positions(self) -> list[Position]:
        raise NotImplementedError(_NOT_IMPL_MSG)

    async def get_account(self) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPL_MSG)
