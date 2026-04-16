"""Paper trading orchestrator — wires data → agents → risk → execution.

This is the single module that turns the test-only collection of components
into a running pipeline.  It is intentionally thin: every step delegates to
existing implementations.

Responsibilities
----------------
* Bootstrap the data provider, paper broker, agents, aggregator, risk
  engine, and execution engine from a :class:`NexusTradeConfig`.
* On each tick, for each configured symbol:
    1. Fetch quote + recent OHLCV bars.
    2. Build a :class:`MarketContext`.
    3. Run all enabled agents through :class:`AgentExecutor`.
    4. Aggregate signals into a :class:`CompositeSignal`.
    5. Skip if HOLD; otherwise build an :class:`Order`.
    6. Run :class:`RiskEngine.assess` — if rejected, skip and record.
    7. Apply the risk-engine's position size to the order.
    8. Execute via :class:`ExecutionEngine` (paper backend).
    9. Update :class:`RuntimeState`.
* Honor pause / kill-switch flags between ticks.
* Emit alerts for fills, blocks, and circuit-breaker activations.

The loop is async; users can call :meth:`tick_once` from FastAPI to fire a
single iteration on demand, or :meth:`run` to spin a periodic background
loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from nexustrade.agents.aggregator import SignalAggregator
from nexustrade.agents.executor import AgentExecutor
from nexustrade.agents.prompt_loader import PromptLoader
from nexustrade.core.config import NexusTradeConfig
from nexustrade.core.interfaces import (
    AgentInterface,
    BrokerBackendInterface,
    DataProviderInterface,
)
from nexustrade.core.models import (
    OHLCV,
    AgentSignal,
    CompositeSignal,
    MarketContext,
    Order,
    OrderSide,
    OrderType,
    PortfolioState,
    Position,
    SignalDirection,
)
from nexustrade.execution.backends.paper import PaperBackend
from nexustrade.execution.engine import ExecutionEngine
from nexustrade.llm.router import LLMRouter
from nexustrade.risk.circuit_breaker import CircuitBreaker
from nexustrade.risk.engine import RiskEngine
from nexustrade.runtime.alerts import AlertDispatcher
from nexustrade.runtime.state import RuntimeState, TickSummary, get_runtime_state

logger = logging.getLogger(__name__)


_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def _interval_to_seconds(interval: str) -> int:
    return _INTERVAL_SECONDS.get(interval, 3600)


class PaperTradingLoop:
    """Asynchronous paper-trading orchestrator."""

    def __init__(
        self,
        config: NexusTradeConfig,
        config_path: str = "(in-memory)",
        state: RuntimeState | None = None,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.state = state or get_runtime_state()

        # Wire components
        self.data_provider: DataProviderInterface = self._build_data_provider()
        self.broker: BrokerBackendInterface = self._build_broker()
        self.executor = AgentExecutor(mode=config.agents.execution_mode)
        self.aggregator = SignalAggregator(
            mode=config.agents.aggregation_mode,
            min_confidence=config.agents.min_confidence,
        )
        self.risk_engine = self._build_risk_engine()
        self.execution_engine = ExecutionEngine(
            mode=config.execution.mode,
            brokers={self.broker.name: self.broker},
            market_broker_map={
                m: self.broker.name for m in self._market_names()
            },
        )

        # Agent factory (LLM + persona templates)
        self.llm_router = LLMRouter(config.llm)
        self.prompt_loader = PromptLoader()
        self.agents: list[AgentInterface] = self._build_agents()
        self.state.set_agents([
            {
                "name": a.name,
                "type": a.agent_type,
                "capabilities": a.get_capabilities(),
                "enabled": True,
            }
            for a in self.agents
        ])

        # Alerts
        self.alerts = AlertDispatcher.from_config(self.state, config.notifications)

        # Tracking
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self.tick_seconds = _interval_to_seconds(config.scheduler.analysis_interval)

        # Initial state snapshot
        snapshot = config.model_dump(mode="json")
        self.state.start(config_path, snapshot)
        self.state.set_risk_status({
            "circuit_breaker_active": False,
            "circuit_breaker_reason": None,
            "consecutive_losses": 0,
            "daily_loss_pct": 0.0,
            "max_daily_loss_pct": config.risk.circuit_breaker.max_daily_loss_pct,
        })

    # ------------------------------------------------------------------
    # builders
    # ------------------------------------------------------------------

    def _market_names(self) -> list[str]:
        return list(self.config.markets.keys()) or ["us_equity"]

    def _build_data_provider(self) -> DataProviderInterface:
        """Pick the first configured provider; fall back to Yahoo."""
        # Try to honor data.providers in order; default to Yahoo.
        for entry in self.config.data.providers:
            if not entry.enabled:
                continue
            try:
                return _instantiate_data_provider(entry.name, entry.config)
            except Exception:
                logger.exception("Failed to build data provider %r", entry.name)
        # Fallback
        from nexustrade.data.adapters.yahoo import YahooFinanceAdapter
        return YahooFinanceAdapter({})

    def _build_broker(self) -> BrokerBackendInterface:
        """Default to PaperBackend; honor first enabled paper broker if specified."""
        for entry in self.config.execution.brokers:
            if not entry.enabled:
                continue
            if entry.name in {"paper", "paper_broker"}:
                cfg = entry.config or {}
                return PaperBackend(
                    initial_cash=float(cfg.get("initial_cash", 100_000.0)),
                    slippage_pct=float(cfg.get("slippage_pct", 0.001)),
                    commission_pct=float(cfg.get("commission_pct", 0.0005)),
                )
        return PaperBackend()

    def _build_risk_engine(self) -> RiskEngine:
        cfg = {
            "max_daily_loss_pct": self.config.risk.circuit_breaker.max_daily_loss_pct,
            "max_consecutive_losses": self.config.risk.circuit_breaker.max_consecutive_losses,
            "max_open_positions": self.config.risk.circuit_breaker.max_open_positions,
            "cooldown_minutes": self.config.risk.circuit_breaker.cooldown_minutes,
            "max_position_pct": self.config.risk.max_position_pct,
            "risk_pct": self.config.risk.max_position_pct / 5.0,  # 1/5 of cap
            "atr_stop_multiple": 2.0,
            "atr_tp_multiple": 3.0,
        }
        cb = CircuitBreaker(cfg)
        return RiskEngine(circuit_breaker=cb, config=cfg)

    def _build_agents(self) -> list[AgentInterface]:
        """Instantiate agents that have a real implementation in the demo path.

        For the demo we ship persona agents (which require prompt templates)
        plus a deterministic baseline so a tick always emits at least one
        signal, even with no LLM keys configured.
        """
        from nexustrade.agents.adapters.ai_hedge_fund import AIHedgeFundAgentGroup

        enabled_names = [
            a.name for a in self.config.agents.enabled if a.enabled
        ]
        # Filter to ai_hedge_fund persona names known to have templates
        group = AIHedgeFundAgentGroup(self.prompt_loader, self.llm_router)
        persona_agents = group.create_agents(enabled_names=enabled_names or None)

        agents: list[AgentInterface] = list(persona_agents)
        # Always include a deterministic momentum baseline so demo works
        # even when no LLM key is configured.
        agents.append(_MomentumBaselineAgent())
        return agents

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Spin up the periodic background tick loop."""
        if self.is_running:
            logger.warning("PaperTradingLoop already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="paper_loop")
        self.state.record_audit("system", "info", "Paper trading loop started")

    async def stop(self) -> None:
        """Stop the loop gracefully."""
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None
        self.state.stop()

    async def _run(self) -> None:
        """Periodic tick loop until stop_event fires."""
        try:
            while not self._stop_event.is_set():
                if self.state.kill_switch_engaged or self.state.is_paused:
                    await asyncio.sleep(1)
                    continue
                try:
                    await self.tick_once()
                except Exception as exc:  # never let the loop die
                    logger.exception("Tick failed: %s", exc)
                    self.state.record_audit("error", "error", f"Tick failed: {exc}")

                # Schedule next tick
                self.state.next_tick_at = (
                    datetime.now(UTC) + timedelta(seconds=self.tick_seconds)
                ).isoformat()
                # Sleep with early-wake on stop
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.tick_seconds)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.state.is_running = False

    async def tick_once(self) -> TickSummary:
        """Run one full tick across all configured symbols. Returns the summary."""
        correlation_id = uuid.uuid4().hex[:8]
        symbols = self._all_symbols()
        signals_emitted = 0
        composite_count = 0
        orders_placed = 0
        orders_blocked = 0
        error: str | None = None

        t0 = perf_counter()
        try:
            # Refresh portfolio snapshot from the broker first.
            await self._refresh_portfolio_snapshot()

            for symbol, market in symbols:
                try:
                    composite = await self._run_symbol(symbol, market, correlation_id)
                    if composite is not None:
                        composite_count += 1
                        signals_emitted += len(composite.contributing_signals)
                        if composite.direction in (SignalDirection.HOLD,):
                            continue
                        placed = await self._maybe_execute(composite, market, correlation_id)
                        if placed:
                            orders_placed += 1
                        else:
                            orders_blocked += 1
                except Exception as exc:
                    logger.exception("Symbol %s failed in tick %s", symbol, correlation_id)
                    self.state.record_audit(
                        "error", "error",
                        f"Symbol {symbol} failed: {exc}",
                        metadata={"correlation_id": correlation_id},
                    )
            # Refresh snapshot at the end as well so positions reflect fills.
            await self._refresh_portfolio_snapshot()
        except Exception as exc:
            error = str(exc)
            logger.exception("Tick %s failed", correlation_id)
        finally:
            elapsed_ms = (perf_counter() - t0) * 1000.0
            summary = TickSummary(
                timestamp=datetime.now(UTC).isoformat(),
                correlation_id=correlation_id,
                symbols=[s for s, _ in symbols],
                signals_emitted=signals_emitted,
                composite_signals=composite_count,
                orders_placed=orders_placed,
                orders_blocked=orders_blocked,
                duration_ms=elapsed_ms,
                error=error,
            )
            self.state.record_tick(summary)

        return summary

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _all_symbols(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for market_name, market_cfg in self.config.markets.items():
            for sym in market_cfg.symbols:
                out.append((sym, market_name))
        return out

    async def _refresh_portfolio_snapshot(self) -> None:
        try:
            account = await self.broker.get_account()
            self.state.update_account(account)
            positions = await self.broker.get_positions()
            self.state.update_positions(positions)
            # Open orders are tracked by paper backend via _pending_orders;
            # simply expose an empty list when broker does not surface them.
            self.state.update_open_orders([])
        except Exception:
            logger.exception("Failed to refresh portfolio snapshot")

    async def _run_symbol(
        self, symbol: str, market: str, correlation_id: str
    ) -> CompositeSignal | None:
        """Build a context, run agents, and aggregate."""
        # Fetch quote + recent bars
        try:
            quote = await self.data_provider.get_quote(symbol)
        except Exception:
            logger.exception("Quote fetch failed for %s", symbol)
            return None

        if not quote or quote.last <= 0:
            self.state.record_audit(
                "tick", "warn",
                f"No price for {symbol} from {self.data_provider.name}",
                metadata={"correlation_id": correlation_id},
            )
            return None

        self.state.update_quote(symbol, quote.to_dict())

        # OHLCV bars (last 100 bars at the first configured timeframe)
        timeframe = (
            self.config.scheduler.timeframes[0]
            if self.config.scheduler.timeframes
            else "1d"
        )
        end = datetime.now(UTC)
        start = end - timedelta(days=180)
        try:
            bars = await self.data_provider.get_ohlcv(symbol, timeframe, start, end)
        except Exception:
            logger.exception("OHLCV fetch failed for %s", symbol)
            bars = []

        # Build PortfolioState dataclass from broker snapshot
        positions = await self.broker.get_positions()
        account = await self.broker.get_account()
        portfolio = PortfolioState(
            cash=float(account.get("cash", 0.0)),
            positions=positions,
            total_value=float(account.get("total_value", 0.0)),
            daily_pnl=float(account.get("daily_pnl", 0.0)),
            total_pnl=float(account.get("total_pnl", 0.0)),
            open_orders=[],
        )

        context = MarketContext(
            symbol=symbol,
            current_price=quote.last,
            ohlcv={timeframe: bars},
            technicals={},
            news=[],
            fundamentals={},
            sentiment_scores=[],
            factor_signals={},
            recent_signals=[],
            memory=[],
            portfolio=portfolio,
            config={"market": market},
        )

        # Run agents
        signals = await self.executor.execute(self.agents, context)
        for sig in signals:
            self.state.record_signal(sig, symbol, correlation_id=correlation_id)

        if not signals:
            return None

        composite = self.aggregator.aggregate(signals, symbol)
        self.state.record_composite(composite, correlation_id=correlation_id)
        return composite

    async def _maybe_execute(
        self,
        composite: CompositeSignal,
        market: str,
        correlation_id: str,
    ) -> bool:
        """Run the risk gate; if approved, route through ExecutionEngine."""
        # Build a fresh portfolio for risk
        positions = await self.broker.get_positions()
        account = await self.broker.get_account()
        portfolio = PortfolioState(
            cash=float(account.get("cash", 0.0)),
            positions=positions,
            total_value=float(account.get("total_value", 0.0)),
            daily_pnl=float(account.get("daily_pnl", 0.0)),
            total_pnl=float(account.get("total_pnl", 0.0)),
            open_orders=[],
        )

        # Use latest quote as current_price
        quote_dict = self.state.latest_quote.get(composite.symbol, {})
        current_price = float(quote_dict.get("last") or 0.0)
        if current_price <= 0:
            self.state.record_audit(
                "risk", "warn",
                f"No price for {composite.symbol} — skipping order",
                metadata={"correlation_id": correlation_id},
            )
            return False

        market_data: dict[str, Any] = {
            "current_price": current_price,
            "atr": current_price * 0.02,
        }

        assessment = await self.risk_engine.assess(
            composite, portfolio, market_data
        )
        self.state.record_risk(assessment, correlation_id=correlation_id)

        # Update circuit breaker state on dashboard
        cb = self.risk_engine.circuit_breaker
        self.state.set_risk_status({
            "circuit_breaker_active": cb.is_triggered,
            "circuit_breaker_reason": getattr(cb, "_trigger_reason", None),
            "consecutive_losses": cb._consecutive_losses,
            "daily_loss_pct": (
                abs(min(0.0, cb._daily_pnl)) / portfolio.total_value
                if portfolio.total_value > 0 else 0.0
            ),
            "max_daily_loss_pct": cb.max_daily_loss_pct,
        })

        if not assessment.approved or assessment.position_size <= 0:
            await self.alerts.dispatch(
                "risk_blocked",
                f"Risk blocked {composite.symbol}",
                f"{', '.join(assessment.warnings) or 'No warnings'} "
                f"(direction={composite.direction.value}, "
                f"confidence={composite.confidence:.2f})",
                level="warning",
            )
            return False

        # Build the order
        side = (
            OrderSide.BUY
            if composite.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
            else OrderSide.SELL
        )
        order = Order(
            symbol=composite.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=float(assessment.position_size),
            price=current_price,  # paper backend needs price
            stop_loss=assessment.stop_loss_price,
            take_profit=assessment.take_profit_price,
            strategy_name="paper_loop",
            metadata={
                "correlation_id": correlation_id,
                "composite_direction": composite.direction.value,
                "composite_confidence": composite.confidence,
            },
        )

        try:
            fill = await self.execution_engine.execute(order, market=market)
        except Exception as exc:
            self.state.record_audit(
                "error", "error",
                f"Execution failed for {order.symbol}: {exc}",
                metadata={"correlation_id": correlation_id},
            )
            await self.alerts.dispatch(
                "error", f"Execution failed: {order.symbol}", str(exc), level="error"
            )
            return False

        self.state.record_order(order, order_id=fill.order_id, broker=fill.broker, correlation_id=correlation_id)
        self.state.record_fill(fill, correlation_id=correlation_id)
        await self.alerts.dispatch(
            "fill",
            f"{fill.side.value.upper()} {fill.symbol}",
            f"{fill.filled_qty} @ {fill.avg_price:.4f} "
            f"(fees {fill.fees:.4f}, slip {fill.slippage:.4f})",
            level="info",
        )

        # Update circuit-breaker tracking on the fill
        try:
            self.risk_engine.circuit_breaker.update(fill)
        except Exception:
            pass

        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _instantiate_data_provider(name: str, cfg: dict[str, Any]) -> DataProviderInterface:
    """Instantiate a known data provider by name."""
    if name == "yahoo":
        from nexustrade.data.adapters.yahoo import YahooFinanceAdapter
        return YahooFinanceAdapter(cfg)
    if name == "ccxt":
        from nexustrade.data.adapters.ccxt_data import CCXTDataAdapter
        return CCXTDataAdapter(cfg)
    if name == "openbb":
        from nexustrade.data.adapters.openbb_adapter import OpenBBAdapter
        return OpenBBAdapter(cfg)
    raise ValueError(f"Unknown data provider: {name}")


# ---------------------------------------------------------------------------
# Deterministic baseline agent (no LLM required)
# ---------------------------------------------------------------------------


class _MomentumBaselineAgent(AgentInterface):
    """A simple momentum baseline so the demo always emits at least one signal.

    Computes a 20-bar SMA from the OHLCV in the context. If price is above
    SMA it BUYS (low confidence), below it SELLS, otherwise HOLD. Pure
    Python — no LLM, no GPU, no external service. Useful for the
    no-credentials demo on Hugging Face Spaces.
    """

    @property
    def name(self) -> str:
        return "momentum_baseline"

    @property
    def agent_type(self) -> str:
        return "deterministic"

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "requires_vision": False,
            "requires_gpu": False,
            "requires_llm": False,
            "supported_markets": ["us_equity", "crypto", "forex", "india_equity"],
        }

    async def analyze(self, context: MarketContext) -> AgentSignal:
        bars: list[OHLCV] = []
        for tf_bars in context.ohlcv.values():
            if len(tf_bars) > len(bars):
                bars = tf_bars
        if len(bars) < 20 or context.current_price <= 0:
            return AgentSignal(
                direction=SignalDirection.HOLD,
                confidence=0.5,
                reasoning="Not enough history for momentum baseline",
                agent_name=self.name,
                agent_type=self.agent_type,
            )

        sma = sum(b.close for b in bars[-20:]) / 20.0
        spread = (context.current_price - sma) / sma

        if spread > 0.02:
            direction = SignalDirection.BUY
            conf = min(0.7, 0.55 + abs(spread))
            why = f"Price {context.current_price:.2f} is {spread:.1%} above SMA20={sma:.2f}"
        elif spread < -0.02:
            direction = SignalDirection.SELL
            conf = min(0.7, 0.55 + abs(spread))
            why = f"Price {context.current_price:.2f} is {abs(spread):.1%} below SMA20={sma:.2f}"
        else:
            direction = SignalDirection.HOLD
            conf = 0.55
            why = f"Price {context.current_price:.2f} within 2% of SMA20={sma:.2f}"

        return AgentSignal(
            direction=direction,
            confidence=conf,
            reasoning=why,
            agent_name=self.name,
            agent_type=self.agent_type,
            metadata={"sma_20": sma, "spread_pct": spread * 100},
        )


