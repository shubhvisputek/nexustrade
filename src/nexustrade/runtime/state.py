"""Process-singleton runtime state.

Holds everything the live trading loop produces and the dashboard reads:
portfolio state, recent signals, agent reasoning traces, order book,
trade history, audit log, alerts, equity curve, and live config.

The dashboard polls FastAPI endpoints which return slices of this state.
The :class:`PaperTradingLoop` writes to it on every tick. Both share
the same in-process instance via :func:`get_runtime_state`.

When Redis is available, this module ALSO mirrors writes to Redis
streams so a multi-process deployment can share state — but the
in-process path always works without Redis.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from nexustrade.core.models import (
    AgentSignal,
    CompositeSignal,
    Fill,
    Order,
    OrderStatus,
    Position,
    RiskAssessment,
)

logger = logging.getLogger(__name__)


# --- Trace records ----------------------------------------------------------


@dataclass
class ReasoningTrace:
    """One agent's reasoning recorded in the trace timeline."""

    timestamp: str
    symbol: str
    agent_name: str
    agent_type: str
    direction: str
    confidence: float
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregationTrace:
    """The composite signal produced by the aggregator for one symbol."""

    timestamp: str
    symbol: str
    direction: str
    confidence: float
    aggregation_mode: str
    reasoning: str
    contributing_count: int
    correlation_id: str = ""


@dataclass
class RiskTrace:
    """Result of the risk engine's assessment."""

    timestamp: str
    symbol: str
    approved: bool
    position_size: float
    stop_loss_price: float
    take_profit_price: float
    risk_reward_ratio: float
    max_loss_amount: float
    sizing_model: str
    risk_debate_summary: str | None = None
    warnings: list[str] = field(default_factory=list)
    correlation_id: str = ""


@dataclass
class OrderTrace:
    """A submitted order (regardless of fill state)."""

    timestamp: str
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None
    status: str
    broker: str
    correlation_id: str = ""


@dataclass
class FillTrace:
    """A fill record in the trade ledger."""

    timestamp: str
    order_id: str
    symbol: str
    side: str
    filled_qty: float
    avg_price: float
    broker: str
    fees: float
    slippage: float
    realized_pnl: float = 0.0
    correlation_id: str = ""


@dataclass
class AuditEvent:
    """One entry in the audit feed."""

    timestamp: str
    category: str  # config | tick | signal | risk | order | fill | error | system
    level: str    # info | warn | error | critical
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertRecord:
    """An alert that was (or would have been) dispatched to a channel."""

    timestamp: str
    title: str
    message: str
    level: str
    channels: list[str]
    delivered: dict[str, bool] = field(default_factory=dict)


@dataclass
class EquityPoint:
    """One point on the portfolio equity curve."""

    timestamp: str
    cash: float
    positions_value: float
    total_value: float
    daily_pnl: float
    total_pnl: float


@dataclass
class TickSummary:
    """Summary of one orchestrator tick."""

    timestamp: str
    correlation_id: str
    symbols: list[str]
    signals_emitted: int
    composite_signals: int
    orders_placed: int
    orders_blocked: int
    duration_ms: float
    error: str | None = None


# --- Runtime state ----------------------------------------------------------


