# NexusTrade — System architecture

> **Version:** 1.0  
> **Purpose:** Complete high-level design (HLD) and low-level design (LLD) with all abstract interfaces, data models, event schemas, configuration schemas, Docker topology, and inter-service communication protocols. Claude Code should use this as the implementation reference for all structural decisions.

---

## 1. High-level design (HLD)

### 1.1 Architecture pattern

**Microservices over event bus.** Nine Docker containers communicate through Redis Streams for asynchronous events and gRPC for synchronous ML inference. Each service owns its dependencies — no shared process space between conflicting libraries.

### 1.2 Service topology

```
                    ┌──────────────────────────────────────────────────────────────┐
                    │                     USER INTERFACES                          │
                    │   CLI (Typer)  │  Web Dashboard (Streamlit)  │  REST API     │
                    └───────┬────────┴──────────┬──────────────────┴───────┬───────┘
                            │                   │                         │
                    ┌───────▼───────────────────▼─────────────────────────▼───────┐
                    │                     WEB UI SERVICE                           │
                    │  FastAPI REST + Streamlit Dashboard + Webhook Receiver       │
                    │  Port: 8085 (API), 8501 (Dashboard), 8888 (Webhook)         │
                    └───────┬─────────────────────────────────────────────┬───────┘
                            │ Redis pub/sub                               │ HTTP
                    ┌───────▼─────────────────────────────────────────────▼───────┐
                    │              REDIS STREAMS EVENT BUS                         │
                    │  Channels: market.data.* │ market.enriched.* │              │
                    │  agent.signal.* │ signal.composite.* │ risk.assessed.* │    │
                    │  execution.order.* │ execution.fill.* │ system.alert        │
                    └──┬────────┬──────────┬──────────┬──────────┬───────────┬────┘
                       │        │          │          │          │           │
              ┌────────▼──┐ ┌──▼───────┐ ┌▼────────┐ ┌▼────────┐ ┌▼───────┐ ┌▼────────┐
              │DATA       │ │AGENT     │ │LLM      │ │RISK     │ │EXEC    │ │CONFIG   │
              │SERVICE    │ │ENGINE    │ │ROUTER   │ │ENGINE   │ │ENGINE  │ │SERVICE  │
              │           │ │          │ │         │ │         │ │        │ │         │
              │OpenBB     │ │ai-HF     │ │LiteLLM  │ │Debate   │ │Alpaca  │ │Pydantic │
              │TV MCP     │ │TradAgts  │ │Fast     │ │CVaR     │ │OpenAlgo│ │YAML     │
              │CCXT       │ │FinBERT*  │ │Deep     │ │Circuit  │ │CCXT    │ │Env vars │
              │Broker API │ │QlibAlpha*│ │Vision   │ │India    │ │IB      │ │         │
              │Yahoo      │ │Quant*    │ │         │ │         │ │TV WH   │ │         │
              │           │ │          │ │         │ │         │ │Paper   │ │         │
              └───────────┘ └──────────┘ └─────────┘ └─────────┘ └────────┘ └─────────┘
                                │                                     
                       ┌────────┴──── gRPC ────────────────┐
                       │              │                     │
                  ┌────▼─────┐  ┌────▼─────┐  ┌───────────▼┐
                  │FINRL     │  │FINGPT    │  │QLIB        │
                  │SERVICE   │  │SERVICE   │  │SERVICE     │
                  │(GPU)     │  │(GPU)     │  │(CPU)       │
                  │SB3, Gym  │  │HF, PEFT  │  │Qlib, LGB  │
                  └──────────┘  └──────────┘  └────────────┘
```

*Services marked with `*` in agent-engine call ML services via gRPC for inference.

### 1.3 Data flow (7 stages)

| Stage | Event stream | Producer | Consumer | Description |
|-------|-------------|----------|----------|-------------|
| 1. Ingestion | `market.data.{symbol}` | Data service | Agent engine, Risk engine | Raw OHLCV, quotes, news, fundamentals |
| 2. Enrichment | `market.enriched.{symbol}` | Agent engine (preprocessing) | Agent engine (analysis) | FinBERT scores, Qlib factors, chart images |
| 3. Analysis | `agent.signal.{symbol}` | Agent engine | Agent engine (aggregator) | Individual agent signals (direction + confidence) |
| 4. Aggregation | `signal.composite.{symbol}` | Agent engine (aggregator) | Risk engine | Combined signal from all agents |
| 5. Risk | `risk.assessed.{symbol}` | Risk engine | Execution engine | Risk-adjusted order with position sizing |
| 6. Execution | `execution.order.{symbol}` | Execution engine | Execution engine (backends) | Order sent to broker(s) |
| 7. Fill | `execution.fill.{symbol}` | Execution engine | Web UI, Risk engine, Memory | Fill confirmation, PnL update |

