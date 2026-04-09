"""Shared test fixtures for NexusTrade test suite."""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def aapl_ohlcv_data() -> list[dict]:
    """Load 50 daily OHLCV bars for AAPL."""
    with open(FIXTURES_DIR / "ohlcv_aapl.json") as f:
        return json.load(f)


@pytest.fixture
def reliance_ohlcv_data() -> list[dict]:
    """Load 50 daily OHLCV bars for RELIANCE."""
    with open(FIXTURES_DIR / "ohlcv_reliance.json") as f:
        return json.load(f)


@pytest.fixture
def btc_ohlcv_data() -> list[dict]:
    """Load 50 hourly OHLCV bars for BTC/USDT."""
    with open(FIXTURES_DIR / "ohlcv_btc.json") as f:
        return json.load(f)


@pytest.fixture
def news_samples() -> list[dict]:
    """Load 10 sample news items across AAPL, RELIANCE, and BTC."""
    with open(FIXTURES_DIR / "news_samples.json") as f:
        return json.load(f)


@pytest.fixture
def agent_signal_samples() -> list[dict]:
    """Load 5 sample agent signals from different agent types."""
    with open(FIXTURES_DIR / "agent_signals.json") as f:
        return json.load(f)


@pytest.fixture
def sample_ohlcv_bar() -> dict:
    """Return a single AAPL OHLCV bar for simple tests."""
    return {
        "timestamp": "2024-01-15T14:30:00Z",
        "open": 186.50,
        "high": 187.10,
        "low": 185.80,
        "close": 186.25,
        "volume": 37654200,
        "symbol": "AAPL",
        "timeframe": "1d",
        "source": "test",
    }


@pytest.fixture
def sample_agent_signal() -> dict:
    """Return a single agent signal for simple tests."""
    return {
        "direction": "buy",
        "confidence": 0.82,
        "reasoning": "Strong fundamentals with consistent revenue growth, high margins, and significant cash reserves. Current price-to-earnings ratio remains attractive relative to sector peers. Long-term competitive moat through ecosystem lock-in.",
        "agent_name": "warren_buffett",
        "agent_type": "persona",
        "timestamp": "2024-01-15T12:00:00Z",
        "metadata": {},
    }
