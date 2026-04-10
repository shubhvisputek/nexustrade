"""TradingView MCP data adapter.

Connects to the TradingView MCP server (tradingview-mcp) via stdio transport
to retrieve OHLCV data, quotes, technical indicators, and chart screenshots.

The MCP server controls a live TradingView Desktop instance via Chrome DevTools Protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from typing import Any

from nexustrade.core.interfaces import DataProviderInterface
from nexustrade.core.models import OHLCV, Quote, TechnicalIndicators

logger = logging.getLogger(__name__)


class MCPStdioClient:
    """MCP client that communicates with an MCP server over stdin/stdout (JSON-RPC 2.0)."""

    def __init__(self, server_command: list[str], cwd: str | None = None):
        self._server_command = server_command
        self._cwd = cwd
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the MCP server subprocess."""
        # Launch with Popen, pipe stdin/stdout, stderr to devnull
        self._process = subprocess.Popen(
            self._server_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self._cwd,
        )
        # Send initialize request (MCP protocol handshake)
        await self._initialize()

    async def _initialize(self) -> dict[str, Any]:
        """Send MCP initialize handshake."""
        return await self.call_method("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "nexustrade", "version": "0.1.0"}
        })

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call an MCP tool and return the result content."""
        result = await self.call_method("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })
        # MCP result format: {"content": [{"type": "text", "text": "..."}]}
        if result and "content" in result:
            for item in result["content"]:
                if item.get("type") == "text":
                    try:
                        return json.loads(item["text"])
                    except json.JSONDecodeError:
                        return item["text"]
        return result

    async def call_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and read the response."""
        async with self._lock:
            if not self._process or self._process.poll() is not None:
                raise RuntimeError("MCP server not running")

            self._request_id += 1
            request = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": self._request_id,
            }

            line = json.dumps(request) + "\n"

            loop = asyncio.get_event_loop()
            # Write request
            await loop.run_in_executor(None, self._write, line)
            # Read response
            response_line = await loop.run_in_executor(None, self._readline)

            if not response_line:
                raise RuntimeError("No response from MCP server")

            response = json.loads(response_line)
            if "error" in response:
                raise RuntimeError(f"MCP error: {response['error']}")
            return response.get("result", {})

    def _write(self, data: str) -> None:
        if self._process and self._process.stdin:
            self._process.stdin.write(data.encode())
            self._process.stdin.flush()

    def _readline(self) -> str:
        if self._process and self._process.stdout:
            return self._process.stdout.readline().decode().strip()
        return ""

    async def stop(self) -> None:
        """Stop the MCP server subprocess."""
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None


