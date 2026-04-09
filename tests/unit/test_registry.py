"""Tests for adapter registry."""

import pytest

from nexustrade.core.registry import AdapterRegistry
from nexustrade.core.exceptions import AdapterNotFoundError


class MockDataProvider:
    name = "mock_provider"
    supported_markets = ["us_equity"]


class MockBroker:
    name = "mock_broker"
    supported_markets = ["us_equity"]


class TestAdapterRegistry:
    def test_register_and_get_data_provider(self):
        registry = AdapterRegistry()
        registry.register_data_provider("mock", MockDataProvider)
        result = registry.get_data_provider("mock")
        assert result is MockDataProvider

    def test_unknown_provider_raises(self):
        registry = AdapterRegistry()
        with pytest.raises(AdapterNotFoundError, match="mock"):
            registry.get_data_provider("mock")

    def test_error_message_lists_available(self):
        registry = AdapterRegistry()
        registry.register_data_provider("yahoo", MockDataProvider)
        registry.register_data_provider("openbb", MockDataProvider)
        with pytest.raises(AdapterNotFoundError) as exc_info:
            registry.get_data_provider("nonexistent")
        assert "yahoo" in str(exc_info.value)
        assert "openbb" in str(exc_info.value)

    def test_register_broker(self):
        registry = AdapterRegistry()
        registry.register_broker("paper", MockBroker)
        assert registry.get_broker("paper") is MockBroker

    def test_unknown_broker_raises(self):
        registry = AdapterRegistry()
        with pytest.raises(AdapterNotFoundError):
            registry.get_broker("alpaca")

    def test_register_agent(self):
        registry = AdapterRegistry()

        class MockAgent:
            pass

        registry.register_agent("buffett", MockAgent)
        assert registry.get_agent("buffett") is MockAgent

    def test_register_notification(self):
        registry = AdapterRegistry()

        class MockNotifier:
            pass

        registry.register_notification("telegram", MockNotifier)
        assert registry.get_notification("telegram") is MockNotifier

    def test_market_routing(self):
        registry = AdapterRegistry()
        registry.register_data_provider("openbb", MockDataProvider)
        registry.register_broker("openalgo", MockBroker)

        registry.configure_routing(
            market_providers={"india_equity": ["openbb"]},
            market_brokers={"india_equity": "openalgo"},
        )

        provider = registry.get_best_provider_for("india_equity")
        assert provider is MockDataProvider

        broker = registry.get_broker_for_market("india_equity")
        assert broker is MockBroker

    def test_market_routing_not_configured(self):
        registry = AdapterRegistry()
        with pytest.raises(AdapterNotFoundError):
            registry.get_best_provider_for("crypto")

    def test_properties(self):
        registry = AdapterRegistry()
        registry.register_data_provider("a", MockDataProvider)
        registry.register_broker("b", MockBroker)
        assert "a" in registry.data_providers
        assert "b" in registry.brokers
