"""Unit tests for the expanded FastAPI surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexustrade.runtime.state import (
    AlertRecord,
    AuditEvent,
    EquityPoint,
    FillTrace,
    OrderTrace,
    ReasoningTrace,
    get_runtime_state,
    reset_runtime_state,
)
from nexustrade.web.app import app


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_runtime_state()
    yield
    reset_runtime_state()


@pytest.fixture
def client():
    return TestClient(app)


def test_root_returns_metadata(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "NexusTrade API"


def test_portfolio_empty_when_no_loop(client):
    r = client.get("/portfolio")
    assert r.status_code == 200
    assert r.json()["cash"] == 0.0


def test_signals_empty_then_populated(client):
    state = get_runtime_state()
    state.signals.append(ReasoningTrace(
        timestamp="t", symbol="AAPL", agent_name="warren_buffett",
        agent_type="persona", direction="buy", confidence=0.8,
        reasoning="because", metadata={},
    ))
    r = client.get("/signals")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["agent_name"] == "warren_buffett"


def test_signals_by_symbol_filter(client):
    state = get_runtime_state()
    state.signals.append(ReasoningTrace(
        timestamp="t", symbol="AAPL", agent_name="a", agent_type="p",
        direction="buy", confidence=0.8, reasoning="", metadata={},
    ))
    state.signals.append(ReasoningTrace(
        timestamp="t", symbol="MSFT", agent_name="a", agent_type="p",
        direction="sell", confidence=0.8, reasoning="", metadata={},
    ))
    r = client.get("/signals/AAPL")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["symbol"] == "AAPL"


def test_config_get_returns_default(client):
    r = client.get("/config")
    assert r.status_code == 200
    data = r.json()
    assert "llm" in data or "version" in data


def test_config_deep_merge_does_not_clobber(client):
    client.put("/config", json={"config": {
        "llm": {"mode": "local", "provider": "ollama", "model": "llama3:8b"}
    }})
    r = client.put("/config", json={"config": {"llm": {"mode": "cloud"}}})
    assert r.status_code == 200
    data = r.json()
    assert data["llm"]["mode"] == "cloud"
    assert data["llm"]["provider"] == "ollama"  # unchanged
    assert data["llm"]["model"] == "llama3:8b"


def test_config_rejects_sensitive_keys(client):
    r = client.put("/config", json={"config": {"api_key": "x"}})
    assert r.status_code == 400


def test_agents_reasoning_filter(client):
    state = get_runtime_state()
    state.signals.append(ReasoningTrace(
        timestamp="t", symbol="AAPL", agent_name="warren_buffett",
        agent_type="persona", direction="buy", confidence=0.8,
        reasoning="", metadata={},
    ))
    state.signals.append(ReasoningTrace(
        timestamp="t", symbol="AAPL", agent_name="ben_graham",
        agent_type="persona", direction="sell", confidence=0.8,
        reasoning="", metadata={},
    ))
    r = client.get("/agents/reasoning", params={"agent": "warren_buffett"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["agent_name"] == "warren_buffett"


def test_orders_endpoints(client):
    state = get_runtime_state()
    state.orders.append(OrderTrace(
        timestamp="t", order_id="o1", symbol="AAPL", side="buy",
        order_type="market", quantity=10, price=100.0,
        status="pending", broker="paper",
    ))
    state.fills.append(FillTrace(
        timestamp="t", order_id="o1", symbol="AAPL", side="buy",
        filled_qty=10, avg_price=100.0, broker="paper", fees=0.1, slippage=0.1,
    ))
    r = client.get("/orders")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.get("/orders/fills")
    assert r.status_code == 200
    assert r.json()[0]["order_id"] == "o1"


def test_manual_order_rejected_without_running_loop(client):
    r = client.post("/orders/manual", json={
        "symbol": "AAPL", "side": "buy", "quantity": 1,
    })
    assert r.status_code == 409  # Loop not running


def test_risk_status(client):
    state = get_runtime_state()
    state.set_risk_status({"circuit_breaker_active": True, "circuit_breaker_reason": "test"})
    r = client.get("/risk")
    assert r.status_code == 200
    data = r.json()
    assert data["circuit_breaker_active"] is True


def test_audit_log_and_alerts_feed(client):
    state = get_runtime_state()
    state.audit.append(AuditEvent(
        timestamp="t", category="system", level="info", message="hi",
    ))
    state.alerts.append(AlertRecord(
        timestamp="t", title="fill", message="m", level="info",
        channels=["telegram"], delivered={"telegram": True},
    ))
    r = client.get("/audit/log")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.get("/audit/alerts")
    assert r.status_code == 200
    assert r.json()[0]["title"] == "fill"

    # Equity endpoint
    state.equity_curve.append(EquityPoint(
        timestamp="t", cash=100, positions_value=0, total_value=100,
        daily_pnl=0, total_pnl=0,
    ))
    r = client.get("/audit/equity")
    assert r.status_code == 200
    assert r.json()[0]["total_value"] == 100


def test_runtime_status_and_tick_without_loop(client):
    r = client.get("/runtime")
    assert r.status_code == 200
    data = r.json()
    assert "is_running" in data
    assert data["loop_running"] is False

    r = client.post("/runtime/tick")
    assert r.status_code == 400


def test_kill_switch_endpoints(client):
    r = client.post("/runtime/kill-switch", params={"reason": "test"})
    assert r.status_code == 200
    state = get_runtime_state()
    assert state.kill_switch_engaged

    r = client.post("/runtime/kill-switch/release")
    assert r.status_code == 200
    assert not state.kill_switch_engaged


def test_backtest_list_empty(client):
    r = client.get("/backtest")
    assert r.status_code == 200
    assert r.json() == {}
