"""Unit tests for the rewritten Streamlit dashboard module.

Verifies that:
- The module imports cleanly under a Streamlit-free harness.
- Helper / formatting functions behave correctly.
- API client helpers surface errors instead of returning None.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import httpx
import pytest


def _stub_streamlit() -> None:
    """Install a no-op Streamlit shim so the dashboard module can import.

    The real Streamlit needs a running script-runner; for unit tests we
    only need the module-level constants to load.
    """
    if "streamlit" in sys.modules and not isinstance(
        sys.modules["streamlit"], types.ModuleType
    ):
        return
    st = types.ModuleType("streamlit")

    class _Sidebar:
        def __getattr__(self, _name: str):
            return MagicMock()

    st.sidebar = _Sidebar()  # type: ignore[attr-defined]

    def _passthrough(*args, **kwargs):  # type: ignore[no-untyped-def]
        return MagicMock()

    for name in (
        "set_page_config", "title", "caption", "subheader", "divider",
        "metric", "info", "warning", "error", "success", "toast", "json",
        "markdown", "dataframe", "line_chart", "area_chart", "bar_chart",
        "container", "expander", "radio", "selectbox", "text_input",
        "number_input", "slider", "checkbox", "form", "form_submit_button",
        "button", "spinner", "file_uploader", "download_button",
        "data_editor", "session_state", "rerun", "text_area", "tabs",
        "columns", "stop",
    ):
        setattr(st, name, _passthrough)
    sys.modules["streamlit"] = st


_stub_streamlit()


# ---------------------------------------------------------------------------
# Import-time tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDashboardImport:
    def test_module_imports_without_running_main(self) -> None:
        # The module calls main() at import time, but every function call
        # is a MagicMock no-op via the streamlit stub above.
        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.side_effect = httpx.ConnectError("offline")
            mock_client.post.side_effect = httpx.ConnectError("offline")
            from nexustrade.web import dashboard  # noqa: F401

    def test_pages_dict_exists(self) -> None:
        from nexustrade.web.dashboard import PAGES

        assert isinstance(PAGES, dict)
        assert any("Live Monitor" in k for k in PAGES)
        assert any("Portfolio" in k for k in PAGES)
        assert any("Agents" in k for k in PAGES)
        assert any("Backtest" in k for k in PAGES)
        assert any("Risk" in k for k in PAGES)
        assert any("Configuration" in k for k in PAGES)
        assert any("Audit" in k for k in PAGES)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatMoney:
    def test_positive_value(self) -> None:
        from nexustrade.web.dashboard import _fmt_money
        assert _fmt_money(1234.56) == "$1,234.56"

    def test_zero(self) -> None:
        from nexustrade.web.dashboard import _fmt_money
        assert _fmt_money(0) == "$0.00"

    def test_none_returns_em_dash(self) -> None:
        from nexustrade.web.dashboard import _fmt_money
        assert _fmt_money(None) == "—"

    def test_large_value(self) -> None:
        from nexustrade.web.dashboard import _fmt_money
        assert _fmt_money(1_000_000) == "$1,000,000.00"

    def test_negative_value(self) -> None:
        from nexustrade.web.dashboard import _fmt_money
        result = _fmt_money(-500.5)
        assert result.startswith("-$")
        assert "500.50" in result


@pytest.mark.unit
class TestTsShort:
    def test_iso_returns_hms(self) -> None:
        from nexustrade.web.dashboard import _ts_short
        assert _ts_short("2026-04-16T12:34:56+00:00") == "12:34:56"

    def test_none_returns_em_dash(self) -> None:
        from nexustrade.web.dashboard import _ts_short
        assert _ts_short(None) == "—"

    def test_unparseable_returns_input(self) -> None:
        from nexustrade.web.dashboard import _ts_short
        assert _ts_short("not-a-date") == "not-a-date"


@pytest.mark.unit
class TestDirectionEmoji:
    def test_known_directions_have_emoji(self) -> None:
        from nexustrade.web.dashboard import _DIRECTION_EMOJI
        for d in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
            assert d in _DIRECTION_EMOJI


# ---------------------------------------------------------------------------
# API client error handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApiClientErrorHandling:
    def test_api_get_connection_refused_returns_error_dict(self) -> None:
        from nexustrade.web import dashboard

        with patch("nexustrade.web.dashboard.API_URL", "http://127.0.0.1:19999"):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = mock_client_cls.return_value.__enter__.return_value
                mock_client.get.side_effect = httpx.ConnectError("refused")
                result = dashboard._api_get("/health")
        assert isinstance(result, dict)
        assert "_error" in result

    def test_api_post_returns_error_dict_on_http_error(self) -> None:
        from nexustrade.web import dashboard

        mock_response = httpx.Response(
            status_code=400,
            content=b"bad request",
            request=httpx.Request("POST", "http://localhost:8085/orders/manual"),
        )
        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_response
            result = dashboard._api_post("/orders/manual", {"symbol": "AAPL"})
        assert isinstance(result, dict)
        assert "_error" in result
        assert result["_error"].startswith("400")

    def test_api_put_returns_error_dict_on_http_error(self) -> None:
        from nexustrade.web import dashboard

        mock_response = httpx.Response(
            status_code=400,
            content=b"bad",
            request=httpx.Request("PUT", "http://localhost:8085/config"),
        )
        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.put.return_value = mock_response
            result = dashboard._api_put("/config", {"config": {}})
        assert isinstance(result, dict)
        assert "_error" in result


@pytest.mark.unit
class TestApiUrlConfigurable:
    def test_default_api_url(self) -> None:
        from nexustrade.web.dashboard import API_URL
        assert isinstance(API_URL, str)
        assert API_URL.startswith("http")
