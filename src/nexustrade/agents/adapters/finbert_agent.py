"""FinBERT sentiment analysis agent adapter.

Uses ProsusAI/finbert from HuggingFace for fast sentiment classification.
Aggregates multiple headlines with recency weighting.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nexustrade.core.interfaces import AgentInterface
from nexustrade.core.models import AgentSignal, MarketContext, SignalDirection

logger = logging.getLogger(__name__)


def _try_import_finbert():
    """Try to import transformers for FinBERT. Returns (pipeline, available)."""
    try:
        from transformers import pipeline
        return pipeline, True
    except ImportError:
        return None, False


class FinBERTAdapter(AgentInterface):
    """Fast sentiment analysis using ProsusAI/finbert.

    Classifies financial headlines as positive/negative/neutral,
    then aggregates with recency weighting into a trading signal.
    """

    def __init__(self, model_name: str = "ProsusAI/finbert") -> None:
        self._model_name = model_name
        self._pipeline = None
        self._available = False
        self._initialized = False

    def _initialize(self) -> None:
        """Lazy initialization — load model only when first needed."""
        if self._initialized:
            return
        self._initialized = True

        pipeline_fn, available = _try_import_finbert()
        if not available:
            logger.warning("transformers not installed. FinBERT will use mock sentiment.")
            return

        try:
            self._pipeline = pipeline_fn(
                "sentiment-analysis",
                model=self._model_name,
                truncation=True,
                max_length=512,
            )
            self._available = True
            logger.info("FinBERT model loaded: %s", self._model_name)
        except Exception:
            logger.exception("Failed to load FinBERT model")

    @property
    def name(self) -> str:
        return "finbert"

    @property
    def agent_type(self) -> str:
        return "sentiment"

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "requires_vision": False,
            "requires_gpu": False,
            "llm_channel": None,  # Doesn't use LLM
            "supported_markets": ["us_equity", "india_equity", "crypto", "forex"],
        }

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Analyze news sentiment for the given symbol.

        1. Extract headlines from context.news
        2. Classify each headline with FinBERT
        3. Apply recency weighting (newer = higher weight)
        4. Map aggregated score to SignalDirection
        """
        headlines = [n.headline for n in context.news if n.headline]
        if not headlines:
            return AgentSignal(
                direction=SignalDirection.HOLD,
                confidence=0.3,
                reasoning="No news headlines available for sentiment analysis.",
                agent_name=self.name,
                agent_type=self.agent_type,
            )

        # Classify headlines
        scores = await self._classify_headlines(headlines)

        # Apply recency weighting
        weighted_score = self._aggregate_with_recency(scores, context.news)

        # Map to signal
        direction = self._score_to_direction(weighted_score)
        confidence = min(abs(weighted_score), 1.0)

        return AgentSignal(
            direction=direction,
            confidence=round(confidence, 3),
            reasoning=(
                f"FinBERT analyzed {len(headlines)} headlines. "
                f"Weighted sentiment score: {weighted_score:.3f}. "
                f"Most recent: '{headlines[0][:80]}...'"
            ),
            agent_name=self.name,
            agent_type=self.agent_type,
            metadata={
                "num_headlines": len(headlines),
                "raw_score": weighted_score,
                "individual_scores": scores[:5],  # First 5
            },
        )

    async def _classify_headlines(self, headlines: list[str]) -> list[float]:
        """Classify headlines using FinBERT. Returns scores (-1 to 1)."""
        self._initialize()

        if not self._available or not self._pipeline:
            # Use pre-computed scores from news items or return neutral
            return [0.0] * len(headlines)

        def _run():
            results = self._pipeline(headlines)
            scores = []
            for r in results:
                label = r["label"].lower()
                score = r["score"]
                if label == "negative":
                    scores.append(-score)
                elif label == "positive":
                    scores.append(score)
                else:
                    scores.append(0.0)
            return scores

        return await asyncio.to_thread(_run)

    def _aggregate_with_recency(
        self, scores: list[float], news_items: list[Any]
    ) -> float:
        """Aggregate sentiment scores with recency weighting.

        Newer headlines get higher weight using exponential decay.
        """
        if not scores:
            return 0.0

        n = len(scores)
        weights = []
        for i in range(n):
            # Exponential decay: first item (most recent) gets weight 1.0
            weight = 0.8 ** i
            weights.append(weight)

        total_weight = sum(weights)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        return weighted_sum / total_weight

    def _score_to_direction(self, score: float) -> SignalDirection:
        """Map sentiment score to SignalDirection."""
        if score >= 0.6:
            return SignalDirection.STRONG_BUY
        elif score >= 0.3:
            return SignalDirection.BUY
        elif score <= -0.6:
            return SignalDirection.STRONG_SELL
        elif score <= -0.3:
            return SignalDirection.SELL
        return SignalDirection.HOLD
