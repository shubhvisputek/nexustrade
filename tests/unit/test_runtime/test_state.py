"""Unit tests for runtime.state — the dashboard's single source of truth."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nexustrade.core.models import (
    AgentSignal,
    CompositeSignal,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskAssessment,
    SignalDirection,
)
from nexustrade.runtime.state import (
    AlertRecord,
    RuntimeState,
    TickSummary,
    reset_runtime_state,
    get_runtime_state,
)


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_runtime_state()
    yield
    reset_runtime_state()


def _signal(direction=SignalDirection.BUY, conf=0.8) -> AgentSignal:
    return AgentSignal(
        direction=direction,
        confidence=conf,
        reasoning="because",
        agent_name="warren_buffett",
        agent_type="persona",
    )


def _composite(symbol="AAPL") -> CompositeSignal:
    return CompositeSignal(
        symbol=symbol,
        direction=SignalDirection.BUY,
        confidence=0.75,
        contributing_signals=[_signal()],
        aggregation_mode="weighted_confidence",
        reasoning="agg",
        timestamp=datetime.now(UTC),
    )


def _assessment(approved=True) -> RiskAssessment:
    return RiskAssessment(
        symbol="AAPL",
        approved=approved,
        position_size=10.0,
        stop_loss_price=95.0,
        take_profit_price=110.0,
        risk_reward_ratio=1.5,
        max_loss_amount=50.0,
        sizing_model="fixed_fraction",
    )


def _order() -> Order:
    return Order(
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        price=100.0,
    )


def _fill(order_id="abc") -> Fill:
    return Fill(
        order_id=order_id,
        symbol="AAPL",
        side=OrderSide.BUY,
        filled_qty=10.0,
        avg_price=100.0,
        timestamp=datetime.now(UTC),
        broker="paper",
        status=OrderStatus.FILLED,
    )


class TestRuntimeState:
    def test_singleton(self):
        a = get_runtime_state()
        b = get_runtime_state()
        assert a is b

    def test_lifecycle_start_stop_pause_resume(self):
        s = RuntimeState()
        assert not s.is_running
        s.start("config/demo.yaml", {"version": "0.1"})
        assert s.is_running and s.config_path == "config/demo.yaml"
        s.pause("test")
        assert s.is_paused
        s.resume()
        assert not s.is_paused
        s.stop()
        assert not s.is_running

    def test_kill_switch_blocks_and_audits(self):
        s = RuntimeState()
        s.engage_kill_switch("risk breach")
        assert s.kill_switch_engaged and s.is_paused
        audit_cats = [a.category for a in s.audit]
        assert "system" in audit_cats
        assert any("KILL SWITCH" in a.message for a in s.audit)
        s.disengage_kill_switch()
        assert not s.kill_switch_engaged

    def test_record_signal_and_reasoning_trace_added(self):
        s = RuntimeState()
        s.record_signal(_signal(), symbol="AAPL", correlation_id="c1")
        assert len(s.signals) == 1
        trace = s.signals[0]
        assert trace.symbol == "AAPL"
        assert trace.agent_name == "warren_buffett"
        assert trace.direction == "buy"
        assert trace.metadata.get("correlation_id") == "c1"

    def test_record_composite_updates_latest(self):
        s = RuntimeState()
        s.record_composite(_composite())
        assert "AAPL" in s.latest_composite
        assert s.latest_composite["AAPL"].direction == "buy"

    def test_record_risk_updates_latest_and_audits(self):
        s = RuntimeState()
        s.record_risk(_assessment(approved=True))
        assert "AAPL" in s.latest_risk
        assert s.latest_risk["AAPL"].approved is True
        assert any(a.category == "risk" for a in s.audit)

    def test_record_order_and_fill_both_appear(self):
        s = RuntimeState()
        order = _order()
        fill = _fill(order_id="ord1")
        s.record_order(order, order_id="ord1", broker="paper", correlation_id="x")
        s.record_fill(fill, correlation_id="x")
        assert len(s.orders) == 1 and s.orders[0].order_id == "ord1"
        assert len(s.fills) == 1 and s.fills[0].order_id == "ord1"

    def test_update_account_appends_equity_point(self):
        s = RuntimeState()
        s.update_account(
            {"cash": 100.0, "positions_value": 50.0, "total_value": 150.0,
             "daily_pnl": 1.0, "total_pnl": 2.0, "initial_cash": 100.0,
             "num_positions": 1, "num_trades": 1}
        )
        assert len(s.equity_curve) == 1
        assert s.equity_curve[0].total_value == 150.0

    def test_buffers_are_bounded(self):
        s = RuntimeState(max_signals=3)
        for i in range(10):
            s.record_signal(_signal(conf=0.5 + i * 0.01), symbol=f"X{i}")
        assert len(s.signals) == 3
        # newest retained
        assert s.signals[-1].symbol == "X9"

    def test_tick_summary_records_and_updates_last_tick(self):
        s = RuntimeState()
        summary = TickSummary(
            timestamp="2026-04-16T00:00:00+00:00",
            correlation_id="cid",
            symbols=["AAPL"],
            signals_emitted=2,
            composite_signals=1,
            orders_placed=1,
            orders_blocked=0,
            duration_ms=42.0,
        )
        s.record_tick(summary)
        assert s.last_tick_at == "2026-04-16T00:00:00+00:00"
        assert len(s.ticks) == 1

    def test_snapshot_shape(self):
        s = RuntimeState()
        snap = s.snapshot()
        for key in (
            "is_running", "is_paused", "kill_switch_engaged",
            "last_tick_at", "config_path", "account", "risk_status",
        ):
            assert key in snap

    def test_alert_record_round_trip(self):
        s = RuntimeState()
        rec = AlertRecord(
            timestamp="2026-04-16T00:00:00+00:00",
            title="Trade",
            message="Bought AAPL",
            level="info",
            channels=["telegram"],
            delivered={"telegram": True},
        )
        s.record_alert(rec)
        assert len(s.alerts) == 1

    def test_backtest_result_stored(self):
        s = RuntimeState()
        s.store_backtest_result("sma_crossover", {"final_value": 120_000})
        assert "sma_crossover" in s.backtests
        assert s.backtests["sma_crossover"]["final_value"] == 120_000
