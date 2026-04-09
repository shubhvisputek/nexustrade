"""NexusTrade abstract interfaces.

All adapters (data providers, brokers, agents, notifications, risk models,
strategies) implement one of these ABCs.  Concrete classes only need to
override the abstract methods; optional methods have sensible defaults.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from nexustrade.core.models import (
    OHLCV,
    AgentSignal,
    CompositeSignal,
    Fill,
    MarketContext,
    NewsItem,
    Order,
    PortfolioState,
    Position,
    Quote,
    RiskAssessment,
    TechnicalIndicators,
)


# ---------------------------------------------------------------------------
# 3.1  Data Provider
# ---------------------------------------------------------------------------

class DataProviderInterface(ABC):
    """Unified interface for all market-data sources.

    Concrete implementations wrap a single upstream (OpenBB, CCXT, Yahoo,
    TradingView MCP, broker feeds, etc.) and convert everything into
    canonical NexusTrade data models.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g. ``'openbb'``, ``'ccxt'``)."""

    @property
    @abstractmethod
    def supported_markets(self) -> list[str]:
        """Markets this provider can serve (e.g. ``['us_equity', 'crypto']``)."""

    # -- required ---------------------------------------------------------

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCV]:
        """Return OHLCV bars for *symbol* between *start* and *end*.

        Parameters
        ----------
        symbol:
            Ticker / pair (e.g. ``"AAPL"``, ``"BTC/USDT"``).
        timeframe:
            Bar size – one of ``"1m","5m","15m","1h","4h","1d","1w","1M"``.
        start, end:
            UTC-aware datetimes bounding the query.

        Returns
        -------
        list[OHLCV]
            Bars in chronological order.
        """

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Return the latest quote (bid/ask/last) for *symbol*."""

    # -- optional (sensible defaults) -------------------------------------

    async def get_news(
        self,
        symbol: str,
        limit: int = 10,
    ) -> list[NewsItem]:
        """Return recent news items for *symbol*.  Default: empty list."""
        return []

    async def get_fundamentals(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """Return fundamental data for *symbol*.  Default: empty dict."""
        return {}

    async def get_technicals(
        self,
        symbol: str,
        timeframe: str,
    ) -> TechnicalIndicators | None:
        """Return pre-computed technical indicators.  Default: ``None``."""
        return None

    async def get_chart_image(
        self,
        symbol: str,
        timeframe: str,
    ) -> bytes | None:
        """Return a chart screenshot as PNG bytes.  Default: ``None``."""
        return None

    async def screen(
        self,
        criteria: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a stock/crypto screener.  Default: empty list."""
        return []

    async def stream(
        self,
        symbols: list[str],
    ) -> AsyncIterator[Quote]:
        """Yield real-time quotes.  Default: raises ``NotImplementedError``."""
        raise NotImplementedError(
            f"{self.name} does not support streaming"
        )
        # AsyncIterator requires `yield` to make this an async generator
        # in subclasses, but the base raises before yielding.
        yield  # type: ignore[misc]  # pragma: no cover – unreachable

    async def health_check(self) -> bool:
        """Return ``True`` if the upstream is reachable.  Default: ``True``."""
        return True


# ---------------------------------------------------------------------------
# 3.2  Broker Backend
# ---------------------------------------------------------------------------

class BrokerBackendInterface(ABC):
    """Unified interface for order execution across all brokers.

    Concrete implementations wrap Alpaca, OpenAlgo (Zerodha/Dhan/…),
    CCXT exchanges, or a local paper-trading engine.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Broker name (e.g. ``'alpaca'``, ``'openalgo_zerodha'``)."""

    @property
    @abstractmethod
    def supported_markets(self) -> list[str]:
        """Markets this broker supports."""

    @property
    @abstractmethod
    def is_paper(self) -> bool:
        """``True`` when connected in paper/sandbox mode."""

    # -- required ---------------------------------------------------------

    @abstractmethod
    async def place_order(self, order: Order) -> Fill:
        """Submit *order* and return the resulting :class:`Fill`.

        Raises
        ------
        RuntimeError
            If the order is rejected by the broker.
        """

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Return ``True`` on success."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Return all open positions."""

    @abstractmethod
    async def get_account(self) -> dict[str, Any]:
        """Return account summary (cash, equity, margin, etc.)."""

    # -- optional ---------------------------------------------------------

    async def modify_order(
        self,
        order_id: str,
        updates: dict[str, Any],
    ) -> bool:
        """Modify a live order.  Default: raises ``NotImplementedError``."""
        raise NotImplementedError(
            f"{self.name} does not support order modification"
        )

    async def get_order_history(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent order history.  Default: empty list."""
        return []

    async def health_check(self) -> bool:
        """Return ``True`` if the broker API is reachable.  Default: ``True``."""
        return True


# ---------------------------------------------------------------------------
# 3.3  Agent
# ---------------------------------------------------------------------------

class AgentInterface(ABC):
    """Single analysis agent (persona, debate, RL, sentiment, vision, …).

    Each agent receives a :class:`MarketContext` and emits a single
    :class:`AgentSignal` with a direction, confidence, and reasoning.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name (e.g. ``'warren_buffett'``, ``'momentum_rl'``)."""

    @property
    def agent_type(self) -> str:
        """Agent category.  Default: ``'generic'``."""
        return "generic"

    # -- required ---------------------------------------------------------

    @abstractmethod
    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Produce a trading signal from the given *context*.

        The agent should populate ``AgentSignal.reasoning`` with a
        human-readable explanation of its logic.
        """

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        """Describe what this agent can do.

        Returns
        -------
        dict
            Keys may include ``'markets'``, ``'timeframes'``,
            ``'requires_vision'``, ``'requires_llm'``, etc.
        """


# ---------------------------------------------------------------------------
# 3.4  Notification Adapter
# ---------------------------------------------------------------------------

class NotificationAdapter(ABC):
    """Push notifications to an external channel (Telegram, Discord, …)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel name (e.g. ``'telegram'``, ``'discord'``)."""

    # -- required ---------------------------------------------------------

    @abstractmethod
    async def send(
        self,
        title: str,
        message: str,
        level: str = "info",
    ) -> bool:
        """Send a notification.  Return ``True`` on success.

        Parameters
        ----------
        title:
            Short headline.
        message:
            Full message body (may contain markdown).
        level:
            One of ``'info'``, ``'warning'``, ``'error'``, ``'critical'``.
        """

    # -- convenience (default implementations) ----------------------------

    async def send_trade_alert(self, fill: Fill) -> bool:
        """Format and send a trade-execution alert.

        Default implementation delegates to :meth:`send`.
        """
        title = f"Trade Executed: {fill.symbol}"
        message = (
            f"**{fill.side.value.upper()}** {fill.filled_qty} "
            f"{fill.symbol} @ {fill.avg_price:.4f}\n"
            f"Broker: {fill.broker} | Status: {fill.status.value}"
        )
        return await self.send(title, message, level="info")

    async def send_circuit_breaker(
        self,
        reason: str,
        resume_at: datetime | None = None,
    ) -> bool:
        """Notify that a circuit breaker has been triggered.

        Default implementation delegates to :meth:`send`.
        """
        title = "Circuit Breaker Activated"
        resume_info = (
            f"\nResumes at: {resume_at.isoformat()}" if resume_at else ""
        )
        message = f"**Reason:** {reason}{resume_info}"
        return await self.send(title, message, level="critical")


# ---------------------------------------------------------------------------
# 3.5  Risk Model
# ---------------------------------------------------------------------------

class RiskModelInterface(ABC):
    """Position-sizing and risk-assessment model.

    Given the current portfolio, a composite signal, and recent market
    data, produce a :class:`RiskAssessment` that tells the execution
    engine how big to make the trade (or whether to block it entirely).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Model name (e.g. ``'kelly'``, ``'fixed_fractional'``)."""

    @abstractmethod
    async def calculate_position_size(
        self,
        portfolio: PortfolioState,
        signal: CompositeSignal,
        market_data: dict[str, Any],
        config: dict[str, Any],
    ) -> RiskAssessment:
        """Compute position size and risk parameters.

        Parameters
        ----------
        portfolio:
            Current portfolio state (cash, positions, P&L).
        signal:
            Aggregated signal from the agent ensemble.
        market_data:
            Recent OHLCV / quote data the model may need for volatility
            calculations.
        config:
            Risk-specific configuration (max position %, max loss, etc.).

        Returns
        -------
        RiskAssessment
            Contains ``approved``, ``position_size``, ``stop_loss_price``,
            ``take_profit_price``, and optional warnings.
        """


# ---------------------------------------------------------------------------
# 3.6  Strategy
# ---------------------------------------------------------------------------

class StrategyInterface(ABC):
    """High-level entry/exit logic that wraps agent signals and risk checks.

    A strategy decides *whether* to enter or exit, while risk models
    decide *how much*.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name (e.g. ``'momentum_breakout'``)."""

    @abstractmethod
    async def evaluate_entry(
        self,
        context: MarketContext,
        signals: list[AgentSignal],
    ) -> bool:
        """Return ``True`` if the strategy wants to open a new position.

        Parameters
        ----------
        context:
            Full market context for the symbol.
        signals:
            Current agent signals.
        """

    @abstractmethod
    async def evaluate_exit(
        self,
        context: MarketContext,
        signals: list[AgentSignal],
        position: Position,
    ) -> bool:
        """Return ``True`` if the strategy wants to close *position*.

        Parameters
        ----------
        context:
            Full market context.
        signals:
            Current agent signals.
        position:
            The open position being evaluated.
        """
