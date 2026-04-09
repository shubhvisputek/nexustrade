"""AI Hedge Fund persona agent adapter.

Creates persona agents inspired by the ai-hedge-fund project. Each persona
agent uses a Jinja2 prompt template and an LLM to produce a trading signal
from the perspective of a famous investor.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from nexustrade.agents.prompt_loader import PromptLoader
from nexustrade.core.interfaces import AgentInterface
from nexustrade.core.models import AgentSignal, MarketContext, SignalDirection

logger = logging.getLogger(__name__)


def _parse_signal_response(text: str, agent_name: str) -> AgentSignal:
    """Parse an LLM JSON response into an AgentSignal.

    Handles markdown code blocks (```json ... ```) and bare JSON.
    Returns a HOLD signal with low confidence on parse failure.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.strip().rstrip("`")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse JSON from %s response, returning HOLD",
                    agent_name,
                )
                return AgentSignal(
                    direction=SignalDirection.HOLD,
                    confidence=0.1,
                    reasoning=f"Failed to parse LLM response: {text[:200]}",
                    agent_name=agent_name,
                    agent_type="persona",
                )
        else:
            logger.warning(
                "No JSON found in %s response, returning HOLD",
                agent_name,
            )
            return AgentSignal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reasoning=f"No JSON found in LLM response: {text[:200]}",
                agent_name=agent_name,
                agent_type="persona",
            )

    # Extract fields with safe defaults
    raw_direction = str(data.get("direction", "hold")).lower().strip()
    direction_map = {
        "strong_buy": SignalDirection.STRONG_BUY,
        "buy": SignalDirection.BUY,
        "hold": SignalDirection.HOLD,
        "sell": SignalDirection.SELL,
        "strong_sell": SignalDirection.STRONG_SELL,
        "bullish": SignalDirection.BUY,
        "bearish": SignalDirection.SELL,
    }
    direction = direction_map.get(raw_direction, SignalDirection.HOLD)

    raw_confidence = data.get("confidence", 0.5)
    try:
        confidence = float(raw_confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    reasoning = str(data.get("reasoning", data.get("analysis", "")))

    return AgentSignal(
        direction=direction,
        confidence=confidence,
        reasoning=reasoning,
        agent_name=agent_name,
        agent_type="persona",
        metadata=data.get("metadata", {}),
    )


class PersonaAgent(AgentInterface):
    """A single persona agent that mimics a famous investor's analysis style.

    Uses a Jinja2 template for the system/user prompt and routes through
    an LLM to produce trading signals.
    """

    def __init__(
        self,
        agent_name: str,
        prompt_loader: PromptLoader,
        llm_router: Any,
    ) -> None:
        self._agent_name = agent_name
        self._prompt_loader = prompt_loader
        self._llm_router = llm_router

    @property
    def name(self) -> str:
        return self._agent_name

    @property
    def agent_type(self) -> str:
        return "persona"

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "requires_vision": False,
            "requires_gpu": False,
            "llm_channel": "fast",
            "supported_markets": [
                "us_equity",
                "crypto",
                "forex",
                "india_equity",
            ],
        }

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Produce a trading signal by rendering the persona prompt and calling the LLM."""
        try:
            # Prepare template variables from context
            technicals_dict = {
                tf: ind.to_dict() if hasattr(ind, "to_dict") else str(ind)
                for tf, ind in context.technicals.items()
            }
            ohlcv_dict = {
                tf: [bar.to_dict() if hasattr(bar, "to_dict") else str(bar) for bar in bars]
                for tf, bars in context.ohlcv.items()
            }
            news_list = [
                item.to_dict() if hasattr(item, "to_dict") else str(item)
                for item in context.news
            ]

            prompt = self._prompt_loader.render_agent_prompt(
                self._agent_name,
                symbol=context.symbol,
                current_price=context.current_price,
                technicals=technicals_dict,
                fundamentals=context.fundamentals,
                news=news_list,
                ohlcv=ohlcv_dict,
            )

            response = await self._llm_router.complete(
                messages=[{"role": "user", "content": prompt}],
                channel="fast",
            )

            # Extract text from response (handle str or dict)
            if isinstance(response, dict):
                text = response.get("content", response.get("text", str(response)))
            else:
                text = str(response)

            return _parse_signal_response(text, self._agent_name)

        except FileNotFoundError:
            logger.warning(
                "Prompt template not found for %s, returning HOLD",
                self._agent_name,
            )
            return AgentSignal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reasoning=f"Prompt template not found for {self._agent_name}",
                agent_name=self._agent_name,
                agent_type="persona",
            )
        except Exception as e:
            logger.exception("Error in %s analyze", self._agent_name)
            return AgentSignal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reasoning=f"Error during analysis: {e}",
                agent_name=self._agent_name,
                agent_type="persona",
            )


class AIHedgeFundAgentGroup:
    """Factory that creates persona agents inspired by ai-hedge-fund.

    Provides all 18 persona agents, or a filtered subset based on
    configuration.
    """

    AGENTS: list[str] = [
        "warren_buffett",
        "charlie_munger",
        "technical_analyst",
        "ben_graham",
        "peter_lynch",
        "cathie_wood",
        "stanley_druckenmiller",
        "ray_dalio",
        "george_soros",
        "carl_icahn",
        "bill_ackman",
        "david_tepper",
        "joel_greenblatt",
        "seth_klarman",
        "michael_burry",
        "howard_marks",
        "jim_simons",
        "aswath_damodaran",
    ]

    def __init__(
        self,
        prompt_loader: PromptLoader,
        llm_router: Any,
    ) -> None:
        self._prompt_loader = prompt_loader
        self._llm_router = llm_router

    def create_agents(
        self,
        enabled_names: list[str] | None = None,
    ) -> list[PersonaAgent]:
        """Create PersonaAgent instances for the specified (or all) persona names.

        Args:
            enabled_names: List of persona names to enable. If None, all 18 are created.

        Returns:
            List of PersonaAgent instances.
        """
        names = enabled_names if enabled_names is not None else self.AGENTS
        return [
            PersonaAgent(
                agent_name=name,
                prompt_loader=self._prompt_loader,
                llm_router=self._llm_router,
            )
            for name in names
            if name in self.AGENTS
        ]
