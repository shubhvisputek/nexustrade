"""QuantAgent vision adapter.

Analyzes chart images using a vision-capable LLM to produce trading signals.
When the vision LLM is unavailable the adapter returns a HOLD signal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from nexustrade.core.interfaces import AgentInterface
from nexustrade.core.models import AgentSignal, MarketContext, SignalDirection

logger = logging.getLogger(__name__)


class QuantAgentVisionAdapter(AgentInterface):
    """Vision-based chart analysis agent.

    In production this would:
    1. Obtain a chart image from the data provider (TradingView MCP)
    2. Send the image to a vision-capable LLM (GPT-4o, Claude, etc.)
    3. Parse the LLM response into a trading signal

    Parameters
    ----------
    llm_channel:
        LLM channel to use for vision analysis (default: ``"vision"``).
    """

    def __init__(self, llm_channel: str = "vision") -> None:
        self._llm_channel = llm_channel

    @property
    def name(self) -> str:
        return "quantagent_vision"

    @property
    def agent_type(self) -> str:
        return "vision"

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Analyze chart image with a vision LLM.

        For now, returns HOLD indicating the vision service is not connected.
        """
        logger.info(
            "QuantAgent vision: vision LLM not connected, returning HOLD for %s",
            context.symbol,
        )
        return AgentSignal(
            direction=SignalDirection.HOLD,
            confidence=0.0,
            reasoning=(
                "Vision LLM is not connected. Chart analysis unavailable. "
                "Defaulting to HOLD."
            ),
            agent_name=self.name,
            agent_type=self.agent_type,
            timestamp=datetime.now(timezone.utc),
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "markets": ["us_equity", "india_equity", "crypto", "forex"],
            "timeframes": ["1d", "4h", "1h", "15m"],
            "requires_vision": True,
            "requires_llm": True,
            "llm_channel": self._llm_channel,
            "analyzes_charts": True,
        }
