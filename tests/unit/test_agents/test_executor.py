"""Tests for AgentExecutor."""

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from nexustrade.agents.executor import AgentExecutor
from nexustrade.core.interfaces import AgentInterface
from nexustrade.core.models import (
    AgentSignal,
    MarketContext,
    Order,
    PortfolioState,
    Position,
    SignalDirection,
)


def _make_context() -> MarketContext:
    return MarketContext(
        symbol="AAPL",
        current_price=150.0,
        ohlcv={},
        technicals={},
        news=[],
        fundamentals={},
        sentiment_scores=[],
        factor_signals={},
        recent_signals=[],
        memory=[],
        portfolio=PortfolioState(
            cash=100000.0,
            positions=[],
            total_value=100000.0,
            daily_pnl=0.0,
            total_pnl=0.0,
            open_orders=[],
        ),
        config={},
    )


def _make_signal(
    direction: SignalDirection = SignalDirection.BUY,
    agent_name: str = "mock_agent",
    confidence: float = 0.8,
) -> AgentSignal:
    return AgentSignal(
        direction=direction,
        confidence=confidence,
        reasoning="mock reasoning",
        agent_name=agent_name,
        agent_type="persona",
        timestamp=datetime.now(timezone.utc),
    )


class MockAgent(AgentInterface):
    """A mock agent that returns a predefined signal."""

    def __init__(
        self,
        name: str,
        signal: AgentSignal,
        depends_on: list[str] | None = None,
    ) -> None:
        self._name = name
        self._signal = signal
        self._depends_on = depends_on or []
        self.called = False
        self.recent_signals_at_call: list[AgentSignal] | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def agent_type(self) -> str:
        return "persona"

    async def analyze(self, context: MarketContext) -> AgentSignal:
        self.called = True
        # Snapshot the recent_signals list at call time (context is mutated in-place)
        self.recent_signals_at_call = list(context.recent_signals)
        return self._signal

    def get_capabilities(self) -> dict[str, Any]:
        caps: dict[str, Any] = {"markets": ["us_equity"]}
        if self._depends_on:
            caps["depends_on"] = self._depends_on
        return caps


class FailingAgent(AgentInterface):
    """An agent that always raises an error."""

    def __init__(self, name: str = "failing_agent") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def analyze(self, context: MarketContext) -> AgentSignal:
        raise RuntimeError("Agent crashed!")

    def get_capabilities(self) -> dict[str, Any]:
        return {"markets": ["us_equity"]}


class TestParallel:
    @pytest.mark.asyncio
    async def test_three_agents_all_results(self):
        executor = AgentExecutor(mode="parallel")
        agents = [
            MockAgent("a", _make_signal(SignalDirection.BUY, "a")),
            MockAgent("b", _make_signal(SignalDirection.SELL, "b")),
            MockAgent("c", _make_signal(SignalDirection.HOLD, "c")),
        ]
        context = _make_context()
        results = await executor.execute(agents, context)
        assert len(results) == 3
        assert all(a.called for a in agents)

    @pytest.mark.asyncio
    async def test_empty_agents(self):
        executor = AgentExecutor(mode="parallel")
        results = await executor.execute([], _make_context())
        assert results == []


class TestSequential:
    @pytest.mark.asyncio
    async def test_agents_run_in_order_with_updated_signals(self):
        executor = AgentExecutor(mode="sequential")
        sig_a = _make_signal(SignalDirection.BUY, "a")
        sig_b = _make_signal(SignalDirection.SELL, "b")
        agent_a = MockAgent("a", sig_a)
        agent_b = MockAgent("b", sig_b)

        context = _make_context()
        results = await executor.execute([agent_a, agent_b], context)

        assert len(results) == 2
        # agent_a should have seen empty recent_signals
        assert agent_a.recent_signals_at_call is not None
        assert len(agent_a.recent_signals_at_call) == 0
        # agent_b should have seen agent_a's signal
        assert agent_b.recent_signals_at_call is not None
        assert len(agent_b.recent_signals_at_call) == 1
        assert agent_b.recent_signals_at_call[0].agent_name == "a"


class TestDag:
    @pytest.mark.asyncio
    async def test_dependent_skipped_on_sell(self):
        """agent_b depends on agent_a. agent_a returns SELL -> agent_b skipped."""
        executor = AgentExecutor(mode="dag")
        executor.skip_on_sell = True

        sig_a = _make_signal(SignalDirection.SELL, "a")
        sig_b = _make_signal(SignalDirection.BUY, "b")
        agent_a = MockAgent("a", sig_a)
        agent_b = MockAgent("b", sig_b, depends_on=["a"])

        context = _make_context()
        results = await executor.execute([agent_a, agent_b], context)

        assert len(results) == 1
        assert results[0].agent_name == "a"
        assert agent_a.called
        assert not agent_b.called

    @pytest.mark.asyncio
    async def test_dependent_runs_on_buy(self):
        """agent_b depends on agent_a. agent_a returns BUY -> agent_b runs."""
        executor = AgentExecutor(mode="dag")
        executor.skip_on_sell = True

        sig_a = _make_signal(SignalDirection.BUY, "a")
        sig_b = _make_signal(SignalDirection.HOLD, "b")
        agent_a = MockAgent("a", sig_a)
        agent_b = MockAgent("b", sig_b, depends_on=["a"])

        context = _make_context()
        results = await executor.execute([agent_a, agent_b], context)

        assert len(results) == 2
        assert agent_a.called
        assert agent_b.called

    @pytest.mark.asyncio
    async def test_independent_agents_all_run(self):
        """Agents without dependencies all run."""
        executor = AgentExecutor(mode="dag")
        agents = [
            MockAgent("a", _make_signal(SignalDirection.BUY, "a")),
            MockAgent("b", _make_signal(SignalDirection.SELL, "b")),
            MockAgent("c", _make_signal(SignalDirection.HOLD, "c")),
        ]
        context = _make_context()
        results = await executor.execute(agents, context)
        assert len(results) == 3


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_one_fails_others_succeed(self):
        executor = AgentExecutor(mode="parallel")
        agents = [
            MockAgent("good_a", _make_signal(SignalDirection.BUY, "good_a")),
            FailingAgent("bad"),
            MockAgent("good_b", _make_signal(SignalDirection.SELL, "good_b")),
        ]
        context = _make_context()
        results = await executor.execute(agents, context)
        assert len(results) == 2
        names = {r.agent_name for r in results}
        assert names == {"good_a", "good_b"}

    @pytest.mark.asyncio
    async def test_all_fail_returns_empty(self):
        executor = AgentExecutor(mode="parallel")
        agents = [FailingAgent("fail1"), FailingAgent("fail2")]
        results = await executor.execute(agents, _make_context())
        assert results == []


class TestInvalidMode:
    def test_raises_on_invalid_mode(self):
        with pytest.raises(ValueError, match="Invalid execution mode"):
            AgentExecutor(mode="invalid")
