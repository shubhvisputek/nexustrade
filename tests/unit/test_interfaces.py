"""Tests for nexustrade.core.interfaces ABCs.

Verifies that:
- Concrete classes implementing all required methods can be instantiated.
- Optional methods return sensible defaults.
- Missing a required method raises TypeError on instantiation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from nexustrade.core.interfaces import (
    AgentInterface,
    BrokerBackendInterface,
    DataProviderInterface,
    NotificationAdapter,
    RiskModelInterface,
    StrategyInterface,
)
from nexustrade.core.models import (
    OHLCV,
    AgentSignal,
    CompositeSignal,
    Fill,
    MarketContext,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioState,
    Position,
    Quote,
    RiskAssessment,
    SignalDirection,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _make_quote(symbol: str = "AAPL") -> Quote:
    return Quote(
        symbol=symbol, bid=150.0, ask=150.1, last=150.05,
        volume=1_000_000, timestamp=_NOW, source="test",
    )


def _make_ohlcv(symbol: str = "AAPL") -> OHLCV:
    return OHLCV(
        timestamp=_NOW, open=149.0, high=151.0, low=148.5,
        close=150.0, volume=500_000, symbol=symbol,
        timeframe="1d", source="test",
    )


def _make_fill() -> Fill:
    return Fill(
        order_id="ord-1", symbol="AAPL", side=OrderSide.BUY,
        filled_qty=10, avg_price=150.0, timestamp=_NOW,
        broker="test", status=OrderStatus.FILLED,
    )


def _make_position() -> Position:
    return Position(
        symbol="AAPL", quantity=10, avg_entry_price=150.0,
        current_price=155.0, unrealized_pnl=50.0,
    )


def _make_portfolio() -> PortfolioState:
    return PortfolioState(
        cash=100_000, positions=[], total_value=100_000,
        daily_pnl=0, total_pnl=0, open_orders=[],
    )


def _make_market_context() -> MarketContext:
    return MarketContext(
        symbol="AAPL", current_price=150.0, ohlcv={}, technicals={},
        news=[], fundamentals={}, sentiment_scores=[], factor_signals={},
        recent_signals=[], memory=[], portfolio=_make_portfolio(),
        config={},
    )


def _make_agent_signal() -> AgentSignal:
    return AgentSignal(
        direction=SignalDirection.BUY, confidence=0.8,
        reasoning="test", agent_name="test", agent_type="generic",
    )


def _make_composite_signal() -> CompositeSignal:
    return CompositeSignal(
        symbol="AAPL", direction=SignalDirection.BUY,
        confidence=0.8, contributing_signals=[], aggregation_mode="mean",
        reasoning="test", timestamp=_NOW,
    )


# ---------------------------------------------------------------------------
# Concrete stubs
# ---------------------------------------------------------------------------

class StubDataProvider(DataProviderInterface):
    @property
    def name(self) -> str:
        return "stub"

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity"]

    async def get_ohlcv(self, symbol, timeframe, start, end):
        return [_make_ohlcv(symbol)]

    async def get_quote(self, symbol):
        return _make_quote(symbol)


class StubBroker(BrokerBackendInterface):
    @property
    def name(self) -> str:
        return "stub_broker"

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity"]

    @property
    def is_paper(self) -> bool:
        return True

    async def place_order(self, order):
        return _make_fill()

    async def cancel_order(self, order_id):
        return True

    async def get_positions(self):
        return [_make_position()]

    async def get_account(self):
        return {"cash": 100_000, "equity": 100_000}


class StubAgent(AgentInterface):
    @property
    def name(self) -> str:
        return "stub_agent"

    async def analyze(self, context):
        return _make_agent_signal()

    def get_capabilities(self):
        return {"markets": ["us_equity"]}


class StubNotification(NotificationAdapter):
    @property
    def name(self) -> str:
        return "stub_notifier"

    async def send(self, title, message, level="info"):
        return True


class StubRiskModel(RiskModelInterface):
    @property
    def name(self) -> str:
        return "stub_risk"

    async def calculate_position_size(self, portfolio, signal, market_data, config):
        return RiskAssessment(
            symbol="AAPL", approved=True, position_size=10,
            stop_loss_price=145.0, take_profit_price=160.0,
            risk_reward_ratio=2.0, max_loss_amount=50.0,
            sizing_model="fixed",
        )


class StubStrategy(StrategyInterface):
    @property
    def name(self) -> str:
        return "stub_strategy"

    async def evaluate_entry(self, context, signals):
        return True

    async def evaluate_exit(self, context, signals, position):
        return False


# ---------------------------------------------------------------------------
# Tests — DataProviderInterface
# ---------------------------------------------------------------------------

class TestDataProviderInterface:
    def test_instantiation_with_required_methods(self):
        provider = StubDataProvider()
        assert provider.name == "stub"
        assert provider.supported_markets == ["us_equity"]

    @pytest.mark.asyncio
    async def test_get_ohlcv(self):
        provider = StubDataProvider()
        bars = await provider.get_ohlcv("AAPL", "1d", _NOW, _NOW)
        assert len(bars) == 1
        assert bars[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_quote(self):
        provider = StubDataProvider()
        quote = await provider.get_quote("AAPL")
        assert quote.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_optional_get_news_returns_empty(self):
        provider = StubDataProvider()
        news = await provider.get_news("AAPL")
        assert news == []

    @pytest.mark.asyncio
    async def test_optional_get_fundamentals_returns_empty(self):
        provider = StubDataProvider()
        data = await provider.get_fundamentals("AAPL")
        assert data == {}

    @pytest.mark.asyncio
    async def test_optional_get_technicals_returns_none(self):
        provider = StubDataProvider()
        result = await provider.get_technicals("AAPL", "1d")
        assert result is None

    @pytest.mark.asyncio
    async def test_optional_get_chart_image_returns_none(self):
        provider = StubDataProvider()
        result = await provider.get_chart_image("AAPL", "1d")
        assert result is None

    @pytest.mark.asyncio
    async def test_optional_screen_returns_empty(self):
        provider = StubDataProvider()
        result = await provider.screen()
        assert result == []

    @pytest.mark.asyncio
    async def test_optional_stream_raises(self):
        provider = StubDataProvider()
        with pytest.raises(NotImplementedError, match="stub"):
            async for _ in provider.stream(["AAPL"]):
                pass  # pragma: no cover

    @pytest.mark.asyncio
    async def test_optional_health_check_returns_true(self):
        provider = StubDataProvider()
        assert await provider.health_check() is True

    def test_missing_required_method_raises(self):
        """Omitting get_ohlcv should prevent instantiation."""

        class BadProvider(DataProviderInterface):
            @property
            def name(self):
                return "bad"

            @property
            def supported_markets(self):
                return []

            # get_ohlcv intentionally missing

            async def get_quote(self, symbol):
                return _make_quote(symbol)

        with pytest.raises(TypeError):
            BadProvider()


# ---------------------------------------------------------------------------
# Tests — BrokerBackendInterface
# ---------------------------------------------------------------------------

class TestBrokerBackendInterface:
    def test_instantiation(self):
        broker = StubBroker()
        assert broker.name == "stub_broker"
        assert broker.is_paper is True

    @pytest.mark.asyncio
    async def test_place_order(self):
        broker = StubBroker()
        order = Order(
            symbol="AAPL", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=10,
        )
        fill = await broker.place_order(order)
        assert fill.symbol == "AAPL"
        assert fill.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_get_positions(self):
        broker = StubBroker()
        positions = await broker.get_positions()
        assert len(positions) == 1

    @pytest.mark.asyncio
    async def test_get_account(self):
        broker = StubBroker()
        acct = await broker.get_account()
        assert "cash" in acct

    @pytest.mark.asyncio
    async def test_optional_modify_order_raises(self):
        broker = StubBroker()
        with pytest.raises(NotImplementedError):
            await broker.modify_order("ord-1", {})

    @pytest.mark.asyncio
    async def test_optional_get_order_history_empty(self):
        broker = StubBroker()
        history = await broker.get_order_history()
        assert history == []

    @pytest.mark.asyncio
    async def test_optional_health_check_true(self):
        broker = StubBroker()
        assert await broker.health_check() is True


# ---------------------------------------------------------------------------
# Tests — AgentInterface
# ---------------------------------------------------------------------------

class TestAgentInterface:
    def test_instantiation(self):
        agent = StubAgent()
        assert agent.name == "stub_agent"

    def test_default_agent_type(self):
        agent = StubAgent()
        assert agent.agent_type == "generic"

    @pytest.mark.asyncio
    async def test_analyze(self):
        agent = StubAgent()
        ctx = _make_market_context()
        signal = await agent.analyze(ctx)
        assert signal.direction == SignalDirection.BUY
        assert 0 <= signal.confidence <= 1

    def test_get_capabilities(self):
        agent = StubAgent()
        caps = agent.get_capabilities()
        assert "markets" in caps

    def test_missing_analyze_raises(self):
        class BadAgent(AgentInterface):
            @property
            def name(self):
                return "bad"

            # analyze intentionally missing

            def get_capabilities(self):
                return {}

        with pytest.raises(TypeError):
            BadAgent()


# ---------------------------------------------------------------------------
# Tests — NotificationAdapter
# ---------------------------------------------------------------------------

class TestNotificationAdapter:
    @pytest.mark.asyncio
    async def test_send(self):
        n = StubNotification()
        assert await n.send("title", "msg") is True

    @pytest.mark.asyncio
    async def test_send_trade_alert(self):
        n = StubNotification()
        fill = _make_fill()
        assert await n.send_trade_alert(fill) is True

    @pytest.mark.asyncio
    async def test_send_circuit_breaker(self):
        n = StubNotification()
        assert await n.send_circuit_breaker("too many losses") is True

    @pytest.mark.asyncio
    async def test_send_circuit_breaker_with_resume(self):
        n = StubNotification()
        result = await n.send_circuit_breaker("losses", resume_at=_NOW)
        assert result is True


# ---------------------------------------------------------------------------
# Tests — RiskModelInterface
# ---------------------------------------------------------------------------

class TestRiskModelInterface:
    def test_instantiation(self):
        rm = StubRiskModel()
        assert rm.name == "stub_risk"

    @pytest.mark.asyncio
    async def test_calculate_position_size(self):
        rm = StubRiskModel()
        assessment = await rm.calculate_position_size(
            _make_portfolio(), _make_composite_signal(), {}, {},
        )
        assert assessment.approved is True
        assert assessment.position_size == 10


# ---------------------------------------------------------------------------
# Tests — StrategyInterface
# ---------------------------------------------------------------------------

class TestStrategyInterface:
    def test_instantiation(self):
        s = StubStrategy()
        assert s.name == "stub_strategy"

    @pytest.mark.asyncio
    async def test_evaluate_entry(self):
        s = StubStrategy()
        result = await s.evaluate_entry(_make_market_context(), [])
        assert result is True

    @pytest.mark.asyncio
    async def test_evaluate_exit(self):
        s = StubStrategy()
        result = await s.evaluate_exit(
            _make_market_context(), [], _make_position(),
        )
        assert result is False
