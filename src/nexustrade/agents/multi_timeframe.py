"""Multi-timeframe analysis orchestrator.

Fetches data at multiple timeframes concurrently, runs agents on each,
and merges signals with timeframe-weighted aggregation.
"""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime

from nexustrade.core.interfaces import AgentInterface, DataProviderInterface
from nexustrade.core.models import AgentSignal, MarketContext, OHLCV, SignalDirection

logger = logging.getLogger(__name__)

# Numeric mapping for signal directions (same as aggregator)
_DIRECTION_TO_SCORE: dict[SignalDirection, float] = {
    SignalDirection.STRONG_BUY: 2.0,
    SignalDirection.BUY: 1.0,
    SignalDirection.HOLD: 0.0,
    SignalDirection.SELL: -1.0,
    SignalDirection.STRONG_SELL: -2.0,
}


def _score_to_direction(score: float) -> SignalDirection:
    """Map a numeric score back to the nearest SignalDirection."""
    if score >= 1.5:
        return SignalDirection.STRONG_BUY
    if score >= 0.5:
        return SignalDirection.BUY
    if score > -0.5:
        return SignalDirection.HOLD
    if score > -1.5:
        return SignalDirection.SELL
    return SignalDirection.STRONG_SELL


@dataclass
class TimeframeConfig:
    timeframe: str  # "1h", "4h", "1d"
    weight: float = 1.0  # Weight in signal aggregation


@dataclass
class MultiTimeframeResult:
    symbol: str
    timeframe_signals: dict[str, list[AgentSignal]]  # timeframe -> signals
    merged_signals: list[AgentSignal]
    merged_context: MarketContext


class MultiTimeframeOrchestrator:
    """Fetch data + run agents across multiple timeframes concurrently."""

    def __init__(
        self,
        timeframes: list[TimeframeConfig],
        data_provider: DataProviderInterface | None = None,
    ):
        self._timeframes = timeframes
        self._data_provider = data_provider
        self._weight_map: dict[str, float] = {
            tf.timeframe: tf.weight for tf in timeframes
        }

    async def fetch_multi_timeframe_data(
        self,
        symbol: str,
        data_provider: DataProviderInterface,
        start: datetime,
        end: datetime,
    ) -> dict[str, list[OHLCV]]:
        """Fetch OHLCV data for all timeframes concurrently."""
        async def _fetch_one(tf: str) -> tuple[str, list[OHLCV]]:
            bars = await data_provider.get_ohlcv(symbol, tf, start, end)
            return tf, bars

        tasks = [_fetch_one(tf.timeframe) for tf in self._timeframes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        data: dict[str, list[OHLCV]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error("Failed to fetch timeframe data: %s", result)
                continue
            tf, bars = result
            data[tf] = bars

        return data

    async def run_agents_multi_timeframe(
        self,
        symbol: str,
        agents: list[AgentInterface],
        contexts: dict[str, MarketContext],
    ) -> dict[str, list[AgentSignal]]:
        """Run agents on each timeframe context concurrently."""
        async def _run_agents_for_tf(
            tf: str, ctx: MarketContext,
        ) -> tuple[str, list[AgentSignal]]:
            signals: list[AgentSignal] = []
            agent_tasks = [agent.analyze(ctx) for agent in agents]
            results = await asyncio.gather(*agent_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        "Agent %s failed on timeframe %s: %s",
                        agents[i].name, tf, result,
                    )
                    continue
                # Tag the signal with the timeframe in metadata
                result.metadata["timeframe"] = tf
                signals.append(result)
            return tf, signals

        tasks = [
            _run_agents_for_tf(tf, ctx)
            for tf, ctx in contexts.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        tf_signals: dict[str, list[AgentSignal]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error("Timeframe agent run failed: %s", result)
                continue
            tf, signals = result
            tf_signals[tf] = signals

        return tf_signals

    def merge_signals(
        self,
        timeframe_signals: dict[str, list[AgentSignal]],
    ) -> list[AgentSignal]:
        """Merge signals across timeframes with weight-adjusted confidence.

        Each signal's confidence is scaled by:
            signal.confidence * timeframe_weight / sum_of_all_weights

        Returns a list of adjusted AgentSignal copies.
        """
        total_weight = sum(
            self._weight_map.get(tf, 1.0)
            for tf in timeframe_signals
        )
        if total_weight == 0:
            total_weight = 1.0

        merged: list[AgentSignal] = []
        for tf, signals in timeframe_signals.items():
            tf_weight = self._weight_map.get(tf, 1.0)
            for signal in signals:
                adjusted = deepcopy(signal)
                adjusted.confidence = min(
                    1.0, signal.confidence * tf_weight / total_weight
                )
                adjusted.metadata["original_confidence"] = signal.confidence
                adjusted.metadata["timeframe_weight"] = tf_weight
                adjusted.metadata["timeframe"] = tf
                merged.append(adjusted)

        return merged

    async def analyze(
        self,
        symbol: str,
        agents: list[AgentInterface],
        data_provider: DataProviderInterface,
        start: datetime,
        end: datetime,
        base_context: MarketContext,
    ) -> MultiTimeframeResult:
        """Full multi-timeframe analysis pipeline.

        1. Fetch OHLCV for all timeframes concurrently.
        2. Build per-timeframe contexts from the base context.
        3. Run agents on each timeframe concurrently.
        4. Merge signals with timeframe weights.
        """
        provider = data_provider or self._data_provider
        if provider is None:
            raise ValueError("No data provider supplied")

        # Step 1: fetch data
        tf_data = await self.fetch_multi_timeframe_data(
            symbol, provider, start, end,
        )

        # Step 2: build per-timeframe contexts
        contexts: dict[str, MarketContext] = {}
        for tf, bars in tf_data.items():
            ctx = deepcopy(base_context)
            ctx.ohlcv[tf] = bars
            contexts[tf] = ctx

        # Step 3: run agents
        tf_signals = await self.run_agents_multi_timeframe(
            symbol, agents, contexts,
        )

        # Step 4: merge
        merged = self.merge_signals(tf_signals)

        # Build a merged context that includes all timeframe data
        merged_context = deepcopy(base_context)
        for tf, bars in tf_data.items():
            merged_context.ohlcv[tf] = bars

        return MultiTimeframeResult(
            symbol=symbol,
            timeframe_signals=tf_signals,
            merged_signals=merged,
            merged_context=merged_context,
        )