---

## 2. Low-level design (LLD) — Core data models

### 2.1 Canonical market data models

```python
# All models use dataclasses for simplicity. Pydantic models for config only.

@dataclass
class OHLCV:
    timestamp: datetime          # UTC, timezone-aware
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str                  # Canonical: "AAPL", "EUR/USD", "BTC/USDT", "RELIANCE"
    timeframe: str               # "1m","5m","15m","1h","4h","1d","1w","1M"
    source: str                  # Provider name: "openbb", "ccxt", "tradingview_mcp"
    metadata: dict = field(default_factory=dict)

@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    timestamp: datetime
    source: str

@dataclass
class NewsItem:
    timestamp: datetime
    headline: str
    source: str                  # "reuters", "moneycontrol", "coindesk"
    symbols: list[str]
    body: str | None = None
    sentiment_score: float | None = None
    url: str | None = None

@dataclass
class TechnicalIndicators:
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
    source: str = ""             # "tradingview_mcp", "computed"
    extra: dict = field(default_factory=dict)
```

### 2.2 Agent models

```python
class SignalDirection(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

@dataclass
class AgentSignal:
    direction: SignalDirection
    confidence: float            # 0.0 to 1.0, validated
    reasoning: str               # Human-readable explanation
    agent_name: str              # "warren_buffett", "finrl_ppo", "finbert"
    agent_type: str              # "persona", "debate", "rl", "sentiment", "vision", "factor"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)
    # metadata examples: {"indicators_used": ["rsi", "macd"]}, {"model": "ppo_v3"}

@dataclass
class MarketContext:
    """Everything an agent needs to make a decision."""
    symbol: str
    current_price: float
    ohlcv: dict[str, list[OHLCV]]   # keyed by timeframe: {"1h": [...], "4h": [...]}
    technicals: dict[str, TechnicalIndicators]  # keyed by timeframe
    news: list[NewsItem]
    fundamentals: dict               # P/E, EPS, revenue, etc.
    sentiment_scores: list[float]    # Pre-computed FinBERT scores
    factor_signals: dict             # Qlib alpha factors
    recent_signals: list[AgentSignal]  # From other agents (for sequential/DAG mode)
    memory: list[dict]               # Similar historical situations from ChromaDB
    portfolio: PortfolioState        # Current positions, balance, PnL
    config: dict                     # Agent-specific config from YAML

@dataclass
class CompositeSignal:
    """Output of signal aggregation."""
    symbol: str
    direction: SignalDirection
    confidence: float
    contributing_signals: list[AgentSignal]
    aggregation_mode: str            # "weighted_confidence", "majority", etc.
    reasoning: str
    timestamp: datetime
```

### 2.3 Execution models

```python
class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

@dataclass
class Order:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    time_in_force: str = "GTC"       # GTC, IOC, DAY
    strategy_name: str = ""
    metadata: dict = field(default_factory=dict)

@dataclass
class Fill:
    order_id: str
    symbol: str
    side: OrderSide
    filled_qty: float
    avg_price: float
    timestamp: datetime
    broker: str                      # "alpaca", "openalgo_zerodha", "ccxt_binance"
    status: OrderStatus
    fees: float = 0.0
    slippage: float = 0.0           # Difference from requested price
    latency_ms: float = 0.0         # Time from order submission to fill
    metadata: dict = field(default_factory=dict)

@dataclass
class Position:
    symbol: str
    quantity: float                  # Positive = long, Negative = short
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    broker: str = ""
    market: str = ""                 # "us_equity", "india_equity", "crypto", "forex"

@dataclass
class PortfolioState:
    cash: float
    positions: list[Position]
    total_value: float               # cash + sum of position values
    daily_pnl: float
    total_pnl: float
    open_orders: list[Order]
    consecutive_losses: int = 0
    circuit_breaker_active: bool = False
```

### 2.4 Risk models