class TradingViewMCPAdapter(DataProviderInterface):
    """TradingView data via MCP server (tradingview-mcp).

    Uses stdio transport to communicate with the TradingView MCP server,
    which controls a live TradingView Desktop via Chrome DevTools Protocol.

    Parameters
    ----------
    config:
        Dictionary with:
        - server_path: path to tradingview-mcp directory (default: ~/source/tradingview-mcp)
        - auto_start: whether to auto-start the MCP server (default: True)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._server_path = self._config.get(
            "server_path",
            os.path.expanduser("~/source/tradingview-mcp")
        )
        self._auto_start = self._config.get("auto_start", True)
        self._client: MCPStdioClient | None = None
        self._started = False

    async def _ensure_client(self) -> MCPStdioClient:
        """Lazily start the MCP client."""
        if self._client and self._client.is_running:
            return self._client

        if not self._auto_start:
            raise RuntimeError("TradingView MCP server not started and auto_start=False")

        self._client = MCPStdioClient(
            server_command=["node", "src/server.js"],
            cwd=self._server_path,
        )
        await self._client.start()
        self._started = True
        return self._client

    # -- properties --
    @property
    def name(self) -> str:
        return "tradingview_mcp"

    @property
    def supported_markets(self) -> list[str]:
        return ["us_equity", "india_equity", "forex", "crypto", "commodity"]

    # -- DataProviderInterface implementation --

    async def get_ohlcv(
        self, symbol: str, timeframe: str, start: datetime, end: datetime,
    ) -> list[OHLCV]:
        """Get OHLCV data from TradingView chart."""
        client = await self._ensure_client()

        # Set the chart to the requested symbol and timeframe
        await client.call_tool("chart_set_symbol", {"symbol": symbol})

        # Map NexusTrade timeframes to TV format
        tf_map = {
            "1m": "1", "5m": "5", "15m": "15",
            "1h": "60", "4h": "240", "1d": "D", "1w": "W",
        }
        tv_tf = tf_map.get(timeframe, timeframe)
        await client.call_tool("chart_set_timeframe", {"timeframe": tv_tf})

        # Wait for chart to load
        await asyncio.sleep(1)

        # Get OHLCV data (not summary -- we need individual bars)
        result = await client.call_tool("data_get_ohlcv", {"count": 500, "summary": False})

        if not result or not result.get("success", False):
            return []

        bars = []
        for bar in result.get("bars", result.get("data", [])):
            try:
                ts = datetime.fromtimestamp(bar.get("time", bar.get("timestamp", 0)), tz=UTC)
                bars.append(OHLCV(
                    timestamp=ts,
                    open=float(bar.get("open", 0)),
                    high=float(bar.get("high", 0)),
                    low=float(bar.get("low", 0)),
                    close=float(bar.get("close", 0)),
                    volume=float(bar.get("volume", 0)),
                    symbol=symbol,
                    timeframe=timeframe,
                    source="tradingview_mcp",
                ))
            except (KeyError, ValueError, TypeError) as e:
                logger.debug("Failed to parse bar: %s", e)
                continue

        # Filter by date range
        bars = [b for b in bars if start <= b.timestamp <= end]
        return bars

    async def get_quote(self, symbol: str) -> Quote:
        """Get real-time quote from TradingView."""
        client = await self._ensure_client()
        result = await client.call_tool("quote_get", {"symbol": symbol})

        if not result or not result.get("success", False):
            raise RuntimeError(f"Failed to get quote for {symbol}: {result}")

        data = result.get("data", result)
        now = datetime.now(UTC)

        return Quote(
            symbol=symbol,
            bid=float(data.get("bid", data.get("last", 0))),
            ask=float(data.get("ask", data.get("last", 0))),
            last=float(data.get("last", data.get("close", 0))),
            volume=float(data.get("volume", 0)),
            timestamp=now,
            source="tradingview_mcp",
        )

    async def get_technicals(self, symbol: str, timeframe: str) -> TechnicalIndicators | None:
        """Get technical indicator values from all visible studies on the chart."""
        client = await self._ensure_client()

        # Ensure we're on the right symbol/timeframe
        await client.call_tool("chart_set_symbol", {"symbol": symbol})
        tf_map = {
            "1m": "1", "5m": "5", "15m": "15",
            "1h": "60", "4h": "240", "1d": "D", "1w": "W",
        }
        tv_tf = tf_map.get(timeframe, timeframe)
        await client.call_tool("chart_set_timeframe", {"timeframe": tv_tf})
        await asyncio.sleep(0.5)

        result = await client.call_tool("data_get_study_values", {})
        if not result or not result.get("success", False):
            return None

        studies = result.get("studies", result.get("data", {}))
        now = datetime.now(UTC)

        # Parse known indicators from study values
        ti = TechnicalIndicators(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=now,
            source="tradingview_mcp",
        )

        # Map TV study names to our fields
        for study_name, values in (studies if isinstance(studies, dict) else {}).items():
            name_lower = study_name.lower()
            if isinstance(values, dict):
                if "rsi" in name_lower:
                    ti.rsi = values.get("RSI", values.get("value"))
                elif "macd" in name_lower:
                    ti.macd = values.get("MACD", values.get("value"))
                    ti.macd_signal = values.get("Signal")
                    ti.macd_histogram = values.get("Histogram")
                elif "bollinger" in name_lower:
                    ti.bb_upper = values.get("Upper")
                    ti.bb_middle = values.get("Basis", values.get("Middle"))
                    ti.bb_lower = values.get("Lower")
                elif "adx" in name_lower:
                    ti.adx = values.get("ADX", values.get("value"))
                elif "atr" in name_lower:
                    ti.atr = values.get("ATR", values.get("value"))
                elif "stoch" in name_lower:
                    ti.stoch_k = values.get("%K", values.get("K"))
                    ti.stoch_d = values.get("%D", values.get("D"))
            # Store ALL study values in extra for custom indicators
            ti.extra[study_name] = values

        return ti

    async def get_chart_image(self, symbol: str, timeframe: str) -> bytes | None:
        """Take a screenshot of the chart."""
        client = await self._ensure_client()

        await client.call_tool("chart_set_symbol", {"symbol": symbol})
        tf_map = {
            "1m": "1", "5m": "5", "15m": "15",
            "1h": "60", "4h": "240", "1d": "D", "1w": "W",
        }
        tv_tf = tf_map.get(timeframe, timeframe)
        await client.call_tool("chart_set_timeframe", {"timeframe": tv_tf})
        await asyncio.sleep(1)

        result = await client.call_tool("capture_screenshot", {"region": "chart"})
        if not result or not result.get("success", False):
            return None

        # The screenshot result may include base64 data or file path
        import base64
        b64 = result.get("data", result.get("base64", ""))
        if b64:
            return base64.b64decode(b64)

        # If file path returned, read the file
        filepath = result.get("path", result.get("file", ""))
        if filepath and os.path.exists(filepath):
            with open(filepath, "rb") as f:
                return f.read()

        return None

    async def screen(self, criteria: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Search for symbols using TradingView."""
        client = await self._ensure_client()
        query = (criteria or {}).get("query", "")
        sym_type = (criteria or {}).get("type")

        result = await client.call_tool("symbol_search", {
            "query": query,
            **({"type": sym_type} if sym_type else {}),
        })

        if not result or not result.get("success", False):
            return []
        return result.get("data", result.get("results", []))

    async def health_check(self) -> bool:
        """Check if TradingView MCP server and TradingView Desktop are running."""
        try:
            client = await self._ensure_client()
            result = await client.call_tool("tv_health_check", {})
            return bool(result and result.get("success", False))
        except Exception:
            return False
