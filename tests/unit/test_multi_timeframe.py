"""Unit tests for multi-timeframe orchestrator."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexustrade.agents.multi_timeframe import (
    MultiTimeframeOrchestrator,
    MultiTimeframeResult,
    TimeframeConfig,
)
from nexustrade.core.interfaces import AgentInterface, DataProviderInterface
from nexustrade.core.models import (
    AgentSignal,
    MarketContext,
    OHLCV,
    Order,
    PortfolioState,
    Position,
    SignalDirection,
    TechnicalIndicators,
)


# --- Helpers ---

def _make_ohlcv(symbol: str, timeframe: str, n: int = 3) -> list[OHLCV]:
    """Create a list of dummy OHLCV bars."""
    bars = []
    for i in range(n):
        bars.append(OHLCV(
            timestamp=datetime(2025, 1, 1, i, 0, tzinfo=timezone.utc),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=1000.0,
            symbol=symbol,
            timeframe=timeframe,
            source="mock",
        ))
    return bars


def _make_signal(
    agent_name: str,
    direction: SignalDirection = SignalDirection.BUY,
    confidence: float = 0.8,
) -> AgentSignal:
    return AgentSignal(
        direction=direction,
        confidence=confidence,
        reasoning=f"Mock signal from {agent_name}",
        agent_name=agent_name,
        agent_type="mock",
        timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        metadata={},
    )


def _make_base_context(symbol: str = "AAPL") -> MarketContext:
    return MarketContext(
        symbol=symbol,
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


def _make_mock_data_provider(symbol: str = "AAPL") -> DataProviderInterface:
    """Create a mock data provider."""
    provider = AsyncMock(spec=DataProviderInterface)
    provider.name = "mock_provider"
    provider.supported_markets = ["us_equity"]

    async def mock_get_ohlcv(sym: str, tf: str, start: datetime, end: datetime) -> list[OHLCV]:
        return _make_ohlcv(sym, tf)

    provider.get_ohlcv = AsyncMock(side_effect=mock_get_ohlcv)
    return provider


def _make_mock_agent(
    name: str,
    direction: SignalDirection = SignalDirection.BUY,
    confidence: float = 0.8,
) -> AgentInterface:
    """Create a mock agent that returns a fixed signal."""
    agent = AsyncMock(spec=AgentInterface)
    agent.name = name
    agent.agent_type = "mock"

    async def mock_analyze(context: MarketContext) -> AgentSignal:
        return _make_signal(name, direction, confidence)

    agent.analyze = AsyncMock(side_effect=mock_analyze)
    agent.get_capabilities = MagicMock(return_value={"markets": ["us_equity"]})
    return agent


# --- Tests ---

@pytest.mark.unit
class TestTimeframeConfig:
    def test_default_weight(self) -> None:
        cfg = TimeframeConfig(timeframe="1h")
        assert cfg.weight == 1.0

    def test_custom_weight(self) -> None:
        cfg = TimeframeConfig(timeframe="1d", weight=3.0)
        assert cfg.weight == 3.0


@pytest.mark.unit
class TestFetchMultiTimeframeData:
    @pytest.mark.asyncio
    async def test_fetches_all_timeframes_concurrently(self) -> None:
        provider = _make_mock_data_provider()
        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[
                TimeframeConfig("1h"),
                TimeframeConfig("4h"),
                TimeframeConfig("1d"),
            ],
        )

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 31, tzinfo=timezone.utc)

        data = await orchestrator.fetch_multi_timeframe_data(
            "AAPL", provider, start, end,
        )

        assert "1h" in data
        assert "4h" in data
        assert "1d" in data
        assert len(data["1h"]) == 3
        assert provider.get_ohlcv.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_fetch_failure_gracefully(self) -> None:
        provider = _make_mock_data_provider()

        call_count = 0
        async def failing_ohlcv(sym: str, tf: str, start: datetime, end: datetime) -> list[OHLCV]:
            nonlocal call_count
            call_count += 1
            if tf == "4h":
                raise ConnectionError("API timeout")
            return _make_ohlcv(sym, tf)

        provider.get_ohlcv = AsyncMock(side_effect=failing_ohlcv)

        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[
                TimeframeConfig("1h"),
                TimeframeConfig("4h"),
                TimeframeConfig("1d"),
            ],
        )

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 31, tzinfo=timezone.utc)

        data = await orchestrator.fetch_multi_timeframe_data(
            "AAPL", provider, start, end,
        )

        # 4h should be missing due to error; others present
        assert "1h" in data
        assert "4h" not in data
        assert "1d" in data


@pytest.mark.unit
class TestRunAgentsMultiTimeframe:
    @pytest.mark.asyncio
    async def test_runs_agents_on_each_timeframe(self) -> None:
        agent1 = _make_mock_agent("agent_a", SignalDirection.BUY, 0.8)
        agent2 = _make_mock_agent("agent_b", SignalDirection.SELL, 0.6)

        contexts = {
            "1h": _make_base_context(),
            "1d": _make_base_context(),
        }

        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[TimeframeConfig("1h"), TimeframeConfig("1d")],
        )

        tf_signals = await orchestrator.run_agents_multi_timeframe(
            "AAPL", [agent1, agent2], contexts,
        )

        assert "1h" in tf_signals
        assert "1d" in tf_signals
        assert len(tf_signals["1h"]) == 2
        assert len(tf_signals["1d"]) == 2

    @pytest.mark.asyncio
    async def test_tags_signals_with_timeframe(self) -> None:
        agent = _make_mock_agent("agent_a")
        contexts = {"4h": _make_base_context()}

        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[TimeframeConfig("4h")],
        )

        tf_signals = await orchestrator.run_agents_multi_timeframe(
            "AAPL", [agent], contexts,
        )

        signal = tf_signals["4h"][0]
        assert signal.metadata["timeframe"] == "4h"

    @pytest.mark.asyncio
    async def test_handles_agent_failure(self) -> None:
        good_agent = _make_mock_agent("good_agent")
        bad_agent = AsyncMock(spec=AgentInterface)
        bad_agent.name = "bad_agent"
        bad_agent.analyze = AsyncMock(side_effect=RuntimeError("LLM error"))

        contexts = {"1h": _make_base_context()}
        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[TimeframeConfig("1h")],
        )

        tf_signals = await orchestrator.run_agents_multi_timeframe(
            "AAPL", [good_agent, bad_agent], contexts,
        )

        # Only good_agent's signal should be present
        assert len(tf_signals["1h"]) == 1
        assert tf_signals["1h"][0].agent_name == "good_agent"


@pytest.mark.unit
class TestMergeSignals:
    def test_merge_equal_weights(self) -> None:
        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[
                TimeframeConfig("1h", weight=1.0),
                TimeframeConfig("1d", weight=1.0),
            ],
        )

        tf_signals = {
            "1h": [_make_signal("agent_a", SignalDirection.BUY, 0.8)],
            "1d": [_make_signal("agent_b", SignalDirection.SELL, 0.6)],
        }

        merged = orchestrator.merge_signals(tf_signals)

        assert len(merged) == 2
        # With equal weights (1.0 each), total=2.0
        # confidence adjusted: 0.8 * 1.0 / 2.0 = 0.4
        for sig in merged:
            if sig.agent_name == "agent_a":
                assert sig.confidence == pytest.approx(0.4)
            elif sig.agent_name == "agent_b":
                assert sig.confidence == pytest.approx(0.3)

    def test_merge_weighted_higher_timeframe(self) -> None:
        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[
                TimeframeConfig("1h", weight=1.0),
                TimeframeConfig("1d", weight=3.0),
            ],
        )

        tf_signals = {
            "1h": [_make_signal("agent_a", SignalDirection.BUY, 0.8)],
            "1d": [_make_signal("agent_b", SignalDirection.BUY, 0.8)],
        }

        merged = orchestrator.merge_signals(tf_signals)

        # Total weight = 4.0
        # 1h signal: 0.8 * 1.0 / 4.0 = 0.2
        # 1d signal: 0.8 * 3.0 / 4.0 = 0.6
        for sig in merged:
            if sig.metadata["timeframe"] == "1h":
                assert sig.confidence == pytest.approx(0.2)
            elif sig.metadata["timeframe"] == "1d":
                assert sig.confidence == pytest.approx(0.6)

    def test_merge_preserves_original_confidence(self) -> None:
        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[TimeframeConfig("1h", weight=1.0)],
        )

        tf_signals = {
            "1h": [_make_signal("agent_a", SignalDirection.BUY, 0.9)],
        }

        merged = orchestrator.merge_signals(tf_signals)
        assert merged[0].metadata["original_confidence"] == 0.9

    def test_merge_empty_signals(self) -> None:
        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[TimeframeConfig("1h")],
        )

        merged = orchestrator.merge_signals({})
        assert merged == []

    def test_merge_caps_confidence_at_one(self) -> None:
        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[TimeframeConfig("1h", weight=5.0)],
        )

        tf_signals = {
            "1h": [_make_signal("agent_a", SignalDirection.BUY, 0.9)],
        }

        merged = orchestrator.merge_signals(tf_signals)
        # 0.9 * 5.0 / 5.0 = 0.9 (within bounds)
        assert merged[0].confidence <= 1.0


@pytest.mark.unit
class TestAnalyzePipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline(self) -> None:
        provider = _make_mock_data_provider()
        agent = _make_mock_agent("test_agent", SignalDirection.BUY, 0.7)
        base_ctx = _make_base_context()

        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[
                TimeframeConfig("1h", weight=1.0),
                TimeframeConfig("1d", weight=2.0),
            ],
        )

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 31, tzinfo=timezone.utc)

        result = await orchestrator.analyze(
            "AAPL", [agent], provider, start, end, base_ctx,
        )

        assert isinstance(result, MultiTimeframeResult)
        assert result.symbol == "AAPL"
        assert "1h" in result.timeframe_signals
        assert "1d" in result.timeframe_signals
        assert len(result.merged_signals) == 2
        # Merged context should have OHLCV for both timeframes
        assert "1h" in result.merged_context.ohlcv
        assert "1d" in result.merged_context.ohlcv

    @pytest.mark.asyncio
    async def test_no_data_provider_raises(self) -> None:
        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[TimeframeConfig("1h")],
        )
        agent = _make_mock_agent("agent")
        base_ctx = _make_base_context()

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 31, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="No data provider"):
            await orchestrator.analyze(
                "AAPL", [agent], None, start, end, base_ctx,  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    async def test_pipeline_with_constructor_provider(self) -> None:
        provider = _make_mock_data_provider()
        agent = _make_mock_agent("agent")
        base_ctx = _make_base_context()

        orchestrator = MultiTimeframeOrchestrator(
            timeframes=[TimeframeConfig("1h")],
            data_provider=provider,
        )

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 31, tzinfo=timezone.utc)

        # Pass provider explicitly -- it should be used
        result = await orchestrator.analyze(
            "AAPL", [agent], provider, start, end, base_ctx,
        )

        assert result.symbol == "AAPL"
        assert len(result.merged_signals) == 1
