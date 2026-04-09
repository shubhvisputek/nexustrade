"""Tests for the TradingView webhook receiver."""

import pytest

from nexustrade.core.models import OrderSide, OrderStatus
from nexustrade.execution.backends.paper import PaperBackend
from nexustrade.execution.webhooks import create_webhook_router

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

pytestmark = pytest.mark.unit


@pytest.fixture
def paper_backend() -> PaperBackend:
    return PaperBackend(initial_cash=100_000.0)


@pytest.fixture
def app_client(paper_backend: PaperBackend):  # type: ignore[no-untyped-def]
    if not _HAS_FASTAPI:
        pytest.skip("FastAPI not installed")

    app = FastAPI()
    router = create_webhook_router(
        passphrase="test_secret",
        brokers={"paper": paper_backend},
        default_broker="paper",
    )
    app.include_router(router)
    return TestClient(app)


class TestWebhookValidPassphrase:
    def test_valid_webhook_returns_200(self, app_client) -> None:  # type: ignore[no-untyped-def]
        payload = {
            "passphrase": "test_secret",
            "ticker": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
        }
        resp = app_client.post("/webhook", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["symbol"] == "AAPL"
        assert data["side"] == "buy"
        assert data["filled_qty"] == 10

    def test_sell_order(self, app_client, paper_backend) -> None:  # type: ignore[no-untyped-def]
        # Buy first to have a position
        buy_payload = {
            "passphrase": "test_secret",
            "ticker": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
        }
        app_client.post("/webhook", json=buy_payload)

        sell_payload = {
            "passphrase": "test_secret",
            "ticker": "AAPL",
            "action": "sell",
            "quantity": 10,
            "price": 155.0,
        }
        resp = app_client.post("/webhook", json=sell_payload)
        assert resp.status_code == 200
        assert resp.json()["side"] == "sell"


class TestWebhookInvalidPassphrase:
    def test_wrong_passphrase_returns_401(self, app_client) -> None:  # type: ignore[no-untyped-def]
        payload = {
            "passphrase": "wrong_secret",
            "ticker": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
        }
        resp = app_client.post("/webhook", json=payload)
        assert resp.status_code == 401

    def test_missing_passphrase_returns_401(self, app_client) -> None:  # type: ignore[no-untyped-def]
        payload = {
            "ticker": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
        }
        resp = app_client.post("/webhook", json=payload)
        assert resp.status_code == 401


class TestWebhookBadPayloads:
    def test_missing_ticker_returns_400(self, app_client) -> None:  # type: ignore[no-untyped-def]
        payload = {
            "passphrase": "test_secret",
            "action": "buy",
        }
        resp = app_client.post("/webhook", json=payload)
        assert resp.status_code == 400

    def test_invalid_action_returns_400(self, app_client) -> None:  # type: ignore[no-untyped-def]
        payload = {
            "passphrase": "test_secret",
            "ticker": "AAPL",
            "action": "invalid",
        }
        resp = app_client.post("/webhook", json=payload)
        assert resp.status_code == 400

    def test_unknown_broker_returns_400(self, app_client) -> None:  # type: ignore[no-untyped-def]
        payload = {
            "passphrase": "test_secret",
            "ticker": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
            "broker": "nonexistent",
        }
        resp = app_client.post("/webhook", json=payload)
        assert resp.status_code == 400
