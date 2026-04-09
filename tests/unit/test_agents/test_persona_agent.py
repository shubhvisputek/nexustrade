"""Tests for AI Hedge Fund persona agent adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexustrade.agents.adapters.ai_hedge_fund import (
    AIHedgeFundAgentGroup,
    PersonaAgent,
    _parse_signal_response,
)
from nexustrade.core.models import (
    AgentSignal,
    MarketContext,
    Order,
    PortfolioState,
    SignalDirection,
)


# --- Fixtures ---


def _make_context(symbol: str = "AAPL", price: float = 150.0) -> MarketContext:
    """Create a minimal MarketContext for testing."""
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
    loader.render_agent_prompt.return_value = "Analyze AAPL at $150"
    return loader


def _make_llm_router(response_text: str) -> MagicMock:
    router = MagicMock()
    router.complete = AsyncMock(return_value=response_text)
    return router


# --- PersonaAgent tests ---


class TestPersonaAgent:
    def test_creation(self) -> None:
        loader = _make_prompt_loader()
        router = _make_llm_router("")
        agent = PersonaAgent("warren_buffett", loader, router)

        assert agent.name == "warren_buffett"
        assert agent.agent_type == "persona"

    def test_capabilities(self) -> None:
        agent = PersonaAgent("warren_buffett", _make_prompt_loader(), _make_llm_router(""))
        caps = agent.get_capabilities()

        assert caps["requires_vision"] is False
        assert caps["requires_gpu"] is False
        assert caps["llm_channel"] == "fast"
        assert "us_equity" in caps["supported_markets"]
        assert "india_equity" in caps["supported_markets"]

    @pytest.mark.asyncio
    async def test_analyze_valid_json(self) -> None:
        response = json.dumps({
            "direction": "buy",
            "confidence": 0.85,
            "reasoning": "Strong fundamentals and moat.",
        })
        loader = _make_prompt_loader()
        router = _make_llm_router(response)
        agent = PersonaAgent("warren_buffett", loader, router)

        signal = await agent.analyze(_make_context())

        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 0.85
        assert "fundamentals" in signal.reasoning.lower()
        assert signal.agent_name == "warren_buffett"
        assert signal.agent_type == "persona"

    @pytest.mark.asyncio
    async def test_analyze_markdown_json(self) -> None:
        response = '```json\n{"direction": "sell", "confidence": 0.7, "reasoning": "Overvalued"}\n```'
        router = _make_llm_router(response)
        agent = PersonaAgent("michael_burry", _make_prompt_loader(), router)

        signal = await agent.analyze(_make_context())

        assert signal.direction == SignalDirection.SELL
        assert signal.confidence == 0.7

    @pytest.mark.asyncio
    async def test_analyze_malformed_json_returns_hold(self) -> None:
        response = "I think the stock looks good but I can't decide."
        router = _make_llm_router(response)
        agent = PersonaAgent("ray_dalio", _make_prompt_loader(), router)

        signal = await agent.analyze(_make_context())

        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.1
        assert signal.agent_name == "ray_dalio"

    @pytest.mark.asyncio
    async def test_analyze_llm_exception_returns_hold(self) -> None:
        router = MagicMock()
        router.complete = AsyncMock(side_effect=RuntimeError("LLM timeout"))
        agent = PersonaAgent("jim_simons", _make_prompt_loader(), router)

        signal = await agent.analyze(_make_context())

        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.1
        assert "Error" in signal.reasoning

    @pytest.mark.asyncio
    async def test_analyze_dict_response(self) -> None:
        response_dict = {
            "content": json.dumps({
                "direction": "strong_buy",
                "confidence": 0.95,
                "reasoning": "Deep value play.",
            })
        }
        router = MagicMock()
        router.complete = AsyncMock(return_value=response_dict)
        agent = PersonaAgent("ben_graham", _make_prompt_loader(), router)

        signal = await agent.analyze(_make_context())

        assert signal.direction == SignalDirection.STRONG_BUY
        assert signal.confidence == 0.95


# --- _parse_signal_response tests ---


class TestParseSignalResponse:
    def test_valid_json(self) -> None:
        text = '{"direction": "buy", "confidence": 0.8, "reasoning": "Good stock"}'
        signal = _parse_signal_response(text, "test_agent")

        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 0.8
        assert signal.agent_name == "test_agent"

    def test_bullish_direction_maps_to_buy(self) -> None:
        text = '{"direction": "bullish", "confidence": 0.6, "reasoning": "Looks good"}'
        signal = _parse_signal_response(text, "test_agent")
        assert signal.direction == SignalDirection.BUY

    def test_confidence_clamped(self) -> None:
        text = '{"direction": "buy", "confidence": 1.5, "reasoning": "Too confident"}'
        signal = _parse_signal_response(text, "test_agent")
        assert signal.confidence == 1.0

    def test_no_json_returns_hold(self) -> None:
        text = "Just some free text with no JSON at all."
        signal = _parse_signal_response(text, "test_agent")
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.1


# --- AIHedgeFundAgentGroup tests ---


class TestAIHedgeFundAgentGroup:
    def test_agents_list_has_18(self) -> None:
        assert len(AIHedgeFundAgentGroup.AGENTS) == 18

    def test_create_all_agents(self) -> None:
        group = AIHedgeFundAgentGroup(_make_prompt_loader(), _make_llm_router(""))
        agents = group.create_agents()

        assert len(agents) == 18
        assert all(isinstance(a, PersonaAgent) for a in agents)
        names = {a.name for a in agents}
        assert "warren_buffett" in names
        assert "jim_simons" in names

    def test_create_subset(self) -> None:
        group = AIHedgeFundAgentGroup(_make_prompt_loader(), _make_llm_router(""))
        agents = group.create_agents(enabled_names=["warren_buffett", "ray_dalio"])

        assert len(agents) == 2
        assert {a.name for a in agents} == {"warren_buffett", "ray_dalio"}

    def test_create_filters_unknown_names(self) -> None:
        group = AIHedgeFundAgentGroup(_make_prompt_loader(), _make_llm_router(""))
        agents = group.create_agents(enabled_names=["warren_buffett", "not_a_real_agent"])

        assert len(agents) == 1
        assert agents[0].name == "warren_buffett"
