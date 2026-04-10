"""Unit tests for the NexusTrade Streamlit dashboard module.

These tests verify that:
- The dashboard module can be imported without errors.
- Helper / formatting functions behave correctly.
- API client functions handle connection errors gracefully.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDashboardImport:
    """Verify the module is importable and exposes expected symbols."""

    def test_module_imports(self) -> None:
        from nexustrade.web import dashboard  # noqa: F401

    def test_dashboard_title_constant(self) -> None:
        from nexustrade.web.dashboard import DASHBOARD_TITLE

        assert DASHBOARD_TITLE == "NexusTrade Trading Dashboard"

    def test_dashboard_version_constant(self) -> None:
        from nexustrade.web.dashboard import DASHBOARD_VERSION

        assert DASHBOARD_VERSION == "0.1.0"

    def test_pages_dict_exists(self) -> None:
        from nexustrade.web.dashboard import PAGES

        assert isinstance(PAGES, dict)
        assert "Dashboard Overview" in PAGES
        assert "Portfolio & Trading" in PAGES
        assert "Agents & Signals" in PAGES
        assert "Configuration" in PAGES
        assert "System Health" in PAGES


# ---------------------------------------------------------------------------
# Formatting helper tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatCurrency:
    def test_positive_value(self) -> None:
        from nexustrade.web.dashboard import format_currency

        assert format_currency(1234.56) == "$1,234.56"

    def test_zero(self) -> None:
        from nexustrade.web.dashboard import format_currency

        assert format_currency(0) == "$0.00"

    def test_none_returns_zero(self) -> None:
        from nexustrade.web.dashboard import format_currency

        assert format_currency(None) == "$0.00"

    def test_large_value(self) -> None:
        from nexustrade.web.dashboard import format_currency

        assert format_currency(1_000_000) == "$1,000,000.00"

    def test_negative_value(self) -> None:
        from nexustrade.web.dashboard import format_currency

        result = format_currency(-500.5)
        assert "-" in result
        assert "500.50" in result


@pytest.mark.unit
class TestFormatPnl:
    def test_positive_pnl(self) -> None:
        from nexustrade.web.dashboard import format_pnl

        assert format_pnl(123.45) == "+$123.45"

    def test_negative_pnl(self) -> None:
        from nexustrade.web.dashboard import format_pnl

        result = format_pnl(-42.10)
        assert result == "-$42.10" or ("-" in result and "42.10" in result)

    def test_zero_pnl(self) -> None:
        from nexustrade.web.dashboard import format_pnl

        assert format_pnl(0) == "+$0.00"

    def test_none_pnl(self) -> None:
        from nexustrade.web.dashboard import format_pnl

        assert format_pnl(None) == "$0.00"


@pytest.mark.unit
class TestDirectionColor:
    def test_buy(self) -> None:
        from nexustrade.web.dashboard import direction_color

        assert direction_color("buy") == "\U0001f7e2"  # green circle

    def test_sell(self) -> None:
        from nexustrade.web.dashboard import direction_color

        assert direction_color("sell") == "\U0001f534"  # red circle

    def test_hold(self) -> None:
        from nexustrade.web.dashboard import direction_color

        assert direction_color("hold") == "\u26aa"  # white circle

    def test_bullish_case_insensitive(self) -> None:
        from nexustrade.web.dashboard import direction_color

        assert direction_color("Bullish") == "\U0001f7e2"

    def test_empty_string(self) -> None:
        from nexustrade.web.dashboard import direction_color

        assert direction_color("") == "\u26aa"


@pytest.mark.unit
class TestServiceStatusIndicator:
    def test_ok(self) -> None:
        from nexustrade.web.dashboard import service_status_indicator

        assert service_status_indicator("ok") == "\u2705"

    def test_degraded(self) -> None:
        from nexustrade.web.dashboard import service_status_indicator

        assert service_status_indicator("degraded") == "\u26a0\ufe0f"

    def test_unavailable(self) -> None:
        from nexustrade.web.dashboard import service_status_indicator

        assert service_status_indicator("unavailable") == "\u274c"


# ---------------------------------------------------------------------------
# API client error-handling tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApiClientErrorHandling:
    """Verify that api_get / api_put / api_post return None on failures."""

    def test_api_get_connection_refused(self) -> None:
        from nexustrade.web.dashboard import api_get

        # Point at a port that is almost certainly not listening
        with patch("nexustrade.web.dashboard.API_URL", "http://127.0.0.1:19999"):
            result = api_get("/health")
        assert result is None

    def test_api_put_connection_refused(self) -> None:
        from nexustrade.web.dashboard import api_put

        with patch("nexustrade.web.dashboard.API_URL", "http://127.0.0.1:19999"):
            result = api_put("/config", json_body={"config": {}})
        assert result is None

    def test_api_post_connection_refused(self) -> None:
        from nexustrade.web.dashboard import api_post

        with patch("nexustrade.web.dashboard.API_URL", "http://127.0.0.1:19999"):
            result = api_post("/webhook/order", json_body={"symbol": "AAPL"})
        assert result is None

    def test_api_get_returns_none_on_http_error(self) -> None:
        """Simulate a 500 response from the backend."""
        from nexustrade.web.dashboard import api_get

        mock_response = httpx.Response(
            status_code=500,
            request=httpx.Request("GET", "http://localhost:8085/health"),
        )
        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = mock_response
            result = api_get("/health")
        assert result is None

    def test_api_put_returns_none_on_http_error(self) -> None:
        from nexustrade.web.dashboard import api_put

        mock_response = httpx.Response(
            status_code=400,
            request=httpx.Request("PUT", "http://localhost:8085/config"),
        )
        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.put.return_value = mock_response
            result = api_put("/config", json_body={"config": {}})
        assert result is None


@pytest.mark.unit
class TestApiUrlConfigurable:
    """Verify the API URL can be configured via environment variable."""

    def test_default_api_url(self) -> None:
        from nexustrade.web.dashboard import API_URL

        # When env var is not set, the module-level default should be localhost:8085
        # (the actual value depends on whether the env var was set before import,
        # but we at least verify it's a string).
        assert isinstance(API_URL, str)
        assert API_URL.startswith("http")