```python
@dataclass
class RiskAssessment:
    symbol: str
    approved: bool
    position_size: float             # Recommended quantity
    stop_loss_price: float
    take_profit_price: float
    risk_reward_ratio: float
    max_loss_amount: float           # Dollar amount of max loss
    sizing_model: str                # "cvar", "kelly", "fixed_fraction", etc.
    risk_debate_summary: str | None  # From 3-perspective debate
    warnings: list[str]              # Any risk warnings
    metadata: dict = field(default_factory=dict)
```

---

## 3. LLD — Abstract interfaces (ABCs)

### 3.1 DataProviderInterface

```python
class DataProviderInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def supported_markets(self) -> list[str]: ...
    # Values: "us_equity", "india_equity", "forex", "crypto", "options", "commodity"

    @abstractmethod
    async def get_ohlcv(self, symbol: str, timeframe: str,
                        start: datetime, end: datetime) -> list[OHLCV]: ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote: ...

    # Optional methods with defaults
    async def get_news(self, symbol: str, limit: int = 20) -> list[NewsItem]:
        return []

    async def get_fundamentals(self, symbol: str) -> dict:
        return {}

    async def get_technicals(self, symbol: str, timeframe: str = "1d") -> TechnicalIndicators | None:
        return None

    async def get_chart_image(self, symbol: str, timeframe: str) -> bytes | None:
        return None

    async def screen(self, filters: dict) -> list[dict]:
        return []

    async def stream(self, symbols: list[str]) -> AsyncIterator[Quote]:
        raise NotImplementedError

    async def health_check(self) -> bool:
        return True
```

### 3.2 BrokerBackendInterface

```python
class BrokerBackendInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def supported_markets(self) -> list[str]: ...

    @property
    @abstractmethod
    def is_paper(self) -> bool: ...

    @abstractmethod
    async def place_order(self, order: Order) -> Fill: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def get_account(self) -> dict: ...

    # Optional
    async def modify_order(self, order_id: str, **changes) -> Fill:
        raise NotImplementedError

    async def get_order_history(self, limit: int = 50) -> list[Fill]:
        return []

    async def health_check(self) -> bool:
        return True
```

### 3.3 AgentInterface

```python
class AgentInterface(ABC):
    @abstractmethod
    async def analyze(self, context: MarketContext) -> AgentSignal: ...

    @abstractmethod
    def get_capabilities(self) -> dict: ...
    # Returns: {"requires_vision": bool, "requires_gpu": bool,
    #           "llm_channel": "fast"|"deep"|"vision",
    #           "supported_markets": ["us_equity", "crypto", ...]}

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def agent_type(self) -> str:
        return "generic"
```

### 3.4 NotificationAdapter

```python
class NotificationAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def send(self, title: str, message: str, level: str = "info") -> bool: ...
    # level: "info", "warning", "error", "critical"

    async def send_trade_alert(self, fill: Fill) -> bool:
        msg = f"{fill.side.value.upper()} {fill.filled_qty} {fill.symbol} @ {fill.avg_price}"
        return await self.send(f"Trade: {fill.symbol}", msg, "info")

    async def send_circuit_breaker(self, reason: str, resume_at: datetime) -> bool:
        return await self.send("Circuit Breaker Triggered", reason, "critical")
```

### 3.5 RiskModelInterface

```python
class RiskModelInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def calculate_position_size(
        self,
        portfolio: PortfolioState,
        signal: CompositeSignal,
        market_data: list[OHLCV],
        config: dict,
    ) -> RiskAssessment: ...
```

### 3.6 StrategyInterface

```python
class StrategyInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def evaluate_entry(
        self,
        context: MarketContext,
        signals: list[AgentSignal],
    ) -> bool: ...

    @abstractmethod
    def evaluate_exit(
        self,
        context: MarketContext,
        signals: list[AgentSignal],
        position: Position,
    ) -> bool: ...
```

---

## 4. LLD — Event schemas

All events are JSON-serialized and published to Redis Streams.

```python
@dataclass
class Event:
    event_type: str          # "market.data", "agent.signal", "execution.fill", etc.
    timestamp: datetime
    payload: dict            # Serialized data model
    source_service: str      # "data-service", "agent-engine", etc.
    correlation_id: str      # UUID linking related events across the pipeline

# Example events:
# market.data.AAPL → {"event_type": "market.data", "payload": {OHLCV as dict}, ...}
# agent.signal.AAPL → {"event_type": "agent.signal", "payload": {AgentSignal as dict}, ...}
# execution.fill.AAPL → {"event_type": "execution.fill", "payload": {Fill as dict}, ...}
```

