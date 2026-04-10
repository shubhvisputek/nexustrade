"""NexusTrade Prometheus metrics.

Provides counters, histograms, and gauges for key trading operations.
Gracefully degrades if prometheus_client is not installed.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


class _NoOp:
    """No-op stub that silently ignores all metric operations."""

    def labels(self, *args: Any, **kwargs: Any) -> _NoOp:
        return self

    def inc(self, amount: float = 1) -> None:
        pass

    def dec(self, amount: float = 1) -> None:
        pass

    def set(self, value: float) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass

    def info(self, val: dict[str, str]) -> None:
        pass


_NOOP = _NoOp()


class MetricsCollector:
    """Singleton metrics collector with graceful degradation.

    When ``prometheus_client`` is installed, real Prometheus metrics are
    created and updated.  Otherwise every recording method is a silent
    no-op so callers never need to guard imports.
    """

    _instance: MetricsCollector | None = None

    @classmethod
    def get(cls) -> MetricsCollector:
        """Return the global singleton, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (useful for tests)."""
        if cls._instance is not None and _HAS_PROMETHEUS:
            from prometheus_client import REGISTRY

            for attr in vars(cls._instance).values():
                name = getattr(attr, "_name", None)
                if isinstance(name, str) and name.startswith("nexustrade"):
                    try:
                        REGISTRY.unregister(attr)
                    except Exception:
                        pass
        cls._instance = None

    def __init__(self) -> None:
        if _HAS_PROMETHEUS:
            # --- Counters ---
            self.orders_total = Counter(
                "nexustrade_orders_total",
                "Total orders placed",
                ["side", "order_type", "broker", "status"],
            )
            self.signals_total = Counter(
                "nexustrade_signals_total",
                "Total trading signals generated",
                ["agent_name", "direction"],
            )
            self.errors_total = Counter(
                "nexustrade_errors_total",
                "Total errors",
                ["component", "error_type"],
            )
            self.notifications_total = Counter(
                "nexustrade_notifications_total",
                "Total notifications sent",
                ["channel", "level"],
            )

            # --- Histograms ---
            self.order_latency_seconds = Histogram(
                "nexustrade_order_latency_seconds",
                "Order placement latency",
                ["broker"],
            )
            self.agent_analysis_seconds = Histogram(
                "nexustrade_agent_analysis_seconds",
                "Agent analysis duration",
                ["agent_name"],
            )
            self.data_fetch_seconds = Histogram(
                "nexustrade_data_fetch_seconds",
                "Data fetch duration",
                ["provider", "data_type"],
            )
            self.llm_request_seconds = Histogram(
                "nexustrade_llm_request_seconds",
                "LLM request duration",
                ["provider", "channel"],
            )

            # --- Gauges ---
            self.portfolio_value = Gauge(
                "nexustrade_portfolio_value",
                "Total portfolio value",
                ["market"],
            )
            self.portfolio_cash = Gauge(
                "nexustrade_portfolio_cash",
                "Available cash",
            )
            self.open_positions = Gauge(
                "nexustrade_open_positions",
                "Number of open positions",
                ["market"],
            )
            self.circuit_breaker_active = Gauge(
                "nexustrade_circuit_breaker_active",
                "Whether circuit breaker is active (1) or not (0)",
            )
            self.daily_pnl = Gauge(
                "nexustrade_daily_pnl",
                "Daily profit and loss",
            )

            # --- Info ---
            self.nexustrade_info = Info(
                "nexustrade",
                "NexusTrade build information",
            )
        else:
            # Assign no-op stubs for every metric
            self.orders_total = _NOOP  # type: ignore[assignment]
            self.signals_total = _NOOP  # type: ignore[assignment]
            self.errors_total = _NOOP  # type: ignore[assignment]
            self.notifications_total = _NOOP  # type: ignore[assignment]
            self.order_latency_seconds = _NOOP  # type: ignore[assignment]
            self.agent_analysis_seconds = _NOOP  # type: ignore[assignment]
            self.data_fetch_seconds = _NOOP  # type: ignore[assignment]
            self.llm_request_seconds = _NOOP  # type: ignore[assignment]
            self.portfolio_value = _NOOP  # type: ignore[assignment]
            self.portfolio_cash = _NOOP  # type: ignore[assignment]
            self.open_positions = _NOOP  # type: ignore[assignment]
            self.circuit_breaker_active = _NOOP  # type: ignore[assignment]
            self.daily_pnl = _NOOP  # type: ignore[assignment]
            self.nexustrade_info = _NOOP  # type: ignore[assignment]

        # Map metric names to histogram objects for the timer helper
        self._histograms: dict[str, Any] = {
            "order_latency": self.order_latency_seconds,
            "agent_analysis": self.agent_analysis_seconds,
            "data_fetch": self.data_fetch_seconds,
            "llm_request": self.llm_request_seconds,
        }

    # ------------------------------------------------------------------
    # Convenience recording methods
    # ------------------------------------------------------------------

    def record_order(
        self, side: str, order_type: str, broker: str, status: str
    ) -> None:
        """Increment the orders counter."""
        self.orders_total.labels(
            side=side, order_type=order_type, broker=broker, status=status
        ).inc()

    def record_signal(self, agent_name: str, direction: str) -> None:
        """Increment the signals counter."""
        self.signals_total.labels(agent_name=agent_name, direction=direction).inc()

    def record_error(self, component: str, error_type: str) -> None:
        """Increment the errors counter."""
        self.errors_total.labels(component=component, error_type=error_type).inc()

    def record_notification(self, channel: str, level: str) -> None:
        """Increment the notifications counter."""
        self.notifications_total.labels(channel=channel, level=level).inc()

    def observe_latency(
        self, metric_name: str, labels: dict[str, str], duration: float
    ) -> None:
        """Record an observed duration on a named histogram.

        Parameters
        ----------
        metric_name:
            One of ``order_latency``, ``agent_analysis``, ``data_fetch``,
            ``llm_request``.
        labels:
            Label key/value pairs to attach.
        duration:
            Elapsed seconds.
        """
        histogram = self._histograms.get(metric_name)
        if histogram is not None:
            histogram.labels(**labels).observe(duration)

    @contextmanager
    def timer(self, metric_name: str, **labels: str) -> Generator[None, None, None]:
        """Context manager to time operations and record on a histogram.

        Usage::

            with metrics.timer("order_latency", broker="alpaca"):
                place_order(...)
        """
        start = time.monotonic()
        yield
        duration = time.monotonic() - start
        self.observe_latency(metric_name, labels, duration)

    # ------------------------------------------------------------------
    # Portfolio gauges
    # ------------------------------------------------------------------

    def update_portfolio(
        self,
        cash: float,
        total_value: float,
        positions_count: int,
        pnl: float,
        market: str = "",
    ) -> None:
        """Update all portfolio-related gauges."""
        self.portfolio_cash.set(cash)
        self.portfolio_value.labels(market=market).set(total_value)
        self.open_positions.labels(market=market).set(positions_count)
        self.daily_pnl.set(pnl)

    def set_circuit_breaker(self, active: bool) -> None:
        """Set the circuit-breaker gauge."""
        self.circuit_breaker_active.set(1.0 if active else 0.0)

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def get_metrics_text(self) -> str:
        """Return Prometheus text-exposition format for scraping."""
        if not _HAS_PROMETHEUS:
            return "# prometheus_client not installed\n"
        return generate_latest().decode()
