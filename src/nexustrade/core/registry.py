"""Adapter registry — discovers all plugins via entry_points.

Uses importlib.metadata to discover data providers, brokers,
agents, and notification channels registered in pyproject.toml.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any

from nexustrade.core.exceptions import AdapterNotFoundError

logger = logging.getLogger(__name__)

# Entry point group names
DATA_GROUP = "nexustrade.data"
BROKER_GROUP = "nexustrade.brokers"
AGENT_GROUP = "nexustrade.agents"
NOTIFICATION_GROUP = "nexustrade.notifications"


class AdapterRegistry:
    """Discovers and manages adapters from entry_points.

    Usage:
        registry = AdapterRegistry()
        registry.discover_all()
        provider = registry.get_data_provider("openbb")
    """

    def __init__(self) -> None:
        self._data_providers: dict[str, Any] = {}
        self._brokers: dict[str, Any] = {}
        self._agents: dict[str, Any] = {}
        self._notifications: dict[str, Any] = {}
        # Market → provider/broker mapping
        self._market_providers: dict[str, list[str]] = {}
        self._market_brokers: dict[str, str] = {}

    def discover_all(self) -> None:
        """Discover all registered adapters from entry_points."""
        self._discover_group(DATA_GROUP, self._data_providers)
        self._discover_group(BROKER_GROUP, self._brokers)
        self._discover_group(AGENT_GROUP, self._agents)
        self._discover_group(NOTIFICATION_GROUP, self._notifications)
        logger.info(
            "Discovered adapters: data=%d, brokers=%d, agents=%d, notifications=%d",
            len(self._data_providers),
            len(self._brokers),
            len(self._agents),
            len(self._notifications),
        )

    def _discover_group(self, group: str, registry: dict[str, Any]) -> None:
        """Load entry points for a given group."""
        eps = entry_points()
        group_eps = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])
        for ep in group_eps:
            try:
                cls = ep.load()
                registry[ep.name] = cls
                logger.debug("Loaded %s: %s", group, ep.name)
            except Exception:
                logger.exception("Failed to load %s: %s", group, ep.name)

    def register_data_provider(self, name: str, cls: Any) -> None:
        """Manually register a data provider."""
        self._data_providers[name] = cls

    def register_broker(self, name: str, cls: Any) -> None:
        """Manually register a broker backend."""
        self._brokers[name] = cls

    def register_agent(self, name: str, cls: Any) -> None:
        """Manually register an agent."""
        self._agents[name] = cls

    def register_notification(self, name: str, cls: Any) -> None:
        """Manually register a notification adapter."""
        self._notifications[name] = cls

    def get_data_provider(self, name: str) -> Any:
        """Get a data provider class by name."""
        if name not in self._data_providers:
            available = list(self._data_providers.keys())
            raise AdapterNotFoundError(
                f"Data provider '{name}' not found. Available: {available}"
            )
        return self._data_providers[name]

    def get_broker(self, name: str) -> Any:
        """Get a broker backend class by name."""
        if name not in self._brokers:
            available = list(self._brokers.keys())
            raise AdapterNotFoundError(
                f"Broker '{name}' not found. Available: {available}"
            )
        return self._brokers[name]

    def get_agent(self, name: str) -> Any:
        """Get an agent class by name."""
        if name not in self._agents:
            available = list(self._agents.keys())
            raise AdapterNotFoundError(
                f"Agent '{name}' not found. Available: {available}"
            )
        return self._agents[name]

    def get_notification(self, name: str) -> Any:
        """Get a notification adapter class by name."""
        if name not in self._notifications:
            available = list(self._notifications.keys())
            raise AdapterNotFoundError(
                f"Notification adapter '{name}' not found. Available: {available}"
            )
        return self._notifications[name]

    def get_best_provider_for(self, market: str) -> Any:
        """Get the highest-priority data provider for a market."""
        providers = self._market_providers.get(market, [])
        for name in providers:
            if name in self._data_providers:
                return self._data_providers[name]
        raise AdapterNotFoundError(
            f"No data provider configured for market '{market}'"
        )

    def get_broker_for_market(self, market: str) -> Any:
        """Get the broker configured for a specific market."""
        name = self._market_brokers.get(market)
        if not name or name not in self._brokers:
            raise AdapterNotFoundError(
                f"No broker configured for market '{market}'"
            )
        return self._brokers[name]

    def configure_routing(
        self,
        market_providers: dict[str, list[str]],
        market_brokers: dict[str, str],
    ) -> None:
        """Set market → provider and market → broker routing."""
        self._market_providers = market_providers
        self._market_brokers = market_brokers

    @property
    def data_providers(self) -> dict[str, Any]:
        return dict(self._data_providers)

    @property
    def brokers(self) -> dict[str, Any]:
        return dict(self._brokers)

    @property
    def agents(self) -> dict[str, Any]:
        return dict(self._agents)

    @property
    def notifications(self) -> dict[str, Any]:
        return dict(self._notifications)