---

## 5. LLD — Configuration schema

Complete Pydantic settings hierarchy:

```python
class LLMProviderConfig(BaseModel):
    provider: str                    # "ollama", "anthropic", "openai", "deepseek", "gemini", "groq"
    model: str                       # "llama3:8b", "claude-sonnet-4-20250514", "gpt-4o"
    base_url: str | None = None      # For Ollama: "http://localhost:11434"
    api_key: str | None = None
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 4096

class LLMConfig(BaseModel):
    mode: Literal["local", "cloud", "hybrid"] = "hybrid"
    fast: LLMProviderConfig
    deep: LLMProviderConfig
    vision: LLMProviderConfig | None = None
    fallbacks: list[LLMProviderConfig] = []

class AgentEntry(BaseModel):
    name: str
    source: str                      # "ai_hedge_fund", "trading_agents", "finrl", etc.
    enabled: bool = True
    llm_override: dict | None = None # Per-agent LLM params
    config: dict = {}                # Agent-specific config

class AgentConfig(BaseModel):
    enabled: list[AgentEntry]
    aggregation_mode: Literal["weighted_confidence", "majority", "unanimous", "portfolio_manager"] = "weighted_confidence"
    min_confidence: float = 0.6
    execution_mode: Literal["parallel", "sequential", "dag"] = "parallel"
    debate_rounds: int = 2
    early_termination_confidence: float = 0.9

class BrokerEntry(BaseModel):
    name: str                        # "alpaca", "openalgo", "ccxt_broker", "paper"
    enabled: bool = True
    markets: list[str]               # ["us_equity"], ["india_equity", "india_fno"]
    config: dict = {}                # Broker-specific: api_key, host, exchange, etc.

class ExecutionConfig(BaseModel):
    mode: Literal["tradingview", "python", "both"] = "python"
    brokers: list[BrokerEntry]
    tradingview: TradingViewConfig = TradingViewConfig()

class TradingViewConfig(BaseModel):
    enabled: bool = False
    webhook_port: int = 8888
    passphrase: str = ""
    india_route: str = "openalgo"
    us_route: str = "alpaca"

class MarketConfig(BaseModel):
    symbols: list[str]
    data_provider: str = "openbb"
    exchange: str | None = None

class RiskConfig(BaseModel):
    max_position_pct: float = 0.05
    max_portfolio_risk: float = 0.20
    sizing_model: Literal["cvar", "kelly", "fixed_fraction", "volatility", "max_drawdown"] = "kelly"
    cvar_confidence: float = 0.95
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()

class CircuitBreakerConfig(BaseModel):
    max_daily_loss_pct: float = 0.03
    max_consecutive_losses: int = 5
    max_open_positions: int = 10
    cooldown_minutes: int = 60

class SchedulerConfig(BaseModel):
    analysis_interval: str = "4h"    # How often to run full analysis
    timeframes: list[str] = ["1h", "4h", "1d"]
    risk_check_interval: str = "15m"

class DataProviderEntry(BaseModel):
    name: str
    enabled: bool = True
    priority: int = 1                # Lower = higher priority
    config: dict = {}

class DataConfig(BaseModel):
    providers: list[DataProviderEntry]
    routing: dict[str, list[str]]    # market → provider priority list
    cache: CacheConfig = CacheConfig()

class CacheConfig(BaseModel):
    enabled: bool = True
    ttl_seconds: dict[str, int] = {
        "quote": 0,                  # No cache for real-time
        "ohlcv_1m": 60,
        "ohlcv_1h": 300,
        "ohlcv_1d": 3600,
        "fundamentals": 86400,
        "news": 300,
    }
    warm_on_start: bool = True

class MemoryConfig(BaseModel):
    enabled: bool = True
    retention_days: int = 90
    max_entries: int = 10000
    similarity_threshold: float = 0.75

class NotificationConfig(BaseModel):
    channels: list[dict] = []        # [{name: "telegram", config: {token: ...}}, ...]
    events: dict[str, list[str]] = { # event_type → channel names
        "trade": ["telegram"],
        "circuit_breaker": ["telegram", "email"],
        "error": ["email"],
    }

class NexusTradeConfig(BaseSettings):
    """Root configuration — all settings validated by Pydantic."""
    llm: LLMConfig
    agents: AgentConfig
    execution: ExecutionConfig
    markets: dict[str, MarketConfig]
    risk: RiskConfig
    scheduler: SchedulerConfig
    data: DataConfig
    memory: MemoryConfig = MemoryConfig()
    notifications: NotificationConfig = NotificationConfig()
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="NEXUS__",
        env_nested_delimiter="__",
        yaml_file="config/default.yaml",
    )
```

