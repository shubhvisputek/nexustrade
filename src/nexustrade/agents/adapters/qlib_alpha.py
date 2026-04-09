"""Qlib alpha factor agent adapter.

Wraps the Qlib gRPC service to produce trading signals from
quantitative alpha factors.  When the Qlib service is unavailable
the adapter returns a HOLD signal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from nexustrade.core.interfaces import AgentInterface
from nexustrade.core.models import AgentSignal, MarketContext, SignalDirection

logger = logging.getLogger(__name__)


class QlibAlphaAdapter(AgentInterface):
    """Agent adapter backed by a Qlib gRPC factor service.

    Parameters
    ----------
    grpc_host:
        Address of the Qlib gRPC server (e.g. ``"localhost:50053"``).
    factor_set:
        Name of the factor set to compute (e.g. ``"alpha158"``).
    """

    def __init__(
        self,
        grpc_host: str = "localhost:50053",
        factor_set: str = "alpha158",
    ) -> None:
        self._grpc_host = grpc_host
        self._factor_set = factor_set

    @property
    def name(self) -> str:
        return "qlib_alpha"

    @property
    def agent_type(self) -> str:
        return "factor"

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Call the Qlib gRPC ComputeFactors endpoint.

        In production this would:
        1. Determine the date range from ``context``
        2. Send a FactorRequest to the gRPC service
        3. Aggregate factor values into a SignalDirection

        For now, returns HOLD indicating the service is not connected.
        """
        logger.info(
            "Qlib alpha agent: service at %s not connected, returning HOLD for %s",
            self._grpc_host,
            context.symbol,
        )
        return AgentSignal(
            direction=SignalDirection.HOLD,
            confidence=0.0,
            reasoning=(
                f"Qlib gRPC service at {self._grpc_host} is not connected. "
                f"Factor set '{self._factor_set}' unavailable. Defaulting to HOLD."
            ),
            agent_name=self.name,
            agent_type=self.agent_type,
            timestamp=datetime.now(timezone.utc),
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "markets": ["us_equity"],
            "timeframes": ["1d"],
            "requires_vision": False,
            "requires_llm": False,
            "requires_grpc": True,
            "grpc_host": self._grpc_host,
            "factor_set": self._factor_set,
        }