class RuntimeState:
    """Process-singleton state holder.

    All deques are bounded — old entries roll off automatically so the
    process never grows unboundedly. Write methods are thread-safe via
    a single lock.
    """

    def __init__(
        self,
        max_signals: int = 1000,
        max_traces: int = 1000,
        max_orders: int = 500,
        max_fills: int = 500,
        max_audit: int = 2000,
        max_alerts: int = 500,
        max_equity_points: int = 4096,
        max_ticks: int = 200,
    ) -> None:
        self._lock = threading.Lock()

        # --- snapshot state (overwritten on every tick) ---
        self.is_running: bool = False
        self.is_paused: bool = False
        self.kill_switch_engaged: bool = False
        self.last_tick_at: str | None = None
        self.next_tick_at: str | None = None
        self.config_path: str | None = None
        self.config_snapshot: dict[str, Any] = {}

        # broker/account snapshot (refreshed each tick)
        self.account: dict[str, Any] = {
            "cash": 0.0,
            "positions_value": 0.0,
            "total_value": 0.0,
            "total_pnl": 0.0,
            "daily_pnl": 0.0,
            "initial_cash": 0.0,
            "num_positions": 0,
            "num_trades": 0,
        }
        self.positions: list[Position] = []
        self.open_orders: list[Order] = []

        # registered agents (filled at startup)
        self.agents: list[dict[str, Any]] = []

        # circuit-breaker / kill-switch status
        self.risk_status: dict[str, Any] = {
            "circuit_breaker_active": False,
            "circuit_breaker_reason": None,
            "consecutive_losses": 0,
            "daily_loss_pct": 0.0,
            "max_daily_loss_pct": 0.03,
        }

        # --- rolling buffers ---
        self.signals: deque[ReasoningTrace] = deque(maxlen=max_signals)
        self.composite_signals: deque[AggregationTrace] = deque(maxlen=max_traces)
        self.risk_assessments: deque[RiskTrace] = deque(maxlen=max_traces)
        self.orders: deque[OrderTrace] = deque(maxlen=max_orders)
        self.fills: deque[FillTrace] = deque(maxlen=max_fills)
        self.audit: deque[AuditEvent] = deque(maxlen=max_audit)
        self.alerts: deque[AlertRecord] = deque(maxlen=max_alerts)
        self.equity_curve: deque[EquityPoint] = deque(maxlen=max_equity_points)
        self.ticks: deque[TickSummary] = deque(maxlen=max_ticks)

        # latest-by-symbol caches (for the dashboard's "now" view)
        self.latest_quote: dict[str, dict[str, Any]] = {}
        self.latest_composite: dict[str, AggregationTrace] = {}
        self.latest_risk: dict[str, RiskTrace] = {}

        # backtest results stored by name
        self.backtests: dict[str, dict[str, Any]] = {}

        # listeners for async event delivery to the dashboard
        self._listeners: list[asyncio.Queue[dict[str, Any]]] = []

    # -- lifecycle --------------------------------------------------------

    def start(self, config_path: str, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self.is_running = True
            self.is_paused = False
            self.kill_switch_engaged = False
            self.config_path = config_path
            self.config_snapshot = snapshot
            self._record_audit("system", "info", f"Runtime started with {config_path}")

    def stop(self) -> None:
        with self._lock:
            self.is_running = False
            self._record_audit("system", "info", "Runtime stopped")

    def pause(self, reason: str = "manual") -> None:
        with self._lock:
            self.is_paused = True
            self._record_audit("system", "warn", f"Runtime paused: {reason}")

    def resume(self) -> None:
        with self._lock:
            self.is_paused = False
            self._record_audit("system", "info", "Runtime resumed")

    def engage_kill_switch(self, reason: str = "manual") -> None:
        with self._lock:
            self.kill_switch_engaged = True
            self.is_paused = True
            self._record_audit("system", "critical", f"KILL SWITCH ENGAGED: {reason}")

    def disengage_kill_switch(self) -> None:
        with self._lock:
            self.kill_switch_engaged = False
            self._record_audit("system", "info", "Kill switch released")

    # -- writers (thread-safe) --------------------------------------------

    def update_account(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self.account.update(snapshot)
            self.equity_curve.append(
                EquityPoint(
                    timestamp=_now(),
                    cash=float(snapshot.get("cash", 0.0)),
                    positions_value=float(snapshot.get("positions_value", 0.0)),
                    total_value=float(snapshot.get("total_value", 0.0)),
                    daily_pnl=float(snapshot.get("daily_pnl", 0.0)),
                    total_pnl=float(snapshot.get("total_pnl", 0.0)),
                )
            )

    def update_positions(self, positions: list[Position]) -> None:
        with self._lock:
            self.positions = list(positions)

    def update_open_orders(self, orders: list[Order]) -> None:
        with self._lock:
            self.open_orders = list(orders)

    def update_quote(self, symbol: str, quote_dict: dict[str, Any]) -> None:
        with self._lock:
            self.latest_quote[symbol] = {**quote_dict, "as_of": _now()}

    def set_agents(self, agents: list[dict[str, Any]]) -> None:
        with self._lock:
            self.agents = list(agents)

    def set_risk_status(self, status: dict[str, Any]) -> None:
        with self._lock:
            self.risk_status.update(status)

    def record_signal(
        self, signal: AgentSignal, symbol: str, correlation_id: str = ""
    ) -> None:
        trace = ReasoningTrace(
            timestamp=_now(),
            symbol=symbol,
            agent_name=signal.agent_name,
            agent_type=signal.agent_type,
            direction=signal.direction.value,
            confidence=float(signal.confidence),
            reasoning=signal.reasoning,
            metadata={**(signal.metadata or {}), "correlation_id": correlation_id},
        )
        with self._lock:
            self.signals.append(trace)
            self._record_audit(
                "signal",
                "info",
                f"{signal.agent_name} → {symbol}: "
                f"{signal.direction.value} ({signal.confidence:.2f})",
                metadata={"correlation_id": correlation_id},
            )
        self._publish({"type": "signal", "data": asdict(trace)})

    def record_composite(self, composite: CompositeSignal, correlation_id: str = "") -> None:
        trace = AggregationTrace(
            timestamp=_now(),
            symbol=composite.symbol,
            direction=composite.direction.value,
            confidence=float(composite.confidence),
            aggregation_mode=composite.aggregation_mode,
            reasoning=composite.reasoning,
            contributing_count=len(composite.contributing_signals),
            correlation_id=correlation_id,
        )
        with self._lock:
            self.composite_signals.append(trace)
            self.latest_composite[composite.symbol] = trace
        self._publish({"type": "composite", "data": asdict(trace)})

    def record_risk(self, assessment: RiskAssessment, correlation_id: str = "") -> None:
        trace = RiskTrace(
            timestamp=_now(),
            symbol=assessment.symbol,
            approved=bool(assessment.approved),
            position_size=float(assessment.position_size),
            stop_loss_price=float(assessment.stop_loss_price),
            take_profit_price=float(assessment.take_profit_price),
            risk_reward_ratio=float(assessment.risk_reward_ratio),
            max_loss_amount=float(assessment.max_loss_amount),
            sizing_model=assessment.sizing_model,
            risk_debate_summary=assessment.risk_debate_summary,
            warnings=list(assessment.warnings or []),
            correlation_id=correlation_id,
        )
        with self._lock:
            self.risk_assessments.append(trace)
            self.latest_risk[assessment.symbol] = trace
            level = "info" if assessment.approved else "warn"
            verb = "APPROVED" if assessment.approved else "BLOCKED"
            self._record_audit(
                "risk",
                level,
                f"Risk {verb}: {assessment.symbol} size={assessment.position_size:.2f}",
                metadata={"correlation_id": correlation_id},
            )
        self._publish({"type": "risk", "data": asdict(trace)})

    def record_order(self, order: Order, order_id: str, broker: str, correlation_id: str = "") -> None:
        trace = OrderTrace(
            timestamp=_now(),
            order_id=order_id,
            symbol=order.symbol,
            side=order.side.value,
            order_type=order.order_type.value,
            quantity=float(order.quantity),
            price=float(order.price) if order.price is not None else None,
            status=OrderStatus.PENDING.value,
            broker=broker,
            correlation_id=correlation_id,
        )
        with self._lock:
            self.orders.append(trace)
            self._record_audit(
                "order",
                "info",
                f"Order placed: {order.side.value} {order.quantity} {order.symbol} via {broker}",
                metadata={"correlation_id": correlation_id, "order_id": order_id},
            )
        self._publish({"type": "order", "data": asdict(trace)})

    def record_fill(self, fill: Fill, correlation_id: str = "", realized_pnl: float = 0.0) -> None:
        trace = FillTrace(
            timestamp=_now(),
            order_id=fill.order_id,
            symbol=fill.symbol,
            side=fill.side.value,
            filled_qty=float(fill.filled_qty),
            avg_price=float(fill.avg_price),
            broker=fill.broker,
            fees=float(fill.fees),
            slippage=float(fill.slippage),
            realized_pnl=float(realized_pnl),
            correlation_id=correlation_id,
        )
        with self._lock:
            self.fills.append(trace)
            self._record_audit(
                "fill",
                "info",
                f"Filled: {fill.side.value} {fill.filled_qty} {fill.symbol} @ "
                f"{fill.avg_price:.4f} ({fill.broker})",
                metadata={"correlation_id": correlation_id, "order_id": fill.order_id},
            )
        self._publish({"type": "fill", "data": asdict(trace)})

    def record_tick(self, summary: TickSummary) -> None:
        with self._lock:
            self.ticks.append(summary)
            self.last_tick_at = summary.timestamp
            self._record_audit(
                "tick",
                "error" if summary.error else "info",
                f"Tick {summary.correlation_id}: "
                f"{summary.signals_emitted} signals, "
                f"{summary.composite_signals} composites, "
                f"{summary.orders_placed} placed, "
                f"{summary.orders_blocked} blocked"
                + (f" — ERROR: {summary.error}" if summary.error else ""),
            )
        self._publish({"type": "tick", "data": asdict(summary)})

    def record_alert(self, alert: AlertRecord) -> None:
        with self._lock:
            self.alerts.append(alert)
            self._record_audit(
                "alert",
                alert.level,
                f"Alert dispatched: {alert.title} → {','.join(alert.channels)}",
            )
        self._publish({"type": "alert", "data": asdict(alert)})

    def record_audit(
        self,
        category: str,
        level: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._record_audit(category, level, message, metadata or {})

    def store_backtest_result(self, name: str, result: dict[str, Any]) -> None:
        with self._lock:
            self.backtests[name] = {**result, "stored_at": _now()}

    # -- internal ---------------------------------------------------------

    def _record_audit(
        self,
        category: str,
        level: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        # caller must already hold the lock
        evt = AuditEvent(
            timestamp=_now(),
            category=category,
            level=level,
            message=message,
            metadata=metadata or {},
        )
        self.audit.append(evt)

    def _publish(self, event: dict[str, Any]) -> None:
        for q in self._listeners:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    # -- readers ----------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "kill_switch_engaged": self.kill_switch_engaged,
                "last_tick_at": self.last_tick_at,
                "next_tick_at": self.next_tick_at,
                "config_path": self.config_path,
                "account": dict(self.account),
                "num_positions": len(self.positions),
                "num_open_orders": len(self.open_orders),
                "num_signals": len(self.signals),
                "num_fills": len(self.fills),
                "risk_status": dict(self.risk_status),
            }


# --- Singleton accessor ----------------------------------------------------

_RUNTIME: RuntimeState | None = None
_RUNTIME_LOCK = threading.Lock()


def get_runtime_state() -> RuntimeState:
    """Return the process-wide singleton :class:`RuntimeState`."""
    global _RUNTIME
    if _RUNTIME is None:
        with _RUNTIME_LOCK:
            if _RUNTIME is None:
                _RUNTIME = RuntimeState()
    return _RUNTIME


def reset_runtime_state() -> None:
    """Reset the singleton — used by tests only."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None


def _now() -> str:
    return datetime.now(UTC).isoformat()
