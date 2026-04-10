"""FinRL agent adapter.

Wraps the FinRL gRPC service to produce trading signals from
reinforcement-learning policy predictions.  When the FinRL service is
unavailable the adapter returns a HOLD signal.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from nexustrade.core.interfaces import AgentInterface
from nexustrade.core.models import AgentSignal, MarketContext, SignalDirection

logger = logging.getLogger(__name__)


class FinRLAgentAdapter(AgentInterface):
    """Agent adapter backed by a FinRL gRPC service.

    Parameters
    ----------
    grpc_host:
        Address of the FinRL gRPC server (e.g. ``"localhost:50051"``).
    model_name:
        Name of the RL model to use for predictions.
    """

    def __init__(
        self,
        grpc_host: str = "localhost:50051",
        model_name: str = "ppo_default",
    ) -> None:
        self._grpc_host = grpc_host
        self._model_name = model_name

    @property
    def name(self) -> str:
        return "finrl"

    @property
    def agent_type(self) -> str:
        return "rl"

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Call the FinRL gRPC Predict endpoint.

        In production this would:
        1. Build an observation vector from ``context`` (prices, volume, technicals)
        2. Send a PredictRequest to the gRPC service
        3. Map the action float to a SignalDirection

        For now, returns HOLD indicating the service is not connected.
        """
        logger.info(
            "FinRL agent: service at %s not connected, returning HOLD for %s",
            self._grpc_host,
            context.symbol,
        )
        return AgentSignal(
            direction=SignalDirection.HOLD,
            confidence=0.0,
            reasoning=(
                f"FinRL gRPC service at {self._grpc_host} is not connected. "
                f"Model '{self._model_name}' unavailable. Defaulting to HOLD."
            ),
            agent_name=self.name,
            agent_type=self.agent_type,
            timestamp=datetime.now(UTC),
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "markets": ["us_equity", "crypto"],
            "timeframes": ["1d", "4h", "1h"],
            "requires_vision": False,
            "requires_llm": False,
            "requires_grpc": True,
            "grpc_host": self._grpc_host,
            "model_name": self._model_name,
        }
