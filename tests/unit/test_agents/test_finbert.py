"""Tests for FinBERT sentiment adapter."""

import pytest
from datetime import datetime, timezone

from nexustrade.agents.adapters.finbert_agent import FinBERTAdapter
from nexustrade.core.models import (
    AgentSignal, MarketContext, NewsItem, SignalDirection,
    PortfolioState, Order, Position,
)


def make_context(news: list[NewsItem] | None = None) -> MarketContext:
    return MarketContext(
        symbol="AAPL",
        current_price=185.0,
        ohlcv={},
        technicals={},
        news=news or [],
        fundamentals={},
        sentiment_scores=[],
        factor_signals={},
        recent_signals=[],
        memory=[],
        portfolio=PortfolioState(
            cash=100000, positions=[], total_value=100000,
            daily_pnl=0, total_pnl=0, open_orders=[],
        ),
        config={},
    )


def make_news(headlines: list[str]) -> list[NewsItem]:
    return [
        NewsItem(
            timestamp=datetime.now(timezone.utc),
            headline=h, source="test", symbols=["AAPL"],
        )
        for h in headlines
    ]


class TestFinBERTAdapter:
    def test_name(self):
        adapter = FinBERTAdapter()
        assert adapter.name == "finbert"
        assert adapter.agent_type == "sentiment"

    def test_capabilities(self):
        adapter = FinBERTAdapter()
        caps = adapter.get_capabilities()
        assert caps["requires_gpu"] is False
        assert caps["llm_channel"] is None

    async def test_no_news_returns_hold(self):
        adapter = FinBERTAdapter()
        context = make_context(news=[])
        signal = await adapter.analyze(context)
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence < 0.5

    async def test_with_news_returns_signal(self):
        adapter = FinBERTAdapter()
        news = make_news([
            "Company beats earnings expectations",
            "Strong revenue growth reported",
        ])
        context = make_context(news=news)
        signal = await adapter.analyze(context)
        assert isinstance(signal, AgentSignal)
        assert signal.agent_name == "finbert"
        assert 0.0 <= signal.confidence <= 1.0

    async def test_metadata_includes_count(self):
        adapter = FinBERTAdapter()
        news = make_news(["Positive earnings report"])
        context = make_context(news=news)
        signal = await adapter.analyze(context)
        assert signal.metadata["num_headlines"] == 1

    def test_score_to_direction(self):
        adapter = FinBERTAdapter()
        assert adapter._score_to_direction(0.8) == SignalDirection.STRONG_BUY
        assert adapter._score_to_direction(0.4) == SignalDirection.BUY
        assert adapter._score_to_direction(0.0) == SignalDirection.HOLD
        assert adapter._score_to_direction(-0.4) == SignalDirection.SELL
        assert adapter._score_to_direction(-0.8) == SignalDirection.STRONG_SELL

    def test_recency_weighting(self):
        adapter = FinBERTAdapter()
        scores = [0.9, 0.1, 0.1]  # First is most recent, strongest
        news = make_news(["a", "b", "c"])
        weighted = adapter._aggregate_with_recency(scores, news)
        # Most recent has highest weight (1.0), second (0.8), third (0.64)
        # Weighted avg: (0.9*1 + 0.1*0.8 + 0.1*0.64) / (1+0.8+0.64) ≈ 0.43
        assert weighted > 0.3  # Recency pulls toward most recent positive
        # Verify ordering: more recent scores should have more impact
        scores_reversed = [0.1, 0.1, 0.9]
        weighted_rev = adapter._aggregate_with_recency(scores_reversed, news)
        assert weighted > weighted_rev  # First-item-high should beat last-item-high
