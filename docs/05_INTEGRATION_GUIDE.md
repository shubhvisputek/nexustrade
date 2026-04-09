# NexusTrade — Step-by-step integration guide

> **Version:** 1.0  
> **Purpose:** Phase-by-phase instructions for building NexusTrade from a blank repo. Each step has clear inputs, outputs, verification criteria, and dependencies. Claude Code should execute these steps sequentially — each step's output feeds the next step's input.  
> **Critical rule:** After completing each step, run the specified verification tests. Do NOT proceed to the next step until all tests pass.

---

## Phase 0: Project initialization (Day 1)

### Step 0.1: Create repo structure

**Input:** Empty directory.  
**Action:** Create the complete directory structure from ARCHITECTURE.md Section 6. Create all `__init__.py` files. Create empty placeholder files for all modules listed.  
**Output:** Complete directory tree with all folders and empty Python files.  
**Verify:** `find src/nexustrade -name "*.py" | wc -l` returns expected count. `python -c "import nexustrade"` succeeds.

### Step 0.2: Setup pyproject.toml

**Input:** TECH_STACK.md Section 4.  
**Action:** Create `pyproject.toml` with all dependencies, optional groups, entry_points, tool configs (ruff, mypy, pytest). Use the exact version pins from TECH_STACK.md.  
**Output:** Valid pyproject.toml.  
**Verify:** `uv sync` succeeds. `uv sync --extra agents --extra data --extra execution` succeeds. `nexus --help` shows CLI commands (even if they don't do anything yet).

### Step 0.3: Setup Docker Compose

**Input:** ARCHITECTURE.md Section 5 (container map) and TECH_STACK.md Section 5.  
**Action:** Create `docker-compose.yml` with all 9 services. Create Dockerfiles for each service in `services/`. Create `docker-compose.cpu-only.yml` that excludes GPU services.  
**Output:** Docker Compose files.  
**Verify:** `docker compose config` validates without errors. `docker compose --profile cpu-only up redis` starts Redis successfully.

### Step 0.4: Create test fixtures

**Input:** Create sample market data for testing.  
**Action:** Create JSON fixtures in `tests/fixtures/`: AAPL OHLCV (50 daily bars), RELIANCE OHLCV (50 daily bars), BTC/USDT OHLCV (50 hourly bars), EUR/USD OHLCV (50 4H bars), sample news items (10), sample agent signals (5 different agents). Create `tests/conftest.py` with pytest fixtures loading these files.  
**Output:** Test fixtures and conftest.py.  
**Verify:** `pytest tests/ --collect-only` discovers fixtures without errors.

### Step 0.5: Setup config examples

**Input:** ARCHITECTURE.md Section 5 (configuration schema).  
**Action:** Create `config/default.yaml` with ALL configuration options and sensible defaults. Create all example configs in `config/examples/`. Create empty Jinja2 template files in `config/prompts/`.  
**Output:** Complete config directory.  
**Verify:** Python script loads default.yaml and validates with Pydantic model. All required fields present.

---

## Phase 1: Core foundation (Weeks 1-2)

### Step 1.1: Implement core data models

**Input:** ARCHITECTURE.md Section 2 (all data models).  
**Action:** Implement ALL data models in `src/nexustrade/core/models.py`: OHLCV, Quote, NewsItem, TechnicalIndicators, AgentSignal, MarketContext, CompositeSignal, Order, Fill, Position, PortfolioState, RiskAssessment, Event. Add validation (confidence 0-1, UTC timestamps, valid enum values). Add serialization methods (to_dict, from_dict) for Redis event bus.  
**Output:** `core/models.py` with all models.  
**Verify:** Tests in `tests/unit/test_models.py`:
- Create OHLCV with valid data → succeeds
- Create OHLCV with non-UTC timestamp → raises error
- Create AgentSignal with confidence=1.5 → raises error
- Serialize AgentSignal to dict and back → data preserved
- Create Order with all fields → succeeds
- Test all enum values for SignalDirection, OrderSide, OrderType

### Step 1.2: Implement abstract interfaces

**Input:** ARCHITECTURE.md Section 3 (all ABCs).  
**Action:** Implement ALL abstract interfaces in `src/nexustrade/core/interfaces.py`: DataProviderInterface, BrokerBackendInterface, AgentInterface, NotificationAdapter, RiskModelInterface, StrategyInterface. Add docstrings explaining each method's contract.  
**Output:** `core/interfaces.py` with all ABCs.  
**Verify:** Tests:
- Create concrete class implementing DataProviderInterface with only required methods → succeeds
- Call optional method → returns default
- Create concrete class missing required method → TypeError on instantiation

### Step 1.3: Implement configuration system

**Input:** ARCHITECTURE.md Section 5 (config schema), config/default.yaml.  
**Action:** Implement `src/nexustrade/core/config.py` with all Pydantic models. Load from YAML → env vars → CLI flags. Support `NEXUS__` prefix for env vars with `__` nesting delimiter.  
**Output:** `core/config.py` with NexusTradeConfig and all sub-models.  
**Verify:** Tests in `tests/unit/test_config.py`:
- Load default.yaml → valid NexusTradeConfig
- Set `NEXUS__LLM__MODE=local` env var → overrides YAML value
- Missing required field → clear error message listing the field
- Invalid enum value → Pydantic validation error
- Nested config access: `config.llm.fast.model` returns expected string

### Step 1.4: Implement event bus

**Input:** ARCHITECTURE.md Section 4 (event schemas), Section 7 (inter-service communication).  
**Action:** Implement `src/nexustrade/core/events.py`: `AsyncEventBus` class wrapping Redis Streams. Methods: `publish(stream, event)`, `subscribe(stream, group, callback)`, `acknowledge(stream, group, event_id)`. Use `redis.asyncio` for async operations. Consumer groups for multi-service consumption.  
**Output:** `core/events.py`.  
**Verify:** Tests in `tests/unit/test_event_bus.py` (requires Redis running):
- Publish event → subscriber receives it
- Publish 100 events → all received in order
- Consumer group prevents duplicate processing
- Event serialization round-trip preserves data

### Step 1.5: Implement adapter registry

**Input:** ARCHITECTURE.md Section 3 (interfaces), TECH_STACK.md Section 4 (entry_points).  
**Action:** Implement `src/nexustrade/core/registry.py`: `AdapterRegistry` class that discovers data providers, brokers, agents, and notification channels via `importlib.metadata.entry_points()`. Methods: `discover_all()`, `get_data_provider(name)`, `get_broker(name)`, `get_agent(name)`, `get_best_provider_for(market)`, `get_broker_for_market(market)`.  
**Output:** `core/registry.py`.  
**Verify:** Tests:
- Register mock entry_point → registry discovers it
- Request unknown provider → raises KeyError with helpful message
- `get_broker_for_market("india_equity")` → returns OpenAlgo backend (when registered)

### Step 1.6: Implement CLI skeleton

**Input:** PRD F-UX-002 (CLI spec).  
**Action:** Implement `src/nexustrade/cli/main.py` with Typer: commands for `trade`, `backtest`, `paper`, `agents list`, `plugins list`, `webhook start`, `health`. Each command loads config, initializes registry, and performs its action. For now, commands can print "Not yet implemented" for unfinished features.  
**Output:** Working CLI.  
**Verify:** `nexus --help` shows all commands. `nexus agents list` runs without crash (even if output is empty).

**Phase 1 verification:** `pytest tests/unit/ -v` — ALL core tests pass.

---

## Phase 2: Data layer (Weeks 2-3)

### Step 2.1: Implement data routing

**Input:** PRD F-DAT-006 (smart routing), config schema.  
**Action:** Implement `src/nexustrade/data/router.py`: `DataRouter` class reads routing config (market → provider priority list), selects best available provider via health checks, falls back on failure.  
**Verify:** Unit tests with mock providers: healthy provider selected, unhealthy → fallback.

### Step 2.2: Implement OpenBB adapter

**Input:** PRD F-DAT-002, FEATURE_SOURCING.md (OpenBB reference).  
**Action:** Implement `src/nexustrade/data/adapters/openbb_adapter.py`: wrap OpenBB's `obb.equity.price.historical()`, `obb.currency.price.historical()`, etc. Convert OpenBB outputs to canonical OHLCV. Handle sub-provider selection from config.  
**Verify:** Integration test (requires OpenBB + FMP API key): fetch AAPL daily 2024 → >=250 OHLCV bars.

### Step 2.3: Implement CCXT data adapter

**Input:** PRD F-DAT-005, FEATURE_SOURCING.md (CCXT reference).  
**Action:** Implement `src/nexustrade/data/adapters/ccxt_data.py`: wrap CCXT's `exchange.fetch_ohlcv()` and `exchange.watch_ticker()`. Convert CCXT array format to canonical OHLCV.  
**Verify:** Integration test: fetch BTC/USDT 1H from Binance → valid OHLCV bars.

### Step 2.4: Implement TradingView MCP adapter

**Input:** PRD F-DAT-003, FEATURE_SOURCING.md (3 TV MCP servers).  
**Action:** Implement `src/nexustrade/data/adapters/tradingview_mcp.py`: connect to TV MCP servers as MCP client. Implement `get_technicals()`, `get_chart_image()`, and `screen()`. Handle MCP connection management.  
**Verify:** Integration test (requires TV MCP server running): get AAPL technicals → RSI, MACD values present.

### Step 2.5: Implement broker data adapter

**Input:** PRD F-DAT-004, FEATURE_SOURCING.md (OpenAlgo).  
**Action:** Implement `src/nexustrade/data/adapters/broker_data.py`: fetch historical candles and real-time quotes from OpenAlgo's data endpoints via httpx.  
**Verify:** Integration test (requires OpenAlgo running): fetch RELIANCE daily data.

### Step 2.6: Implement Yahoo Finance adapter

**Input:** Fallback adapter, minimal implementation.  
**Action:** Implement `src/nexustrade/data/adapters/yahoo.py`: wrap yfinance for OHLCV and basic fundamentals. This is the no-API-key fallback.  
**Verify:** Unit test: fetch AAPL data → valid OHLCV (no API key needed).

### Step 2.7: Implement data caching

**Input:** PRD F-DAT-007.  
**Action:** Implement `src/nexustrade/data/cache.py`: 3-level cache (memory LRU → Redis → disk). Configurable TTL per data type from config.  
**Verify:** Unit tests: same request twice → provider called once. After TTL → provider called again. Cache disabled → always calls provider.

**Phase 2 verification:** `nexus trade --config examples/us_equities_basic.yaml --dry-run` fetches AAPL data and prints it.

---

## Phase 3: Agent engine (Weeks 3-5)

### Step 3.1: Implement prompt loader

**Action:** Implement `src/nexustrade/agents/prompt_loader.py`: load Jinja2 templates from `config/prompts/`, render with MarketContext variables, support hot-reload (check file mtime).  
**Verify:** Load template, render with mock data, modify file, verify next render uses updated template.

### Step 3.2: Implement LLM router

**Input:** PRD F-LLM-001 through F-LLM-004.  
**Action:** Implement `src/nexustrade/llm/router.py`: `LLMRouter` with `complete(messages, channel, **params)`. Routes to fast/deep/vision based on channel. Uses LiteLLM for actual API calls. Per-agent overrides applied. Fallback chain on failure.  
**Verify:** Mock LiteLLM: fast channel → Ollama model string, deep channel → Anthropic model string. Fallback works on error.

### Step 3.3: Implement ai-hedge-fund agent adapters

**Input:** PRD F-AGT-002, FEATURE_SOURCING.md.  
**Action:** Implement `src/nexustrade/agents/adapters/ai_hedge_fund.py`: create adapter for EACH of 18 persona agents. Each adapter constructs a prompt from Jinja2 template, calls LLM via router, parses response into AgentSignal. Create all 18 Jinja2 templates in `config/prompts/agents/`.  
**Verify:** Unit test with mock LLM: each agent produces valid AgentSignal. Integration test: run Buffett agent with real LLM on AAPL data.

### Step 3.4: Implement TradingAgents debate adapter

**Input:** PRD F-AGT-003, FEATURE_SOURCING.md.  
**Action:** Implement `src/nexustrade/agents/adapters/trading_agents.py`: bull/bear debate using LangGraph workflow. Configurable rounds. Early termination. Uses deep LLM for synthesis.  
**Verify:** Unit test: mock bull (bullish) + bear (bearish) → manager synthesizes. Test configurable rounds. Test early termination.

### Step 3.5: Implement FinBERT adapter

**Input:** PRD F-AGT-005 (fast path).  
**Action:** Implement `src/nexustrade/agents/adapters/finbert_agent.py`: load ProsusAI/finbert from HuggingFace, classify headlines, aggregate with recency weighting.  
**Verify:** Unit test: "Company beats earnings" → positive. "Massive layoffs" → negative. Aggregation test with multiple headlines.

### Step 3.6: Implement signal aggregator

**Input:** PRD F-AGT-010.  
**Action:** Implement `src/nexustrade/agents/aggregator.py`: 4 modes (weighted_confidence, majority, unanimous, portfolio_manager). Min confidence filtering. Per-agent weight support.  
**Verify:** Unit tests for all 4 modes with various signal combinations.

### Step 3.7: Implement agent executor

**Input:** PRD F-AGT-011.  
**Action:** Implement `src/nexustrade/agents/executor.py`: parallel (asyncio.gather), sequential (ordered loop), DAG (dependency resolution + conditional execution).  
**Verify:** DAG test: agent_b depends on agent_a. agent_a returns SELL → agent_b skipped.

### Step 3.8: Implement ChromaDB memory

**Input:** PRD F-AGT-008.  
**Action:** Implement `src/nexustrade/agents/memory.py`: store market situations in ChromaDB, query similar situations, enforce retention policy.  
**Verify:** Store situation → query similar → verify retrieval. Test retention pruning.

**Phase 3 verification:** Full agent pipeline on AAPL: data → 3 agents (Buffett + debate + FinBERT) → aggregated signal. Print result.

---

## Phase 4: Risk engine (Weeks 5-6)

### Step 4.1: Implement pre-trade checks

**Input:** PRD F-RSK-001.  
**Action:** Implement `src/nexustrade/risk/pre_trade.py`: max position size, max portfolio risk, market hours, India circuit limits, F&O lot size validation.  
**Verify:** All unit tests from PRD spec.

### Step 4.2: Implement position sizing models

**Input:** PRD F-RSK-003.  
**Action:** Implement 5 models in `src/nexustrade/risk/sizing/`: CVaR, Kelly, fixed_fraction, volatility, max_drawdown. Each implements RiskModelInterface.  
**Verify:** Unit tests with known inputs → known outputs for each model.

### Step 4.3: Implement circuit breakers

**Input:** PRD F-RSK-004.  
**Action:** Implement `src/nexustrade/risk/circuit_breaker.py`: daily loss limit, consecutive loss limit, open position limit, cooldown timer, manual override.  
**Verify:** All unit tests from PRD spec.

### Step 4.4: Implement risk debate

**Input:** PRD F-RSK-002, FEATURE_SOURCING.md (TradingAgents).  
**Action:** Implement `src/nexustrade/risk/debate.py`: 3-perspective risk assessment using LangGraph.  
**Verify:** Mock three risk agents → manager produces RiskAssessment.

### Step 4.5: Implement India-specific rules

**Input:** PRD F-RSK-005.  
**Action:** Implement `src/nexustrade/risk/india_rules.py`: circuit limit checking, rate limiting, SEBI audit trail, session restrictions.  
**Verify:** All unit tests from PRD spec.

### Step 4.6: Implement risk engine pipeline

**Input:** All risk components.  
**Action:** Implement `src/nexustrade/risk/engine.py`: orchestrate pre-trade → debate → sizing → circuit breaker check. Produce final RiskAssessment.  
**Verify:** E2E: composite signal → risk engine → approved/rejected with position size.

**Phase 4 verification:** Signal → risk engine → approved order with stop-loss and take-profit.

---

## Phase 5: Execution engine (Weeks 6-8)

### Step 5.1: Implement paper trading backend

**Input:** PRD F-EXE-008.  
**Action:** Implement `src/nexustrade/execution/backends/paper.py`: in-memory position tracking, configurable slippage models, commission calculation, PnL tracking.  
**Verify:** Buy + sell cycle → correct PnL. Slippage applied. Commission deducted.

### Step 5.2: Implement Alpaca backend

**Input:** PRD F-EXE-003.  
**Action:** Implement `src/nexustrade/execution/backends/alpaca.py`: wrap alpaca-py for order placement, position retrieval, account info.  
**Verify:** Integration test on Alpaca paper: place order → verify fill.

### Step 5.3: Implement OpenAlgo backend

**Input:** PRD F-EXE-002, FEATURE_SOURCING.md.  
**Action:** Implement `src/nexustrade/execution/backends/openalgo.py`: HTTP client for OpenAlgo REST API. Handle authentication, error responses, rate limiting.  
**Verify:** Integration test with OpenAlgo + Dhan sandbox: place order → verify response.

### Step 5.4: Implement CCXT broker backend

**Input:** PRD F-EXE-004.  
**Action:** Implement `src/nexustrade/execution/backends/ccxt_broker.py`: wrap CCXT's `create_order()`, `cancel_order()`, `fetch_positions()`.  
**Verify:** Integration test on Binance testnet: place limit order → verify.

### Step 5.5: Implement TradingView webhook

**Input:** PRD F-EXE-006.  
**Action:** Implement `src/nexustrade/execution/webhooks.py`: FastAPI endpoint at `/webhook`, HMAC passphrase validation, payload parsing, routing to broker backend.  
**Verify:** Unit test: valid webhook → order routed. Invalid passphrase → 401.

### Step 5.6: Implement execution router

**Input:** PRD F-EXE-007.  
**Action:** Implement `src/nexustrade/execution/engine.py`: reads `execution.mode` config, routes to TradingView path, Python path, or both. Maps market → broker backend.  
**Verify:** Mode=both → both paths called. Mode=python → only broker API. Mode=tradingview → only webhook.

**Phase 5 verification:** Full pipeline: data → agents → risk → paper execution → fill confirmation logged. `nexus paper --config examples/us_equities_basic.yaml` runs a complete cycle.

---

## Phase 6: Strategy & backtesting (Weeks 8-9)

### Step 6.1: Implement strategy parser

**Input:** PRD F-BKT-002 (YAML strategy spec).  
**Action:** Implement `src/nexustrade/strategy/parser.py`: parse YAML strategy definitions. Validate conditions, agent references, indicator references.  
**Verify:** Parse example YAML → valid strategy object. Invalid YAML → clear error.

### Step 6.2: Implement strategy engine

**Input:** PRD F-BKT-002.  
**Action:** Implement `src/nexustrade/strategy/engine.py`: evaluate entry/exit conditions against MarketContext + agent signals. Hot-reload strategy YAML.  
**Verify:** Mock conditions: all met → entry=True. One fails → entry=False. Exit conditions tested.

### Step 6.3: Implement backtest engine

**Input:** PRD F-BKT-001.  
**Action:** Implement `src/nexustrade/backtest/engine.py`: historical replay using data from DataProviderInterface. Run full pipeline for each decision point. Track positions, PnL.  
**Verify:** Backtest buy-and-hold AAPL 2024 → return matches actual.

### Step 6.4: Implement backtest metrics

**Action:** Implement `src/nexustrade/backtest/metrics.py`: Sharpe ratio, max drawdown, win rate, profit factor, annualized return, average holding period, total trades.  
**Verify:** Known return series → known Sharpe/drawdown values.

**Phase 6 verification:** `nexus backtest --strategy examples/strategy_basic.yaml --from 2024-01-01 --to 2024-12-31` produces report with all metrics.

---

## Phase 7: Notifications & scheduling (Weeks 9-10)

### Step 7.1: Implement notification adapters

**Action:** Implement Telegram, Discord, Email, Webhook notification adapters in `src/nexustrade/notifications/`.  
**Verify:** Unit tests with mocked APIs. Rate limiting test.

### Step 7.2: Implement scheduler

**Action:** Implement `src/nexustrade/scheduler/engine.py`: cron-based, interval-based, and market-session-based scheduling. Timezone-aware.  
**Verify:** 15-min interval triggers correctly. NSE open (9:15 IST) triggers at correct UTC.

---

## Phase 8: ML services (Weeks 10-11)

### Step 8.1: Implement FinRL gRPC service

**Action:** Define `services/finrl/proto/finrl.proto`, implement gRPC server in `services/finrl/server.py`, implement client in agent adapter. Build Docker container.  
**Verify:** gRPC call with observation vector → prediction returned.

### Step 8.2: Implement FinGPT gRPC service

**Action:** Define proto, implement server and client. Build Docker container with GPU support.  
**Verify:** gRPC call with text → sentiment prediction returned.

### Step 8.3: Implement Qlib gRPC service

**Action:** Define proto, implement server and client. Build Docker container.  
**Verify:** gRPC call with symbol + date range → Alpha158 factors returned.

---

## Phase 9: Web UI & observability (Weeks 11-12)

### Step 9.1: Implement Streamlit dashboard

**Action:** Implement `src/nexustrade/web/dashboard.py`: portfolio panel, signals panel, trade history, risk status, system health.  
**Verify:** Dashboard loads. Shows mock data from Redis.

### Step 9.2: Implement REST API

**Action:** Implement FastAPI endpoints in `src/nexustrade/web/api/`: signals, portfolio, config, health.  
**Verify:** All endpoints return correct data. Health check returns all service statuses.

### Step 9.3: Implement observability

**Action:** Implement structured logging, trade audit trail (JSON format), optional Prometheus metrics export.  
**Verify:** Trade execution → audit log entry written. Log levels filter correctly.

---

## Phase 10: Integration testing & hardening (Week 12)

### Step 10.1: Full E2E test suite

**Action:** Write comprehensive integration tests in `tests/integration/`:
- `test_full_pipeline.py`: data → agents → risk → paper execution for each market (US, India, crypto, forex).
- `test_multi_market.py`: simultaneous AAPL + RELIANCE + BTC/USDT + EUR/USD pipeline.
- `test_config_swap.py`: change broker, LLM, agent via config → verify behavior changes.
- `test_circuit_breaker.py`: simulate losses → verify halt → verify cooldown → verify resume.
- `test_backtest_accuracy.py`: backtest known strategy → verify metrics match expected.

### Step 10.2: Docker Compose full stack test

**Action:** `docker compose up` → verify all 9 services start → health checks pass → run paper trading cycle through all services.

### Step 10.3: Documentation

**Action:** Write README.md with: project overview, quickstart guide, configuration reference, architecture overview, and links to these design docs.

---

## Completion checklist

- [ ] All core data models with validation
- [ ] All abstract interfaces (6 ABCs)
- [ ] Configuration system (4 layers + Pydantic)
- [ ] Event bus (Redis Streams)
- [ ] Adapter registry (entry_points discovery)
- [ ] Data adapters: OpenBB, TradingView MCP, CCXT, Broker Data, Yahoo
- [ ] Smart data routing with fallback
- [ ] Data caching (3 levels)
- [ ] 18 investor persona agent adapters
- [ ] Bull/bear debate adapter
- [ ] FinBERT sentiment adapter
- [ ] Signal aggregator (4 modes)
- [ ] Agent executor (parallel/sequential/DAG)
- [ ] ChromaDB market memory
- [ ] LLM router (fast/deep/vision channels)
- [ ] Prompt template system (Jinja2 + hot-reload)
- [ ] Risk pre-trade checks
- [ ] 5 position sizing models
- [ ] Circuit breakers
- [ ] Risk debate (3-perspective)
- [ ] India-specific risk rules
- [ ] Paper trading backend with slippage
- [ ] Alpaca backend
- [ ] OpenAlgo backend
- [ ] CCXT broker backend
- [ ] TradingView webhook receiver
- [ ] Execution router (TV/Python/Both)
- [ ] Strategy YAML parser + engine
- [ ] Backtesting engine + metrics
- [ ] Notification adapters (Telegram, Discord, Email, Webhook)
- [ ] Scheduler (cron + interval + session-based)
- [ ] FinRL gRPC service + Docker
- [ ] FinGPT gRPC service + Docker
- [ ] Qlib gRPC service + Docker
- [ ] Streamlit dashboard
- [ ] REST API (FastAPI)
- [ ] Observability (logging, audit trail)
- [ ] Docker Compose (9 services)
- [ ] CLI commands (trade, backtest, paper, agents, plugins, webhook, health)
- [ ] Unit tests for ALL features
- [ ] Integration tests for ALL markets
- [ ] E2E tests for full pipeline
- [ ] README.md and documentation
