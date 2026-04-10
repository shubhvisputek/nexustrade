"""Tests for core data models."""

import pytest
from datetime import datetime, timezone, timedelta

from nexustrade.core.models import (
    OHLCV, Quote, NewsItem, TechnicalIndicators,
    AgentSignal, MarketContext, CompositeSignal,
    Order, Fill, Position, PortfolioState, RiskAssessment, Event,
    SignalDirection, OrderSide, OrderType, OrderStatus,
)


UTC_NOW = datetime.now(timezone.utc)


class TestOHLCV:
    def test_create_valid(self):
        bar = OHLCV(
            timestamp=UTC_NOW, open=185.0, high=186.0, low=184.0,
            close=185.5, volume=1_000_000, symbol="AAPL",
            timeframe="1d", source="test",
        )
        assert bar.symbol == "AAPL"
        assert bar.close == 185.5

    def test_non_utc_timestamp_raises(self):
        naive = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(ValueError, match="UTC"):
            OHLCV(
                timestamp=naive, open=185.0, high=186.0, low=184.0,
                close=185.5, volume=1_000_000, symbol="AAPL",
                timeframe="1d", source="test",
            )

    def test_non_utc_timezone_raises(self):
        est = timezone(timedelta(hours=-5))
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=est)
        with pytest.raises(ValueError, match="UTC"):
            OHLCV(
                timestamp=ts, open=185.0, high=186.0, low=184.0,
                close=185.5, volume=1_000_000, symbol="AAPL",
                timeframe="1d", source="test",
            )

    def test_serialization_roundtrip(self):
        bar = OHLCV(
            timestamp=UTC_NOW, open=185.0, high=186.0, low=184.0,
            close=185.5, volume=1_000_000, symbol="AAPL",
            timeframe="1d", source="test", metadata={"extra": "val"},
        )
        d = bar.to_dict()
        assert isinstance(d["timestamp"], str)
        bar2 = OHLCV.from_dict(d)
        assert bar2.symbol == bar.symbol
        assert bar2.close == bar.close
        assert bar2.metadata == {"extra": "val"}

    def test_from_dict_with_naive_timestamp(self):
        d = {
            "timestamp": "2024-01-02T14:30:00",
            "open": 185.0, "high": 186.0, "low": 184.0,
            "close": 185.5, "volume": 1000000, "symbol": "AAPL",
            "timeframe": "1d", "source": "test", "metadata": {},
        }
        bar = OHLCV.from_dict(d)
        assert bar.timestamp.tzinfo == timezone.utc


class TestAgentSignal:
    def test_create_valid(self):
        sig = AgentSignal(
            direction=SignalDirection.BUY, confidence=0.82,
            reasoning="Strong fundamentals", agent_name="warren_buffett",
            agent_type="persona",
        )
        assert sig.direction == SignalDirection.BUY
        assert sig.confidence == 0.82

    def test_confidence_too_high_raises(self):
        with pytest.raises(ValueError, match="(?i)confidence"):
            AgentSignal(
                direction=SignalDirection.BUY, confidence=1.5,
                reasoning="test", agent_name="test", agent_type="test",
            )

    def test_confidence_too_low_raises(self):
        with pytest.raises(ValueError, match="(?i)confidence"):
            AgentSignal(
                direction=SignalDirection.SELL, confidence=-0.1,
                reasoning="test", agent_name="test", agent_type="test",
            )

    def test_confidence_boundary_values(self):
        sig0 = AgentSignal(
            direction=SignalDirection.HOLD, confidence=0.0,
            reasoning="test", agent_name="test", agent_type="test",
        )
        assert sig0.confidence == 0.0

        sig1 = AgentSignal(
            direction=SignalDirection.HOLD, confidence=1.0,
            reasoning="test", agent_name="test", agent_type="test",
        )
        assert sig1.confidence == 1.0

    def test_string_direction_coerced(self):
        sig = AgentSignal(
            direction="buy", confidence=0.7,
            reasoning="test", agent_name="test", agent_type="test",
        )
        assert sig.direction == SignalDirection.BUY

    def test_serialization_roundtrip(self):
        sig = AgentSignal(
            direction=SignalDirection.STRONG_SELL, confidence=0.9,
            reasoning="Market crash expected", agent_name="bear_agent",
            agent_type="debate", metadata={"model": "gpt-4o"},
        )
        d = sig.to_dict()
        assert d["direction"] == "strong_sell"
        assert isinstance(d["timestamp"], str)

        sig2 = AgentSignal.from_dict(d)
        assert sig2.direction == SignalDirection.STRONG_SELL
        assert sig2.confidence == 0.9
        assert sig2.agent_name == "bear_agent"
        assert sig2.metadata == {"model": "gpt-4o"}

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError):
            AgentSignal(
                direction="invalid_direction", confidence=0.5,
                reasoning="test", agent_name="test", agent_type="test",
            )


