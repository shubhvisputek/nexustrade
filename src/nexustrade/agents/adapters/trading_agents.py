"""TradingAgents debate adapter.

Implements a bull/bear debate pattern where two LLM-powered researchers
argue for and against a trade, then a research manager synthesizes a
final signal.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from nexustrade.agents.prompt_loader import PromptLoader
from nexustrade.core.interfaces import AgentInterface
from nexustrade.core.models import AgentSignal, MarketContext, SignalDirection

logger = logging.getLogger(__name__)


@dataclass
class DebateRound:
    """Record of a single debate round."""

    round_number: int
    bull_argument: str
    bear_argument: str


def _parse_debate_signal(text: str) -> AgentSignal:
    """Parse the research manager's synthesis into an AgentSignal.

    Handles markdown code blocks and bare JSON.
    Returns HOLD with low confidence on failure.
    """
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.strip().rstrip("`")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Failed to parse debate synthesis JSON")
                return AgentSignal(
                    direction=SignalDirection.HOLD,
                    confidence=0.1,
                    reasoning=f"Failed to parse debate synthesis: {text[:200]}",
                    agent_name="bull_bear_debate",
                    agent_type="debate",
                )
        else:
            logger.warning("No JSON found in debate synthesis")
            return AgentSignal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reasoning=f"No JSON found in debate synthesis: {text[:200]}",
                agent_name="bull_bear_debate",
                agent_type="debate",
            )

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

    reasoning = str(data.get("reasoning", data.get("synthesis", "")))

    return AgentSignal(
        direction=direction,
        confidence=confidence,
        reasoning=reasoning,
        agent_name="bull_bear_debate",
        agent_type="debate",
        metadata={
            "bull_summary": data.get("bull_summary", ""),
            "bear_summary": data.get("bear_summary", ""),
        },
    )


class TradingAgentsDebateAdapter(AgentInterface):
    """Bull/bear debate adapter inspired by TradingAgents.

    Runs multiple rounds of structured debate between a bull researcher
    and a bear researcher, then uses a research manager to synthesize
    a final trading signal.
    """

    def __init__(
        self,
        prompt_loader: PromptLoader,
        llm_router: Any,
        rounds: int = 2,
        early_termination_confidence: float = 0.9,
    ) -> None:
        self._prompt_loader = prompt_loader
        self._llm_router = llm_router
        self._rounds = rounds
        self._early_termination_confidence = early_termination_confidence

    @property
    def name(self) -> str:
        return "bull_bear_debate"

    @property
    def agent_type(self) -> str:
        return "debate"

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "requires_vision": False,
            "requires_gpu": False,
            "llm_channel": "deep",
            "supported_markets": [
                "us_equity",
                "crypto",
                "forex",
                "india_equity",
            ],
        }

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Run the bull/bear debate and produce a synthesized signal."""
        try:
            # Prepare context variables
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

            context_vars = {
                "symbol": context.symbol,
                "current_price": context.current_price,
                "technicals": technicals_dict,
                "fundamentals": context.fundamentals,
                "news": news_list,
                "ohlcv": ohlcv_dict,
            }

            rounds: list[DebateRound] = []
            prior_bear = ""

            for round_num in range(1, self._rounds + 1):
                # Bull researcher
                bull_prompt = self._prompt_loader.render_debate_prompt(
                    "bull_researcher",
                    **context_vars,
                    prior_bear_arguments=prior_bear,
                    round_number=round_num,
                    total_rounds=self._rounds,
                )
                bull_response = await self._llm_router.complete(
                    messages=[{"role": "user", "content": bull_prompt}],
                    channel="deep",
                )
                bull_text = (
                    bull_response.get("content", str(bull_response))
                    if isinstance(bull_response, dict)
                    else str(bull_response)
                )

                # Bear researcher
                bear_prompt = self._prompt_loader.render_debate_prompt(
                    "bear_researcher",
                    **context_vars,
                    prior_bull_arguments=bull_text,
                    round_number=round_num,
                    total_rounds=self._rounds,
                )
                bear_response = await self._llm_router.complete(
                    messages=[{"role": "user", "content": bear_prompt}],
                    channel="deep",
                )
                bear_text = (
                    bear_response.get("content", str(bear_response))
                    if isinstance(bear_response, dict)
                    else str(bear_response)
                )

                rounds.append(
                    DebateRound(
                        round_number=round_num,
                        bull_argument=bull_text,
                        bear_argument=bear_text,
                    )
                )

                prior_bear = bear_text

                # Check early termination
                if self._check_early_termination(bull_text, bear_text):
                    logger.info(
                        "Early termination at round %d: both sides agree strongly",
                        round_num,
                    )
                    break

            # Research manager synthesizes
            all_bull = "\n\n---\n\n".join(
                f"Round {r.round_number}:\n{r.bull_argument}" for r in rounds
            )
            all_bear = "\n\n---\n\n".join(
                f"Round {r.round_number}:\n{r.bear_argument}" for r in rounds
            )

            manager_prompt = self._prompt_loader.render_debate_prompt(
                "research_manager",
                **context_vars,
                bull_arguments=all_bull,
                bear_arguments=all_bear,
                num_rounds=len(rounds),
            )
            manager_response = await self._llm_router.complete(
                messages=[{"role": "user", "content": manager_prompt}],
                channel="deep",
            )
            manager_text = (
                manager_response.get("content", str(manager_response))
                if isinstance(manager_response, dict)
                else str(manager_response)
            )

            signal = _parse_debate_signal(manager_text)
            signal.metadata["debate_rounds"] = len(rounds)
            return signal

        except FileNotFoundError as e:
            logger.warning("Debate prompt template not found: %s", e)
            return AgentSignal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reasoning=f"Debate prompt template not found: {e}",
                agent_name="bull_bear_debate",
                agent_type="debate",
            )
        except Exception as e:
            logger.exception("Error during bull/bear debate")
            return AgentSignal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reasoning=f"Error during debate: {e}",
                agent_name="bull_bear_debate",
                agent_type="debate",
            )

    def _check_early_termination(
        self,
        bull_text: str,
        bear_text: str,
    ) -> bool:
        """Check if both sides agree strongly enough to terminate early.

        Looks for explicit confidence values in the responses and checks
        if both exceed the early termination threshold in the same direction.
        """
        try:
            bull_data = self._try_extract_json(bull_text)
            bear_data = self._try_extract_json(bear_text)

            if not bull_data or not bear_data:
                return False

            bull_dir = str(bull_data.get("direction", "")).lower()
            bear_dir = str(bear_data.get("direction", "")).lower()

            bull_conf = float(bull_data.get("confidence", 0))
            bear_conf = float(bear_data.get("confidence", 0))

            # Both agree on direction and both are very confident
            if bull_dir == bear_dir and bull_dir != "hold":
                if (
                    bull_conf >= self._early_termination_confidence
                    and bear_conf >= self._early_termination_confidence
                ):
                    return True

            return False
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _try_extract_json(text: str) -> dict[str, Any] | None:
        """Attempt to extract a JSON object from text."""
        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = cleaned.strip().rstrip("`")

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    return None
            return None