# ---------------------------------------------------------------------------
# Singleton accessor (so FastAPI can fetch the running loop)
# ---------------------------------------------------------------------------


_LOOP: PaperTradingLoop | None = None
_LOOP_LOCK = asyncio.Lock()


async def get_or_create_loop(config: NexusTradeConfig, config_path: str = "(in-memory)") -> PaperTradingLoop:
    global _LOOP
    async with _LOOP_LOCK:
        if _LOOP is None:
            _LOOP = PaperTradingLoop(config, config_path=config_path)
        return _LOOP


def get_running_loop() -> PaperTradingLoop | None:
    return _LOOP


def reset_loop() -> None:
    """Reset the singleton (tests only)."""
    global _LOOP
    _LOOP = None


# Convenience wrapper used by the dashboard's "manual order" panel.
async def submit_manual_order(
    symbol: str,
    side: str,
    quantity: float,
    price: float | None = None,
    market: str = "us_equity",
) -> dict[str, Any]:
    """Submit a one-off order via the running paper broker.

    Goes through the risk engine like any orchestrated order, but the
    composite signal is synthesised from the user's intent (BUY/SELL).
    """
    loop = get_running_loop()
    if loop is None:
        raise RuntimeError("Paper trading loop is not running. Start it first.")

    direction = (
        SignalDirection.BUY if side.lower() == "buy" else SignalDirection.SELL
    )

    # synthesise a composite for risk assessment
    quote_dict = loop.state.latest_quote.get(symbol)
    if not quote_dict and price is None:
        # Fetch a fresh quote
        quote = await loop.data_provider.get_quote(symbol)
        quote_dict = quote.to_dict()
        loop.state.update_quote(symbol, quote_dict)
    px = float(price) if price is not None else float(quote_dict.get("last") or 0.0)
    if px <= 0:
        raise ValueError("Could not determine price for order")

    composite = CompositeSignal(
        symbol=symbol,
        direction=direction,
        confidence=0.99,
        contributing_signals=[],
        aggregation_mode="manual",
        reasoning="User-submitted manual order",
        timestamp=datetime.now(UTC),
    )

    # Build order using the requested quantity directly (skip sizing model)
    correlation_id = uuid.uuid4().hex[:8]
    order = Order(
        symbol=symbol,
        side=OrderSide.BUY if direction == SignalDirection.BUY else OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=float(quantity),
        price=px,
        strategy_name="manual",
        metadata={"correlation_id": correlation_id, "manual": True},
    )

    fill = await loop.execution_engine.execute(order, market=market)
    loop.state.record_composite(composite, correlation_id=correlation_id)
    loop.state.record_order(order, order_id=fill.order_id, broker=fill.broker, correlation_id=correlation_id)
    loop.state.record_fill(fill, correlation_id=correlation_id)
    await loop._refresh_portfolio_snapshot()
    return {
        "order_id": fill.order_id,
        "symbol": fill.symbol,
        "side": fill.side.value,
        "filled_qty": fill.filled_qty,
        "avg_price": fill.avg_price,
        "fees": fill.fees,
        "slippage": fill.slippage,
        "correlation_id": correlation_id,
    }


# Re-export Position for typing convenience in the API
__all__ = [
    "PaperTradingLoop",
    "get_or_create_loop",
    "get_running_loop",
    "reset_loop",
    "submit_manual_order",
    "Position",
]