class TestOrder:
    def test_create_with_all_fields(self):
        order = Order(
            symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=100, price=185.0, stop_loss=180.0, take_profit=195.0,
            time_in_force="DAY", strategy_name="test_strategy",
        )
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == 100
        assert order.stop_loss == 180.0

    def test_string_side_coerced(self):
        order = Order(
            symbol="AAPL", side="sell", order_type="market", quantity=50,
        )
        assert order.side == OrderSide.SELL
        assert order.order_type == OrderType.MARKET

    def test_market_order_no_price(self):
        order = Order(
            symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=0.5,
        )
        assert order.price is None


class TestFill:
    def test_create_valid(self):
        fill = Fill(
            order_id="ord-123", symbol="AAPL", side=OrderSide.BUY,
            filled_qty=100, avg_price=185.50, timestamp=UTC_NOW,
            broker="alpaca", status=OrderStatus.FILLED,
            fees=1.0, slippage=0.05, latency_ms=45.2,
        )
        assert fill.status == OrderStatus.FILLED
        assert fill.fees == 1.0


class TestEnums:
    def test_signal_direction_values(self):
        assert SignalDirection.STRONG_BUY.value == "strong_buy"
        assert SignalDirection.BUY.value == "buy"
        assert SignalDirection.HOLD.value == "hold"
        assert SignalDirection.SELL.value == "sell"
        assert SignalDirection.STRONG_SELL.value == "strong_sell"

    def test_order_side_values(self):
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"

    def test_order_type_values(self):
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"

    def test_order_status_values(self):
        all_statuses = [s.value for s in OrderStatus]
        assert "pending" in all_statuses
        assert "filled" in all_statuses
        assert "partial" in all_statuses
        assert "rejected" in all_statuses
        assert "cancelled" in all_statuses


class TestPosition:
    def test_create(self):
        pos = Position(
            symbol="AAPL", quantity=100, avg_entry_price=185.0,
            current_price=190.0, unrealized_pnl=500.0,
            broker="alpaca", market="us_equity",
        )
        assert pos.unrealized_pnl == 500.0


class TestPortfolioState:
    def test_create(self):
        state = PortfolioState(
            cash=50000.0, positions=[], total_value=50000.0,
            daily_pnl=0.0, total_pnl=0.0, open_orders=[],
        )
        assert state.consecutive_losses == 0
        assert state.circuit_breaker_active is False


class TestEvent:
    def test_create_and_json_roundtrip(self):
        evt = Event(
            event_type="agent.signal", timestamp=UTC_NOW,
            payload={"direction": "buy", "confidence": 0.8},
            source_service="agent-engine", correlation_id="abc-123",
        )
        json_str = evt.to_json()
        evt2 = Event.from_json(json_str)
        assert evt2.event_type == "agent.signal"
        assert evt2.payload["direction"] == "buy"
        assert evt2.correlation_id == "abc-123"


class TestRiskAssessment:
    def test_create(self):
        ra = RiskAssessment(
            symbol="AAPL", approved=True, position_size=50,
            stop_loss_price=180.0, take_profit_price=195.0,
            risk_reward_ratio=2.75, max_loss_amount=250.0,
            sizing_model="kelly",
        )
        assert ra.approved is True
        assert ra.warnings == []
