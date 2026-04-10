"""Unit tests for nexustrade.core.metrics."""

from __future__ import annotations

import pytest

from nexustrade.core.metrics import MetricsCollector, _HAS_PROMETHEUS


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure each test gets a fresh MetricsCollector."""
    MetricsCollector.reset()
    yield
    MetricsCollector.reset()


# If prometheus_client is available we also need to clear the Collector registry
# between tests, because prometheus_client forbids re-registering metrics with
# the same name.
if _HAS_PROMETHEUS:
    from prometheus_client import REGISTRY, CollectorRegistry

    @pytest.fixture(autouse=True)
    def _clean_prometheus_registry():
        """Unregister NexusTrade collectors between tests."""
        yield
        # Collect names registered by our metrics
        to_remove = []
        for collector in list(REGISTRY._names_to_collectors.values()):
            name = getattr(collector, "_name", "")
            if isinstance(name, str) and name.startswith("nexustrade"):
                to_remove.append(collector)
        for c in set(to_remove):
            try:
                REGISTRY.unregister(c)
            except Exception:
                pass


@pytest.mark.unit
class TestMetricsCollectorSingleton:
    def test_get_returns_same_instance(self):
        a = MetricsCollector.get()
        b = MetricsCollector.get()
        assert a is b

    def test_reset_clears_singleton(self):
        a = MetricsCollector.get()
        MetricsCollector.reset()
        b = MetricsCollector.get()
        assert a is not b


@pytest.mark.unit
class TestRecordOrder:
    def test_record_order_does_not_raise(self):
        m = MetricsCollector.get()
        m.record_order(side="buy", order_type="market", broker="alpaca", status="filled")

    def test_record_order_multiple_times(self):
        m = MetricsCollector.get()
        for _ in range(5):
            m.record_order(side="sell", order_type="limit", broker="paper", status="submitted")


@pytest.mark.unit
class TestRecordSignal:
    def test_record_signal_does_not_raise(self):
        m = MetricsCollector.get()
        m.record_signal(agent_name="ai_hedge_fund", direction="long")

    def test_record_signal_various_directions(self):
        m = MetricsCollector.get()
        for direction in ("long", "short", "hold"):
            m.record_signal(agent_name="test_agent", direction=direction)


@pytest.mark.unit
class TestRecordError:
    def test_record_error_does_not_raise(self):
        m = MetricsCollector.get()
        m.record_error(component="execution", error_type="timeout")

    def test_record_error_different_components(self):
        m = MetricsCollector.get()
        m.record_error(component="data", error_type="api_error")
        m.record_error(component="agents", error_type="llm_failure")


@pytest.mark.unit
class TestTimerContextManager:
    def test_timer_yields_and_records(self):
        m = MetricsCollector.get()
        with m.timer("order_latency", broker="paper"):
            total = sum(range(100))
        assert total == 4950  # sanity: body executed

    def test_timer_with_unknown_metric_does_not_raise(self):
        m = MetricsCollector.get()
        with m.timer("nonexistent_metric", foo="bar"):
            pass

    def test_timer_records_positive_duration(self):
        """Ensure observe_latency is called with a positive value."""
        import time

        m = MetricsCollector.get()
        durations: list[float] = []
        original = m.observe_latency

        def spy(metric_name, labels, duration):
            durations.append(duration)
            original(metric_name, labels, duration)

        m.observe_latency = spy  # type: ignore[assignment]
        with m.timer("data_fetch", provider="yahoo", data_type="ohlcv"):
            time.sleep(0.01)
        assert len(durations) == 1
        assert durations[0] > 0


@pytest.mark.unit
class TestUpdatePortfolio:
    def test_update_portfolio_does_not_raise(self):
        m = MetricsCollector.get()
        m.update_portfolio(
            cash=10000.0,
            total_value=50000.0,
            positions_count=5,
            pnl=250.0,
            market="us_equities",
        )

    def test_update_portfolio_default_market(self):
        m = MetricsCollector.get()
        m.update_portfolio(cash=5000.0, total_value=5000.0, positions_count=0, pnl=0.0)


@pytest.mark.unit
class TestSetCircuitBreaker:
    def test_set_active(self):
        m = MetricsCollector.get()
        m.set_circuit_breaker(True)

    def test_set_inactive(self):
        m = MetricsCollector.get()
        m.set_circuit_breaker(False)


@pytest.mark.unit
class TestGetMetricsText:
    def test_returns_non_empty_string(self):
        m = MetricsCollector.get()
        text = m.get_metrics_text()
        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.skipif(not _HAS_PROMETHEUS, reason="prometheus_client not installed")
    def test_contains_nexustrade_metrics(self):
        m = MetricsCollector.get()
        m.record_order(side="buy", order_type="market", broker="alpaca", status="filled")
        text = m.get_metrics_text()
        assert "nexustrade_orders_total" in text

    @pytest.mark.skipif(not _HAS_PROMETHEUS, reason="prometheus_client not installed")
    def test_text_includes_recorded_signal(self):
        m = MetricsCollector.get()
        m.record_signal(agent_name="test", direction="long")
        text = m.get_metrics_text()
        assert "nexustrade_signals_total" in text

    def test_graceful_without_prometheus(self):
        """Even without prometheus, get_metrics_text returns a string."""
        m = MetricsCollector.get()
        text = m.get_metrics_text()
        assert isinstance(text, str)


@pytest.mark.unit
class TestRecordNotification:
    def test_record_notification_does_not_raise(self):
        m = MetricsCollector.get()
        m.record_notification(channel="telegram", level="info")
