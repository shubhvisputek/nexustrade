"""NexusTrade custom exceptions."""


class NexusTradeError(Exception):
    """Base exception for all NexusTrade errors."""


class ConfigError(NexusTradeError):
    """Configuration error."""


class AdapterNotFoundError(NexusTradeError):
    """Requested adapter not found in registry."""


class DataProviderError(NexusTradeError):
    """Error from a data provider."""


class BrokerError(NexusTradeError):
    """Error from a broker backend."""


class AgentError(NexusTradeError):
    """Error from an agent."""


class RiskCheckError(NexusTradeError):
    """A risk check has failed."""


class CircuitBreakerTriggered(NexusTradeError):
    """Circuit breaker has been activated."""


class EventBusError(NexusTradeError):
    """Error from the event bus."""