---

## 6. LLD — Project directory structure

```
nexustrade/
├── pyproject.toml
├── docker-compose.yml
├── docker-compose.cpu-only.yml        # Without GPU services
├── Makefile                           # Common commands: make dev, make test, make build
├── README.md
├── LICENSE                            # MIT
├── config/
│   ├── default.yaml                   # Complete default configuration
│   ├── production.yaml                # Production overrides
│   ├── development.yaml               # Dev overrides (paper trading, verbose logging)
│   ├── examples/
│   │   ├── us_equities_basic.yaml     # Minimal US equity setup
│   │   ├── india_nse_zerodha.yaml     # Indian market with Zerodha via OpenAlgo
│   │   ├── crypto_binance.yaml        # Crypto on Binance
│   │   ├── forex_with_tv.yaml         # Forex with TradingView execution
│   │   ├── multi_market_full.yaml     # All markets, all features
│   │   └── local_ollama_only.yaml     # Full local mode, no cloud APIs
│   └── prompts/                       # Jinja2 prompt templates
│       ├── agents/
│       │   ├── warren_buffett.j2
│       │   ├── charlie_munger.j2
│       │   ├── technical_analyst.j2
│       │   └── ...                    # One template per persona agent
│       ├── debate/
│       │   ├── bull_researcher.j2
│       │   ├── bear_researcher.j2
│       │   └── research_manager.j2
│       ├── risk/
│       │   ├── aggressive.j2
│       │   ├── conservative.j2
│       │   ├── neutral.j2
│       │   └── risk_manager.j2
│       └── aggregation/
│           └── portfolio_manager.j2
├── src/nexustrade/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py                  # ALL data models (OHLCV, AgentSignal, Order, Fill, etc.)
│   │   ├── interfaces.py             # ALL ABCs (DataProvider, BrokerBackend, Agent, etc.)
│   │   ├── config.py                  # Pydantic settings models
│   │   ├── events.py                  # Event class, EventBus ABC, Redis implementation
│   │   ├── registry.py               # AdapterRegistry — discovers all entry_points
│   │   └── exceptions.py             # Custom exceptions
│   ├── data/
│   │   ├── __init__.py
│   │   ├── router.py                  # Smart data routing (market → provider)
│   │   ├── cache.py                   # 3-level cache (memory → Redis → disk)
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── openbb_adapter.py
│   │       ├── tradingview_mcp.py
│   │       ├── ccxt_data.py
│   │       ├── broker_data.py         # OpenAlgo data endpoints
│   │       └── yahoo.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── registry.py               # Agent discovery and instantiation
│   │   ├── aggregator.py             # Signal aggregation (4 modes)
│   │   ├── executor.py               # Agent execution (parallel/sequential/DAG)
│   │   ├── memory.py                  # ChromaDB situation memory
│   │   ├── prompt_loader.py           # Jinja2 template loading + hot-reload
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── ai_hedge_fund.py       # 18 persona agent adapters
│   │       ├── trading_agents.py      # Bull/bear debate + risk debate
│   │       ├── finrl_agent.py         # DRL agent (gRPC to finrl-service)
│   │       ├── fingpt_sentiment.py    # FinGPT sentiment (gRPC to fingpt-service)
│   │       ├── finbert_agent.py       # FinBERT fast sentiment
│   │       ├── quantagent_vision.py   # Vision chart analysis
│   │       └── qlib_alpha.py          # Qlib factor signals (gRPC to qlib-service)
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── router.py                  # LLMRouter: channel-based routing
│   │   ├── litellm_provider.py        # LiteLLM wrapper
│   │   └── capabilities.py            # Model capability registry
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── engine.py                  # Risk assessment pipeline
│   │   ├── pre_trade.py              # Pre-trade validation checks
│   │   ├── sizing/
│   │   │   ├── __init__.py
│   │   │   ├── cvar.py
│   │   │   ├── kelly.py
│   │   │   ├── fixed_fraction.py
│   │   │   ├── volatility.py
│   │   │   └── max_drawdown.py
│   │   ├── circuit_breaker.py
│   │   ├── india_rules.py             # India-specific risk rules
│   │   └── debate.py                  # 3-perspective risk debate
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── engine.py                  # ExecutionEngine: mode-based routing
│   │   ├── order_manager.py           # Order lifecycle tracking
│   │   ├── webhooks.py                # FastAPI webhook receiver
│   │   └── backends/
│   │       ├── __init__.py
│   │       ├── alpaca.py
│   │       ├── openalgo.py
│   │       ├── ccxt_broker.py
│   │       ├── ib.py
│   │       ├── paper.py               # Paper trading with slippage
│   │       └── tradingview.py         # TradingView webhook relay
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── engine.py                  # Strategy evaluation engine
│   │   ├── parser.py                  # YAML strategy definition parser
│   │   └── conditions.py             # Condition evaluators (agent refs, indicator refs)
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── engine.py                  # Historical replay engine
│   │   ├── metrics.py                 # Performance metrics (Sharpe, drawdown, etc.)
│   │   └── report.py                  # Backtest report generator
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── telegram.py
│   │   ├── discord.py
│   │   ├── email.py
│   │   └── webhook.py
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── engine.py                  # Cron + interval + event-based scheduling
│   ├── web/
│   │   ├── __init__.py
│   │   ├── app.py                     # FastAPI main application
│   │   ├── dashboard.py               # Streamlit dashboard
│   │   └── api/
│   │       ├── signals.py
│   │       ├── portfolio.py
│   │       ├── config.py
│   │       └── health.py
│   └── cli/
│       ├── __init__.py
│       └── main.py                    # Typer CLI entry point
├── services/                          # Docker service definitions
│   ├── data/
│   │   └── Dockerfile
│   ├── agent-engine/
│   │   └── Dockerfile
│   ├── finrl/
│   │   ├── Dockerfile
│   │   ├── server.py                  # gRPC server
│   │   └── proto/
│   │       └── finrl.proto
│   ├── fingpt/
│   │   ├── Dockerfile
│   │   ├── server.py                  # gRPC server
│   │   └── proto/
│   │       └── fingpt.proto
│   ├── qlib/
│   │   ├── Dockerfile
│   │   ├── server.py                  # gRPC server
│   │   └── proto/
│   │       └── qlib.proto
│   └── execution/
│       └── Dockerfile
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Shared fixtures (mock data, mock brokers)
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_config.py
│   │   ├── test_event_bus.py
│   │   ├── test_data_router.py
│   │   ├── test_agents/
│   │   ├── test_risk/
│   │   ├── test_execution/
│   │   ├── test_strategy/
│   │   └── test_backtest/
│   ├── integration/
│   │   ├── test_openbb.py
│   │   ├── test_alpaca.py
│   │   ├── test_openalgo.py
│   │   ├── test_ccxt.py
│   │   └── test_full_pipeline.py
│   └── fixtures/
│       ├── ohlcv_aapl.json
│       ├── ohlcv_reliance.json
│       ├── ohlcv_btc.json
│       ├── news_samples.json
│       └── agent_signals.json
├── models/                            # Pre-trained models (gitignored, downloaded on setup)
│   ├── finrl/
│   ├── fingpt/
│   └── finbert/
└── scripts/
    ├── setup.sh                       # One-command dev environment setup
    ├── download_models.py             # Download pre-trained models
    └── generate_proto.sh              # Compile .proto files
```

---

## 7. Inter-service communication

| From → To | Protocol | Serialization | Latency target | Purpose |
|-----------|----------|---------------|----------------|---------|
| Any → Redis | Redis protocol | JSON | <1ms | Event publish/subscribe |
| Agent engine → FinRL service | gRPC | Protobuf | <50ms | DRL model inference |
| Agent engine → FinGPT service | gRPC | Protobuf | <100ms | Sentiment inference |
| Agent engine → Qlib service | gRPC | Protobuf | <200ms | Factor computation |
| Agent engine → LLM router | HTTP | JSON | <5s (cloud), <2s (local) | LLM completion requests |
| Execution → Broker APIs | HTTP/WS | JSON | <200ms | Order placement |
| Execution → TradingView | HTTP POST | JSON | <100ms | Webhook relay |
| Web UI → Redis | Redis protocol | JSON | <1ms | Real-time dashboard updates |
