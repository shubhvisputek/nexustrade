"""Tests for TradingAgents debate adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from nexustrade.agents.adapters.trading_agents import (
    TradingAgentsDebateAdapter,
    _parse_debate_signal,
)
from nexustrade.core.models import (
    MarketContext,
    Order,
    PortfolioState,
    SignalDirection,
)


# --- Fixtures ---


def _make_context(symbol: str = "AAPL", price: float = 150.0) -> MarketContext:
    portfolio = PortfolioState(
        cash=100_000.0,
        positions=[],
        total_value=100_000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        open_orders=[],
    )
    return MarketContext(
        symbol=symbol,
        current_price=price,
        ohlcv={},
        technicals={},
        news=[],
        fundamentals={},
        sentiment_scores=[],
        factor_signals={},
        recent_signals=[],
        memory=[],
        portfolio=portfolio,
        config={},
    )


def _make_prompt_loader() -> MagicMock:
    loader = MagicMock()
    loader.render_debate_prompt.return_value = "Debate prompt text"
    return loader


# --- TradingAgentsDebateAdapter tests ---


class TestTradingAgentsDebateAdapter:
    def test_creation(self) -> None:
        loader = _make_prompt_loader()
        router = MagicMock()
        adapter = TradingAgentsDebateAdapter(loader, router, rounds=3)

        assert adapter.name == "bull_bear_debate"
        assert adapter.agent_type == "debate"
        assert adapter._rounds == 3

    def test_capabilities(self) -> None:
        adapter = TradingAgentsDebateAdapter(_make_prompt_loader(), MagicMock())
        caps = adapter.get_capabilities()

        assert caps["requires_vision"] is False
        assert caps["llm_channel"] == "deep"
        assert "us_equity" in caps["supported_markets"]

    @pytest.mark.asyncio
    async def test_analyze_produces_signal(self) -> None:
        """Test full debate flow with 2 rounds."""
        bull_response = "Bull case: strong earnings growth"
        bear_response = "Bear case: high valuation"
        synthesis = json.dumps({
            "direction": "buy",
            "confidence": 0.72,
            "reasoning": "Bull arguments outweigh bear concerns.",
        })

        loader = _make_prompt_loader()
        router = MagicMock()
        # 2 rounds x 2 (bull+bear) + 1 synthesis = 5 calls
        router.complete = AsyncMock(
            side_effect=[
                bull_response,
                bear_response,
                bull_response,
                bear_response,
                synthesis,
            ]
        )

        adapter = TradingAgentsDebateAdapter(loader, router, rounds=2)
        signal = await adapter.analyze(_make_context())

        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 0.72
        assert signal.agent_name == "bull_bear_debate"
        assert signal.agent_type == "debate"
        assert signal.metadata.get("debate_rounds") == 2

    @pytest.mark.asyncio
    async def test_debate_runs_configured_rounds(self) -> None:
        """Verify the LLM is called the correct number of times for N rounds."""
        loader = _make_prompt_loader()
        router = MagicMock()
        # 3 rounds x 2 (bull+bear) + 1 synthesis = 7 calls
        router.complete = AsyncMock(
            return_value=json.dumps({
                "direction": "hold",
                "confidence": 0.5,
                "reasoning": "Inconclusive.",
            })
        )

        adapter = TradingAgentsDebateAdapter(loader, router, rounds=3)
        signal = await adapter.analyze(_make_context())

        # 3 rounds * 2 participants + 1 synthesis = 7
        assert router.complete.call_count == 7
        assert signal.metadata.get("debate_rounds") == 3

    @pytest.mark.asyncio
    async def test_debate_single_round(self) -> None:
        loader = _make_prompt_loader()
        router = MagicMock()
        # 1 round x 2 + 1 synthesis = 3 calls
        router.complete = AsyncMock(
            return_value=json.dumps({
                "direction": "sell",
                "confidence": 0.65,
                "reasoning": "Bearish outlook.",
            })
        )

        adapter = TradingAgentsDebateAdapter(loader, router, rounds=1)
        signal = await adapter.analyze(_make_context())

        assert router.complete.call_count == 3
        assert signal.direction == SignalDirection.SELL

    @pytest.mark.asyncio
    async def test_debate_error_returns_hold(self) -> None:
        loader = _make_prompt_loader()
        router = MagicMock()
        router.complete = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        adapter = TradingAgentsDebateAdapter(loader, router)
        signal = await adapter.analyze(_make_context())

        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.1
        assert "Error" in signal.reasoning

    @pytest.mark.asyncio
    async def test_debate_passes_context_to_prompt(self) -> None:
        loader = _make_prompt_loader()
        router = MagicMock()
        router.complete = AsyncMock(
            return_value=json.dumps({
                "direction": "hold",
                "confidence": 0.5,
                "reasoning": "Neutral.",
            })
        )

        adapter = TradingAgentsDebateAdapter(loader, router, rounds=1)
        ctx = _make_context(symbol="TSLA", price=250.0)
        await adapter.analyze(ctx)

        # Check that bull_researcher was called with correct symbol
        first_call = loader.render_debate_prompt.call_args_list[0]
        assert first_call[0][0] == "bull_researcher"
        assert first_call[1]["symbol"] == "TSLA"
        assert first_call[1]["current_price"] == 250.0


# --- _parse_debate_signal tests ---


class TestParseDebateSignal:
    def test_valid_json(self) -> None:
        text = json.dumps({
            "direction": "strong_sell",
            "confidence": 0.9,
            "reasoning": "Overwhelming bear case.",
        })
        signal = _parse_debate_signal(text)
        assert signal.direction == SignalDirection.STRONG_SELL
        assert signal.confidence == 0.9

    def test_malformed_returns_hold(self) -> None:
        signal = _parse_debate_signal("no json here at all")
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.1
