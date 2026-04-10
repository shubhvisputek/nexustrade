"""NexusTrade canonical data models.

All adapters convert to/from these models. Uses dataclasses for simplicity.
Pydantic models are used only for configuration (see config.py).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

# --- Enums ---

class SignalDirection(StrEnum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    SPREAD = "spread"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    IRON_CONDOR = "iron_condor"


class OptionType(StrEnum):
    CALL = "call"
    PUT = "put"


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# --- Validation helpers ---

def _validate_utc(ts: datetime) -> None:
    if ts.tzinfo is None or ts.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"Timestamp must be UTC timezone-aware, got {ts!r}")


def _validate_confidence(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"Confidence must be between 0.0 and 1.0, got {value}")


# --- Serialization mixin ---

class SerializableMixin:
    """Mixin providing JSON-compatible serialization for dataclasses."""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)  # type: ignore[arg-type]
        # Convert datetime to ISO string, Enum to value
        return _serialize_value(d)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        # Subclasses should implement specific deserialization if needed
        return cls(**data)


def _serialize_value(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _serialize_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_value(item) for item in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    return obj


# --- Options Models ---

@dataclass
class OptionGreeks(SerializableMixin):
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    iv: float  # implied volatility


@dataclass
class OptionContract(SerializableMixin):
    symbol: str
    underlying: str
    option_type: OptionType
    strike: float
    expiry: datetime
    greeks: OptionGreeks | None
    bid: float
    ask: float
    last: float
    volume: float
    open_interest: float
    source: str

    def __post_init__(self) -> None:
        if isinstance(self.option_type, str):
            self.option_type = OptionType(self.option_type)


@dataclass
class OptionChain(SerializableMixin):
    underlying: str
    expiry: datetime
    contracts: list[OptionContract]
    timestamp: datetime
    source: str

    def __post_init__(self) -> None:
        _validate_utc(self.timestamp)


# --- Market Data Models ---

@dataclass
class OHLCV(SerializableMixin):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    timeframe: str  # "1m","5m","15m","1h","4h","1d","1w","1M"
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_utc(self.timestamp)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OHLCV:
        d = dict(data)
        if isinstance(d["timestamp"], str):
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
            if d["timestamp"].tzinfo is None:
                d["timestamp"] = d["timestamp"].replace(tzinfo=UTC)
        return cls(**d)


@dataclass
class Quote(SerializableMixin):
    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    timestamp: datetime
    source: str

    def __post_init__(self) -> None:
        _validate_utc(self.timestamp)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Quote:
        d = dict(data)
        if isinstance(d["timestamp"], str):
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
            if d["timestamp"].tzinfo is None:
                d["timestamp"] = d["timestamp"].replace(tzinfo=UTC)
        return cls(**d)


@dataclass
class NewsItem(SerializableMixin):
    timestamp: datetime
    headline: str
    source: str
    symbols: list[str]
    body: str | None = None
    sentiment_score: float | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        _validate_utc(self.timestamp)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NewsItem:
        d = dict(data)
        if isinstance(d["timestamp"], str):
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
            if d["timestamp"].tzinfo is None:
                d["timestamp"] = d["timestamp"].replace(tzinfo=UTC)
        return cls(**d)


@dataclass
class TechnicalIndicators(SerializableMixin):
    symbol: str
    timeframe: str
    timestamp: datetime
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_9: float | None = None
    ema_21: float | None = None
    atr: float | None = None
    adx: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None
    source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    option_delta: float | None = None
    option_gamma: float | None = None
    option_theta: float | None = None
    option_vega: float | None = None
    option_iv: float | None = None

    def __post_init__(self) -> None:
        _validate_utc(self.timestamp)


# --- Agent Models ---

@dataclass
class AgentSignal(SerializableMixin):
    direction: SignalDirection
    confidence: float
    reasoning: str
    agent_name: str
    agent_type: str  # "persona", "debate", "rl", "sentiment", "vision", "factor"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)
        _validate_utc(self.timestamp)
        if isinstance(self.direction, str):
            self.direction = SignalDirection(self.direction)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentSignal:
        d = dict(data)
        if isinstance(d.get("timestamp"), str):
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
            if d["timestamp"].tzinfo is None:
                d["timestamp"] = d["timestamp"].replace(tzinfo=UTC)
        if isinstance(d.get("direction"), str):
            d["direction"] = SignalDirection(d["direction"])
        return cls(**d)


@dataclass
class PortfolioState(SerializableMixin):
    cash: float
    positions: list[Position]
    total_value: float
    daily_pnl: float
    total_pnl: float
    open_orders: list[Order]
    consecutive_losses: int = 0
    circuit_breaker_active: bool = False


@dataclass
class MarketContext(SerializableMixin):
    """Everything an agent needs to make a decision."""
    symbol: str
    current_price: float
    ohlcv: dict[str, list[OHLCV]]  # keyed by timeframe
    technicals: dict[str, TechnicalIndicators]  # keyed by timeframe
    news: list[NewsItem]
    fundamentals: dict[str, Any]
    sentiment_scores: list[float]
    factor_signals: dict[str, Any]
    recent_signals: list[AgentSignal]
    memory: list[dict[str, Any]]
    portfolio: PortfolioState
    config: dict[str, Any]


@dataclass
class CompositeSignal(SerializableMixin):
    """Output of signal aggregation."""
    symbol: str
    direction: SignalDirection
    confidence: float
    contributing_signals: list[AgentSignal]
    aggregation_mode: str
    reasoning: str
    timestamp: datetime

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)
        _validate_utc(self.timestamp)
        if isinstance(self.direction, str):
            self.direction = SignalDirection(self.direction)


# --- Execution Models ---

@dataclass
class Order(SerializableMixin):
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    time_in_force: str = "GTC"
    strategy_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    legs: list[Order] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.side, str):
            self.side = OrderSide(self.side)
        if isinstance(self.order_type, str):
            self.order_type = OrderType(self.order_type)


@dataclass
class Fill(SerializableMixin):
    order_id: str
    symbol: str
    side: OrderSide
    filled_qty: float
    avg_price: float
    timestamp: datetime
    broker: str
    status: OrderStatus
    fees: float = 0.0
    slippage: float = 0.0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_utc(self.timestamp)
        if isinstance(self.side, str):
            self.side = OrderSide(self.side)
        if isinstance(self.status, str):
            self.status = OrderStatus(self.status)


@dataclass
class Position(SerializableMixin):
    symbol: str
    quantity: float  # Positive = long, Negative = short
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    broker: str = ""
    market: str = ""  # "us_equity", "india_equity", "crypto", "forex"


# --- Risk Models ---

@dataclass
class RiskAssessment(SerializableMixin):
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
    metadata: dict[str, Any] = field(default_factory=dict)


# --- Event Model ---

@dataclass
class Event(SerializableMixin):
    event_type: str
    timestamp: datetime
    payload: dict[str, Any]
    source_service: str
    correlation_id: str

    def __post_init__(self) -> None:
        _validate_utc(self.timestamp)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, data: str) -> Event:
        d = json.loads(data)
        if isinstance(d["timestamp"], str):
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
            if d["timestamp"].tzinfo is None:
                d["timestamp"] = d["timestamp"].replace(tzinfo=UTC)
        return cls(**d)
