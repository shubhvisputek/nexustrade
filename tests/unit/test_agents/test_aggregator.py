"""Tests for SignalAggregator."""

import pytest
from datetime import datetime, timezone

from nexustrade.agents.aggregator import SignalAggregator
from nexustrade.core.models import AgentSignal, SignalDirection


def _make_signal(
    direction: SignalDirection,
    confidence: float = 0.8,
    agent_name: str = "test_agent",
) -> AgentSignal:
    return AgentSignal(
        direction=direction,
        confidence=confidence,
        reasoning="test reasoning",
        agent_name=agent_name,
        agent_type="persona",
        timestamp=datetime.now(timezone.utc),
    )


class TestWeightedConfidence:
    def test_three_buy_signals(self):
        agg = SignalAggregator(mode="weighted_confidence")
        signals = [
            _make_signal(SignalDirection.BUY, 0.9, "agent_a"),
            _make_signal(SignalDirection.BUY, 0.8, "agent_b"),
            _make_signal(SignalDirection.BUY, 0.7, "agent_c"),
        ]
        result = agg.aggregate(signals, "AAPL")
        assert result.direction == SignalDirection.BUY
        assert result.symbol == "AAPL"
        assert result.aggregation_mode == "weighted_confidence"
        assert len(result.contributing_signals) == 3

    def test_mixed_signals_weighted(self):
        agg = SignalAggregator(mode="weighted_confidence")
        signals = [
            _make_signal(SignalDirection.STRONG_BUY, 0.9, "bull"),
            _make_signal(SignalDirection.SELL, 0.6, "bear"),
            _make_signal(SignalDirection.HOLD, 0.7, "neutral"),
        ]
        result = agg.aggregate(signals, "TSLA")
        # strong_buy(2)*0.9 + sell(-1)*0.6 + hold(0)*0.7 = 1.8 - 0.6 = 1.2
        # total_weight = 2.2, avg_score = 1.2/2.2 ≈ 0.545 → BUY
        assert result.direction == SignalDirection.BUY

    def test_sell_dominant_weighted(self):
        agg = SignalAggregator(mode="weighted_confidence")
        signals = [
            _make_signal(SignalDirection.SELL, 0.9, "bear1"),
            _make_signal(SignalDirection.STRONG_SELL, 0.85, "bear2"),
            _make_signal(SignalDirection.BUY, 0.6, "bull"),
        ]
        result = agg.aggregate(signals, "XYZ")
        # sell(-1)*0.9 + strong_sell(-2)*0.85 + buy(1)*0.6
        # = -0.9 - 1.7 + 0.6 = -2.0 / 2.35 ≈ -0.851 → SELL
        assert result.direction == SignalDirection.SELL


class TestMajority:
    def test_two_buy_one_sell(self):
        agg = SignalAggregator(mode="majority")
        signals = [
            _make_signal(SignalDirection.BUY, 0.8, "a"),
            _make_signal(SignalDirection.BUY, 0.7, "b"),
            _make_signal(SignalDirection.SELL, 0.9, "c"),
        ]
        result = agg.aggregate(signals, "AAPL")
        assert result.direction == SignalDirection.BUY
        assert result.confidence == pytest.approx(2 / 3)

    def test_all_same_direction(self):
        agg = SignalAggregator(mode="majority")
        signals = [
            _make_signal(SignalDirection.SELL, 0.8, "a"),
            _make_signal(SignalDirection.SELL, 0.7, "b"),
        ]
        result = agg.aggregate(signals, "AAPL")
        assert result.direction == SignalDirection.SELL
        assert result.confidence == 1.0


class TestUnanimous:
    def test_all_buy(self):
        agg = SignalAggregator(mode="unanimous")
        signals = [
            _make_signal(SignalDirection.BUY, 0.9, "a"),
            _make_signal(SignalDirection.BUY, 0.7, "b"),
            _make_signal(SignalDirection.STRONG_BUY, 0.8, "c"),
        ]
        result = agg.aggregate(signals, "AAPL")
        # All buy-side, should agree
        assert result.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
        assert result.confidence == pytest.approx(0.7)  # min confidence

    def test_mixed_returns_hold(self):
        agg = SignalAggregator(mode="unanimous")
        signals = [
            _make_signal(SignalDirection.BUY, 0.9, "bull"),
            _make_signal(SignalDirection.SELL, 0.8, "bear"),
        ]
        result = agg.aggregate(signals, "AAPL")
        assert result.direction == SignalDirection.HOLD
        assert result.confidence == 0.0

    def test_all_sell_side(self):
        agg = SignalAggregator(mode="unanimous")
        signals = [
            _make_signal(SignalDirection.SELL, 0.8, "a"),
            _make_signal(SignalDirection.STRONG_SELL, 0.65, "b"),
        ]
        result = agg.aggregate(signals, "XYZ")
        assert result.direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL)
        assert result.confidence == pytest.approx(0.65)


class TestMinConfidenceFiltering:
    def test_filters_low_confidence(self):
        agg = SignalAggregator(mode="majority", min_confidence=0.7)
        signals = [
            _make_signal(SignalDirection.BUY, 0.9, "strong"),
            _make_signal(SignalDirection.SELL, 0.5, "weak_sell"),
            _make_signal(SignalDirection.SELL, 0.4, "weaker_sell"),
        ]
        result = agg.aggregate(signals, "AAPL")
        # Only "strong" passes the 0.7 threshold
        assert result.direction == SignalDirection.BUY
        assert result.confidence == 1.0  # 1/1

    def test_all_filtered_returns_hold(self):
        agg = SignalAggregator(mode="weighted_confidence", min_confidence=0.9)
        signals = [
            _make_signal(SignalDirection.BUY, 0.5, "a"),
            _make_signal(SignalDirection.SELL, 0.3, "b"),
        ]
        result = agg.aggregate(signals, "AAPL")
        assert result.direction == SignalDirection.HOLD
        assert result.confidence == 0.0


class TestPortfolioManager:
    def test_returns_first_signal_direction(self):
        agg = SignalAggregator(mode="portfolio_manager")
        signals = [
            _make_signal(SignalDirection.SELL, 0.9, "first"),
            _make_signal(SignalDirection.BUY, 0.8, "second"),
        ]
        result = agg.aggregate(signals, "AAPL")
        assert result.direction == SignalDirection.SELL
        # Averaged confidence: (0.9 + 0.8) / 2 = 0.85
        assert result.confidence == pytest.approx(0.85)

    def test_single_signal(self):
        agg = SignalAggregator(mode="portfolio_manager")
        signals = [_make_signal(SignalDirection.BUY, 0.75, "only")]
        result = agg.aggregate(signals, "TSLA")
        assert result.direction == SignalDirection.BUY
        assert result.confidence == pytest.approx(0.75)


class TestInvalidMode:
    def test_raises_on_invalid_mode(self):
        with pytest.raises(ValueError, match="Invalid aggregation mode"):
            SignalAggregator(mode="invalid")
