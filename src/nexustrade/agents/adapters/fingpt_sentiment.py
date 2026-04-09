"""FinGPT sentiment agent adapter.

Wraps the FinGPT gRPC service to produce trading signals from
LLM-based financial sentiment analysis.  When the FinGPT service is
unavailable the adapter returns a HOLD signal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from nexustrade.core.interfaces import AgentInterface
from nexustrade.core.models import AgentSignal, MarketContext, SignalDirection

logger = logging.getLogger(__name__)


class FinGPTSentimentAdapter(AgentInterface):
    """Agent adapter backed by a FinGPT gRPC sentiment service.

    Parameters
    ----------
    grpc_host:
        Address of the FinGPT gRPC server (e.g. ``"localhost:50052"``).
    model_name:
        Name of the sentiment model to use.
    """

    def __init__(
        self,
        grpc_host: str = "localhost:50052",
        model_name: str = "fingpt_default",
    ) -> None:
        self._grpc_host = grpc_host
        self._model_name = model_name

    @property
    def name(self) -> str:
        return "fingpt_sentiment"

    @property
    def agent_type(self) -> str:
        return "sentiment"

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Call the FinGPT gRPC AnalyzeSentiment endpoint.

        In production this would:
        1. Extract headlines from ``context.news``
        2. Send a SentimentRequest to the gRPC service
        3. Aggregate sentiment scores into a SignalDirection

        For now, returns HOLD indicating the service is not connected.
        """
        headline_count = len(context.news) if context.news else 0
        logger.info(
            "FinGPT agent: service at %s not connected, returning HOLD for %s "
            "(%d headlines available)",
            self._grpc_host,
            context.symbol,
            headline_count,
        )
        return AgentSignal(
            direction=SignalDirection.HOLD,
            confidence=0.0,
            reasoning=(
                f"FinGPT gRPC service at {self._grpc_host} is not connected. "
                f"Model '{self._model_name}' unavailable. "
                f"{headline_count} headlines would be analyzed. Defaulting to HOLD."
            ),
            agent_name=self.name,
            agent_type=self.agent_type,
            timestamp=datetime.now(timezone.utc),
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "markets": ["us_equity", "india_equity", "crypto"],
            "timeframes": ["1d"],
            "requires_vision": False,
            "requires_llm": False,
            "requires_grpc": True,
            "grpc_host": self._grpc_host,
            "model_name": self._model_name,
            "analyzes_news": True,
        }
