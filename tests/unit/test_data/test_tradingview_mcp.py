"""Unit tests for TradingView MCP data adapter (stdio transport)."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexustrade.data.adapters.tradingview_mcp import (
    MCPStdioClient,
    TradingViewMCPAdapter,
)


# ---------------------------------------------------------------------------
# MCPStdioClient tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMCPStdioClient:
    """Tests for the stdio-based MCP JSON-RPC client."""

    def test_initialization(self) -> None:
        """Client stores server command and cwd."""
        client = MCPStdioClient(
            server_command=["node", "src/server.js"],
            cwd="/some/path",
        )
        assert client._server_command == ["node", "src/server.js"]
        assert client._cwd == "/some/path"
        assert client._process is None
        assert client._request_id == 0

    def test_is_running_false_when_no_process(self) -> None:
        """is_running is False before start."""
        client = MCPStdioClient(["node", "server.js"])
        assert client.is_running is False

    def test_is_running_true_with_active_process(self) -> None:
        """is_running is True when process is alive."""
        client = MCPStdioClient(["node", "server.js"])
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        client._process = mock_proc
        assert client.is_running is True

    def test_is_running_false_when_process_exited(self) -> None:
        """is_running is False when process has exited."""
        client = MCPStdioClient(["node", "server.js"])
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # exited
        client._process = mock_proc
        assert client.is_running is False

    @pytest.mark.asyncio
    async def test_call_tool_parses_json_text(self) -> None:
        """call_tool parses JSON from MCP text content."""
        client = MCPStdioClient(["node", "server.js"])
        # Mock call_method to return MCP-style result
        client.call_method = AsyncMock(return_value={
            "content": [{"type": "text", "text": '{"success": true, "value": 42}'}],
        })
        result = await client.call_tool("some_tool", {"key": "val"})
        assert result == {"success": True, "value": 42}

    @pytest.mark.asyncio
    async def test_call_tool_returns_plain_text(self) -> None:
        """call_tool returns plain string when text is not valid JSON."""
        client = MCPStdioClient(["node", "server.js"])
        client.call_method = AsyncMock(return_value={
            "content": [{"type": "text", "text": "plain text response"}],
        })
        result = await client.call_tool("some_tool")
        assert result == "plain text response"

    @pytest.mark.asyncio
    async def test_call_tool_no_content(self) -> None:
        """call_tool returns raw result when no content key."""
        client = MCPStdioClient(["node", "server.js"])
        client.call_method = AsyncMock(return_value={"status": "ok"})
        result = await client.call_tool("some_tool")
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_stop_terminates_process(self) -> None:
        """stop() terminates the subprocess."""
        client = MCPStdioClient(["node", "server.js"])
        mock_proc = MagicMock()
        client._process = mock_proc

        await client.stop()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=5)
        assert client._process is None


# ---------------------------------------------------------------------------
# TradingViewMCPAdapter tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTradingViewMCPAdapter:
    """Tests for the TradingView MCP data adapter (stdio transport)."""

    def _make_adapter(self, **kwargs) -> TradingViewMCPAdapter:
        config = {"auto_start": False}
        config.update(kwargs)
        return TradingViewMCPAdapter(config)

    def _adapter_with_mock_client(self) -> tuple[TradingViewMCPAdapter, AsyncMock]:
        """Create adapter with a pre-injected mock client."""
        adapter = self._make_adapter()
        mock_client = AsyncMock(spec=MCPStdioClient)
        mock_client.is_running = True
        adapter._client = mock_client
        return adapter, mock_client

    # -- properties --

    def test_name(self) -> None:
        adapter = TradingViewMCPAdapter()
        assert adapter.name == "tradingview_mcp"

    def test_supported_markets(self) -> None:
        adapter = TradingViewMCPAdapter()
        markets = adapter.supported_markets
        assert "us_equity" in markets
        assert "crypto" in markets
        assert "commodity" in markets
        assert "india_equity" in markets
        assert "forex" in markets

    # -- get_ohlcv --

    @pytest.mark.asyncio
    async def test_get_ohlcv_success(self) -> None:
        """get_ohlcv parses bars from MCP response."""
        adapter, mock_client = self._adapter_with_mock_client()

        async def call_tool_side_effect(tool_name, args=None):
            if tool_name == "data_get_ohlcv":
                return {
                    "success": True,
                    "bars": [
                        {
                            "time": 1704067200,  # 2024-01-01 00:00 UTC
                            "open": 100.0,
                            "high": 105.0,
                            "low": 99.0,
                            "close": 103.0,
                            "volume": 1000000,
                        },
                        {
                            "time": 1704153600,  # 2024-01-02 00:00 UTC
                            "open": 103.0,
                            "high": 107.0,
                            "low": 102.0,
                            "close": 106.0,
                            "volume": 1200000,
                        },
                    ],
                }
            return {"success": True}

        mock_client.call_tool = AsyncMock(side_effect=call_tool_side_effect)

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 12, 31, tzinfo=timezone.utc)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            bars = await adapter.get_ohlcv("AAPL", "1d", start, end)

        assert len(bars) == 2
        assert bars[0].symbol == "AAPL"
        assert bars[0].open == 100.0
        assert bars[0].high == 105.0
        assert bars[0].close == 103.0
        assert bars[0].volume == 1000000
        assert bars[0].source == "tradingview_mcp"
        assert bars[0].timeframe == "1d"

    @pytest.mark.asyncio
    async def test_get_ohlcv_empty_on_failure(self) -> None:
        """get_ohlcv returns empty list when MCP call fails."""
        adapter, mock_client = self._adapter_with_mock_client()
        mock_client.call_tool = AsyncMock(return_value={"success": False})

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 12, 31, tzinfo=timezone.utc)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            bars = await adapter.get_ohlcv("AAPL", "1d", start, end)

        assert bars == []

    @pytest.mark.asyncio
    async def test_get_ohlcv_filters_by_date_range(self) -> None:
        """get_ohlcv filters bars outside the requested date range."""
        adapter, mock_client = self._adapter_with_mock_client()

        async def call_tool_side_effect(tool_name, args=None):
            if tool_name == "data_get_ohlcv":
                return {
                    "success": True,
                    "bars": [
                        {"time": 1704067200, "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000000},  # Jan 1
                        {"time": 1706745600, "open": 103, "high": 107, "low": 102, "close": 106, "volume": 1200000},  # Feb 1
                    ],
                }
            return {"success": True}

        mock_client.call_tool = AsyncMock(side_effect=call_tool_side_effect)

        # Only request January
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, tzinfo=timezone.utc)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            bars = await adapter.get_ohlcv("AAPL", "1d", start, end)

        assert len(bars) == 1
        assert bars[0].open == 100.0

    # -- get_quote --

    @pytest.mark.asyncio
    async def test_get_quote_success(self) -> None:
        """get_quote returns Quote from MCP response."""
        adapter, mock_client = self._adapter_with_mock_client()
        mock_client.call_tool = AsyncMock(return_value={
            "success": True,
            "data": {
                "bid": 149.50,
                "ask": 150.50,
                "last": 150.00,
                "volume": 5000000,
            },
        })

        quote = await adapter.get_quote("AAPL")

        assert quote.symbol == "AAPL"
        assert quote.bid == 149.50
        assert quote.ask == 150.50
        assert quote.last == 150.00
        assert quote.volume == 5000000
        assert quote.source == "tradingview_mcp"

    @pytest.mark.asyncio
    async def test_get_quote_failure_raises(self) -> None:
        """get_quote raises RuntimeError on failure."""
        adapter, mock_client = self._adapter_with_mock_client()
        mock_client.call_tool = AsyncMock(return_value={"success": False})

        with pytest.raises(RuntimeError, match="Failed to get quote"):
            await adapter.get_quote("AAPL")

    # -- get_technicals --

    @pytest.mark.asyncio
    async def test_get_technicals_parses_studies(self) -> None:
        """get_technicals parses study values into TechnicalIndicators."""
        adapter, mock_client = self._adapter_with_mock_client()

        async def call_tool_side_effect(tool_name, args=None):
            if tool_name == "data_get_study_values":
                return {
                    "success": True,
                    "studies": {
                        "RSI": {"RSI": 55.3, "value": 55.3},
                        "MACD": {"MACD": 1.23, "Signal": 0.98, "Histogram": 0.25},
                        "Bollinger Bands": {"Upper": 155.0, "Basis": 150.0, "Lower": 145.0},
                        "ADX": {"ADX": 25.1},
                        "ATR": {"ATR": 3.5},
                        "Stochastic": {"%K": 70.0, "%D": 65.0},
                        "Custom Study": {"value": 42.0},
                    },
                }
            return {"success": True}

        mock_client.call_tool = AsyncMock(side_effect=call_tool_side_effect)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.get_technicals("AAPL", "1d")

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.timeframe == "1d"
        assert result.source == "tradingview_mcp"
        assert result.rsi == 55.3
        assert result.macd == 1.23
        assert result.macd_signal == 0.98
        assert result.macd_histogram == 0.25
        assert result.bb_upper == 155.0
        assert result.bb_middle == 150.0
        assert result.bb_lower == 145.0
        assert result.adx == 25.1
        assert result.atr == 3.5
        assert result.stoch_k == 70.0
        assert result.stoch_d == 65.0
        # All studies stored in extra
        assert "Custom Study" in result.extra
        assert "RSI" in result.extra

    @pytest.mark.asyncio
    async def test_get_technicals_failure_returns_none(self) -> None:
        """get_technicals returns None when MCP call fails."""
        adapter, mock_client = self._adapter_with_mock_client()

        async def call_tool_side_effect(tool_name, args=None):
            if tool_name == "data_get_study_values":
                return {"success": False}
            return {"success": True}

        mock_client.call_tool = AsyncMock(side_effect=call_tool_side_effect)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.get_technicals("AAPL", "1d")

        assert result is None

    # -- get_chart_image --

    @pytest.mark.asyncio
    async def test_get_chart_image_base64(self) -> None:
        """get_chart_image decodes base64 screenshot data."""
        adapter, mock_client = self._adapter_with_mock_client()
        png_data = b"\x89PNG\r\n\x1a\nfake_image_data"
        b64_data = base64.b64encode(png_data).decode()

        async def call_tool_side_effect(tool_name, args=None):
            if tool_name == "capture_screenshot":
                return {"success": True, "data": b64_data}
            return {"success": True}

        mock_client.call_tool = AsyncMock(side_effect=call_tool_side_effect)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.get_chart_image("AAPL", "1d")

        assert result == png_data

    @pytest.mark.asyncio
    async def test_get_chart_image_failure_returns_none(self) -> None:
        """get_chart_image returns None on failure."""
        adapter, mock_client = self._adapter_with_mock_client()

        async def call_tool_side_effect(tool_name, args=None):
            if tool_name == "capture_screenshot":
                return {"success": False}
            return {"success": True}

        mock_client.call_tool = AsyncMock(side_effect=call_tool_side_effect)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.get_chart_image("AAPL", "1d")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_chart_image_from_file(self) -> None:
        """get_chart_image reads from file path when no base64 data."""
        adapter, mock_client = self._adapter_with_mock_client()
        png_data = b"\x89PNG\r\n\x1a\nfile_image_data"

        async def call_tool_side_effect(tool_name, args=None):
            if tool_name == "capture_screenshot":
                return {"success": True, "path": "/tmp/screenshot.png"}
            return {"success": True}

        mock_client.call_tool = AsyncMock(side_effect=call_tool_side_effect)

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=png_data)))
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("os.path.exists", return_value=True), \
             patch("builtins.open", return_value=mock_file):
            result = await adapter.get_chart_image("AAPL", "1d")

        assert result == png_data

    # -- health_check --

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        """health_check returns True when server reports healthy."""
        adapter, mock_client = self._adapter_with_mock_client()
        mock_client.call_tool = AsyncMock(return_value={"success": True})

        result = await adapter.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        """health_check returns False when server reports unhealthy."""
        adapter, mock_client = self._adapter_with_mock_client()
        mock_client.call_tool = AsyncMock(return_value={"success": False})

        result = await adapter.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self) -> None:
        """health_check returns False on exception."""
        adapter = self._make_adapter()
        # No client set, auto_start=False -> RuntimeError caught
        result = await adapter.health_check()
        assert result is False

    # -- screen --

    @pytest.mark.asyncio
    async def test_screen_success(self) -> None:
        """screen returns search results."""
        adapter, mock_client = self._adapter_with_mock_client()
        mock_client.call_tool = AsyncMock(return_value={
            "success": True,
            "data": [
                {"symbol": "AAPL", "name": "Apple Inc."},
                {"symbol": "AMZN", "name": "Amazon.com Inc."},
            ],
        })

        results = await adapter.screen({"query": "tech", "type": "stock"})

        assert len(results) == 2
        assert results[0]["symbol"] == "AAPL"
        assert results[1]["symbol"] == "AMZN"

    @pytest.mark.asyncio
    async def test_screen_failure(self) -> None:
        """screen returns empty list on failure."""
        adapter, mock_client = self._adapter_with_mock_client()
        mock_client.call_tool = AsyncMock(return_value={"success": False})

        results = await adapter.screen({"query": "xyz"})
        assert results == []

    @pytest.mark.asyncio
    async def test_screen_no_criteria(self) -> None:
        """screen works with no criteria."""
        adapter, mock_client = self._adapter_with_mock_client()
        mock_client.call_tool = AsyncMock(return_value={
            "success": True,
            "data": [],
        })

        results = await adapter.screen()
        assert results == []

    # -- initialization --

    def test_default_config(self) -> None:
        """Adapter initializes with default config."""
        adapter = TradingViewMCPAdapter()
        assert adapter._auto_start is True
        assert "tradingview-mcp" in adapter._server_path
        assert adapter._client is None

    def test_custom_server_path(self) -> None:
        """Adapter uses custom server path."""
        adapter = TradingViewMCPAdapter({"server_path": "/custom/path"})
        assert adapter._server_path == "/custom/path"

    def test_auto_start_false(self) -> None:
        """Adapter respects auto_start=False."""
        adapter = TradingViewMCPAdapter({"auto_start": False})
        assert adapter._auto_start is False

    @pytest.mark.asyncio
    async def test_ensure_client_raises_when_auto_start_false(self) -> None:
        """_ensure_client raises RuntimeError when auto_start is False and no client."""
        adapter = self._make_adapter()
        with pytest.raises(RuntimeError, match="auto_start=False"):
            await adapter._ensure_client()
