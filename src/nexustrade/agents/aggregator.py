"""Signal aggregator for combining multiple agent signals into a composite signal."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from nexustrade.core.models import AgentSignal, CompositeSignal, SignalDirection

logger = logging.getLogger(__name__)

# Numeric mapping for signal directions
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


class SignalAggregator:
    """Aggregates multiple AgentSignal instances into a single CompositeSignal.

    Supports 4 aggregation modes:
    - weighted_confidence: Weight each signal by its confidence.
    - majority: Simple majority vote.
    - unanimous: All signals must agree (buy-side or sell-side).
    - portfolio_manager: Placeholder that returns the first signal's direction.
    """

    VALID_MODES = ("weighted_confidence", "majority", "unanimous", "portfolio_manager")

    def __init__(
        self,
        mode: str = "weighted_confidence",
        min_confidence: float = 0.6,
    ) -> None:
        if mode not in self.VALID_MODES:
            raise ValueError(
                f"Invalid aggregation mode '{mode}'. "
                f"Must be one of {self.VALID_MODES}"
            )
        self.mode = mode
        self.min_confidence = min_confidence

    def aggregate(self, signals: list[AgentSignal], symbol: str) -> CompositeSignal:
        """Aggregate a list of agent signals into a composite signal."""
        # Filter signals below min_confidence
        filtered = [s for s in signals if s.confidence >= self.min_confidence]

        if not filtered:
            return CompositeSignal(
                symbol=symbol,
                direction=SignalDirection.HOLD,
                confidence=0.0,
                contributing_signals=signals,
                aggregation_mode=self.mode,
                reasoning="No signals met the minimum confidence threshold.",
                timestamp=datetime.now(UTC),
            )

        method = getattr(self, f"_aggregate_{self.mode}")
        return method(filtered, symbol)

    def _aggregate_weighted_confidence(
        self, signals: list[AgentSignal], symbol: str
    ) -> CompositeSignal:
        """Weight each signal by its confidence, compute weighted average score."""
        total_weight = sum(s.confidence for s in signals)
        weighted_score = sum(
            _DIRECTION_TO_SCORE[s.direction] * s.confidence for s in signals
        )
        avg_score = weighted_score / total_weight if total_weight > 0 else 0.0
        direction = _score_to_direction(avg_score)
        avg_confidence = total_weight / len(signals)

        reasons = [
            f"{s.agent_name}: {s.direction.value} ({s.confidence:.2f})"
            for s in signals
        ]
        reasoning = (
            f"Weighted confidence aggregation (score={avg_score:.2f}): "
            + "; ".join(reasons)
        )

        return CompositeSignal(
            symbol=symbol,
            direction=direction,
            confidence=min(avg_confidence, 1.0),
            contributing_signals=signals,
            aggregation_mode=self.mode,
            reasoning=reasoning,
            timestamp=datetime.now(UTC),
        )

    def _aggregate_majority(
        self, signals: list[AgentSignal], symbol: str
    ) -> CompositeSignal:
        """Simple majority vote. Direction with most signals wins."""
        from collections import Counter

        vote_counts: Counter[SignalDirection] = Counter(
            s.direction for s in signals
        )
        winner, winner_count = vote_counts.most_common(1)[0]
        confidence = winner_count / len(signals)

        reasons = [
            f"{s.agent_name}: {s.direction.value}" for s in signals
        ]
        reasoning = (
            f"Majority vote: {winner.value} won with "
            f"{winner_count}/{len(signals)} votes. " + "; ".join(reasons)
        )

        return CompositeSignal(
            symbol=symbol,
            direction=winner,
            confidence=confidence,
            contributing_signals=signals,
            aggregation_mode=self.mode,
            reasoning=reasoning,
            timestamp=datetime.now(UTC),
        )

    def _aggregate_unanimous(
        self, signals: list[AgentSignal], symbol: str
    ) -> CompositeSignal:
        """All signals must agree on the same side (buy or sell)."""
        buy_side = {SignalDirection.BUY, SignalDirection.STRONG_BUY}
        sell_side = {SignalDirection.SELL, SignalDirection.STRONG_SELL}

        directions = {s.direction for s in signals}

        all_buy = directions.issubset(buy_side)
        all_sell = directions.issubset(sell_side)
        all_hold = directions == {SignalDirection.HOLD}

        if all_buy:
            # Use the most common buy-side direction
            from collections import Counter
            counts: Counter[SignalDirection] = Counter(
                s.direction for s in signals
            )
            direction = counts.most_common(1)[0][0]
            confidence = min(s.confidence for s in signals)
            reasoning = f"Unanimous buy-side agreement: {direction.value}"
        elif all_sell:
            from collections import Counter
            counts = Counter(s.direction for s in signals)
            direction = counts.most_common(1)[0][0]
            confidence = min(s.confidence for s in signals)
            reasoning = f"Unanimous sell-side agreement: {direction.value}"
        elif all_hold:
            direction = SignalDirection.HOLD
            confidence = min(s.confidence for s in signals)
            reasoning = "Unanimous hold agreement."
        else:
            direction = SignalDirection.HOLD
            confidence = 0.0
            reasoning = (
                "No unanimous agreement. Signals: "
                + ", ".join(f"{s.agent_name}={s.direction.value}" for s in signals)
            )

        return CompositeSignal(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            contributing_signals=signals,
            aggregation_mode=self.mode,
            reasoning=reasoning,
            timestamp=datetime.now(UTC),
        )

    def _aggregate_portfolio_manager(
        self, signals: list[AgentSignal], symbol: str
    ) -> CompositeSignal:
        """Placeholder: returns first signal's direction with averaged confidence.

        Will be replaced with LLM-based portfolio manager in Phase 3.3.
        """
        direction = signals[0].direction
        avg_confidence = sum(s.confidence for s in signals) / len(signals)

        reasoning = (
            "Portfolio manager placeholder: using first signal's direction "
            f"({signals[0].agent_name}) with averaged confidence."
        )

        return CompositeSignal(
            symbol=symbol,
            direction=direction,
            confidence=min(avg_confidence, 1.0),
            contributing_signals=signals,
            aggregation_mode=self.mode,
            reasoning=reasoning,
            timestamp=datetime.now(UTC),
        )
