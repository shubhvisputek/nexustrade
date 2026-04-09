# NexusTrade — Feature sourcing map

> **Version:** 1.0  
> **Purpose:** For each NexusTrade feature, this document specifies: which open-source project it originates from, the exact source files/modules to reference, the extraction/adaptation approach, what must be built from scratch, and the estimated effort. Claude Code should use this to decide whether to study an existing codebase (reference) or design from scratch (build).  
> **Key principle:** NEVER copy code directly. Study the source project's approach, understand its patterns, then implement NexusTrade's own clean version behind the universal interfaces defined in the PRD.

---

## 1. Sourcing categories

Each feature falls into one of three categories:

| Category | Meaning | Claude Code action |
|----------|---------|-------------------|
| **REFERENCE** | An OSS project has a complete, working implementation. Study its architecture and patterns, then build NexusTrade's version behind our interfaces. | Study the referenced source files. Understand the data flow, error handling, and edge cases. Implement a clean version that conforms to NexusTrade's AgentInterface/BrokerBackendInterface/DataProviderInterface. |
| **ADAPT** | An OSS project has a partial solution. The core logic exists but needs extension, configuration support, or interface wrapping. | Study the referenced source files for the core logic. Extend with the specified missing capabilities. Wrap behind NexusTrade interfaces. |
| **BUILD** | No OSS project solves this. Design and implement from scratch based on the PRD specification. | Follow the PRD spec exactly. Design the implementation, write tests, integrate with the event bus and config system. |

---

## 2. Feature sourcing table

### Markets & assets

| Feature ID | Feature | Source | Project | Key source references | Approach | Notes |
|-----------|---------|--------|---------|----------------------|----------|-------|
| F-MKT-001 | US equities | REFERENCE | OpenBB + Alpaca | OpenBB: `openbb_equity` extension. Alpaca: `alpaca-py` SDK `TradingClient`, `StockHistoricalDataClient` | Study OpenBB's Fetcher pattern for data. Study alpaca-py's order submission flow. Build NexusTrade adapters. | OpenBB handles data, Alpaca handles execution. Both have clean Python APIs. |
| F-MKT-002 | Indian equities | REFERENCE | OpenAlgo | GitHub: `marketcalls/openalgo`. Key files: `broker/zerodha/api/`, `broker/dhan/api/`, `restx_api/placeorder.py`, `utils/common_symbol.py` | Study OpenAlgo's unified API layer. NexusTrade's OpenAlgoBackend calls OpenAlgo's REST endpoints — do NOT reimplement broker-specific logic. | OpenAlgo is a SEPARATE running service. NexusTrade is a CLIENT of OpenAlgo. User installs and runs OpenAlgo independently. |
| F-MKT-003 | Forex | ADAPT | OpenBB + TradingView MCP | OpenBB: `openbb_currency` extension. TradingView MCP: `atilaahmettaner/tradingview-mcp` for live technicals, `fiale-plus/tradingview-mcp-server` for screening | OpenBB provides OHLCV. TradingView MCP provides pre-computed indicators. Execution via TradingView webhooks. No single project covers the full forex pipeline — combine. | Forex execution is the least solved area. TradingView webhook relay is the primary execution path for forex. |
| F-MKT-004 | Crypto | REFERENCE | CCXT + OctoBot | CCXT: `ccxt` PyPI package, unified API. OctoBot: `drakkar-software/OctoBot`, exchange connector patterns in `octobot/exchanges/` | Study CCXT's unified exchange interface for data + execution. Study OctoBot's exchange connector architecture for WebSocket patterns. | CCXT is the de facto standard. Its unified API is the model for NexusTrade's crypto support. |
| F-MKT-005 | Options | ADAPT | OpenBB + IB | OpenBB: `openbb_derivatives` extension. IB: `ib_insync` library | Study OpenBB for options chain data. Study ib_insync for multi-leg order construction. Build options-specific logic. | Complex order types (spreads, straddles) need custom logic on top of IB's API. |
| F-MKT-006 | Commodities | ADAPT | OpenBB + IB | OpenBB: `openbb_commodity` extension. | Study OpenBB for commodity data. Execution via IB or TradingView webhooks for MCX. | Lower priority — data is available but execution paths are limited. |
| F-MKT-007 | Multi-market simultaneous | BUILD | None | No project supports multi-market in one system with per-market routing. | Design the execution router that maps market → broker backend. Use Python asyncio for concurrent analysis. | This is the integration layer — the individual market supports are referenced above, but combining them is new. |

### AI & agents

| Feature ID | Feature | Source | Project | Key source references | Approach | Notes |
|-----------|---------|--------|---------|----------------------|----------|-------|
| F-AGT-001 | Universal agent interface | BUILD | None (inspired by ai-hedge-fund) | ai-hedge-fund: `src/graph/state.py` (AgentState TypedDict), agent function signatures | Study ai-hedge-fund's agent state pattern. Design NexusTrade's own AgentInterface ABC + AgentSignal dataclass. Make it more generic to support non-LLM agents (RL, NLP). | The ABC design is in the PRD. Key difference from ai-hedge-fund: NexusTrade's interface must accommodate RL agents and NLP models, not just LLM prompt-response agents. |
| F-AGT-002 | Investor persona agents | REFERENCE | ai-hedge-fund (virattt) | GitHub: `virattt/ai-hedge-fund`. Agent files: `src/agents/warren_buffett.py`, `src/agents/charlie_munger.py`, etc. (18 files, one per agent). LLM factory: `src/utils/llm.py`. Tools: `src/tools/api.py` | Study each agent's prompt structure, what data it requests, and how it produces signals. Build NexusTrade adapters that: (1) construct MarketContext → ai-hedge-fund-style state, (2) call the agent logic, (3) translate output → AgentSignal. | Each agent is a single function that takes state and returns a signal. The prompts are the valuable IP — study them to understand each investor's analytical framework. Do NOT copy prompts verbatim — write NexusTrade's own Jinja2 templates inspired by the same analytical frameworks. |
| F-AGT-003 | Bull/bear debate | REFERENCE | TradingAgents (TauricResearch) | GitHub: `TauricResearch/TradingAgents`. Key files: `tradingagents/agents/research/bull_researcher.py`, `bear_researcher.py`, `research_manager.py`. LangGraph workflow: `tradingagents/graph/trading_graph.py` | Study the debate mechanism: how bull/bear researchers receive the same data, produce opposing arguments, and how the manager synthesizes. Build NexusTrade's version with configurable rounds. | TradingAgents uses LangGraph for the debate workflow. NexusTrade should also use LangGraph but with configurable round counts and early termination. |
| F-AGT-004 | DRL trading agents | REFERENCE | FinRL | GitHub: `AI4Finance-Foundation/FinRL`. Key files: `finrl/agents/stablebaselines3/models.py`, `finrl/meta/env_stock_trading/env_stocktrading.py`. Also: FinRL-DeepSeek paper for LLM+RL integration. | Study FinRL's observation vector construction and action-to-trade mapping. Build NexusTrade's FinRLAdapter that: loads SB3 model, constructs obs from MarketContext, calls predict(), maps action → AgentSignal. | FinRL models are .zip files loaded with `PPO.load()`. The adapter is thin — the complexity is in observation vector construction. |
| F-AGT-005 | Sentiment (FinBERT+FinGPT) | REFERENCE | FinBERT (ProsusAI) + FinGPT (AI4Finance) | FinBERT: HuggingFace `ProsusAI/finbert`. FinGPT: GitHub `AI4Finance-Foundation/FinGPT`, adapters in `fingpt/FinGPT_Others/`. | FinBERT: 3-line integration — load model, tokenize, softmax. FinGPT: load base + LoRA adapter via PeftModel. Build sentiment adapter that aggregates multiple headlines with recency weighting. | FinBERT is trivial to integrate. FinGPT requires GPU and specific model+adapter pairing. |
| F-AGT-006 | Vision chart analysis | REFERENCE | QuantAgent | GitHub: `Y-Research-SBU/QuantAgent`. Pattern recognition logic in agent files. | Study QuantAgent's approach: generate chart image → send to vision LLM → parse pattern response. Build NexusTrade's adapter combining TradingView MCP chart screenshots with vision LLM analysis. | QuantAgent uses matplotlib for chart generation. NexusTrade should prefer TradingView MCP screenshots (more realistic, include indicators). |
| F-AGT-007 | Auto factor mining | REFERENCE | Qlib + RD-Agent | Qlib: GitHub `microsoft/qlib`. Expressions: `qlib/data/ops.py`. Alpha158: `qlib/contrib/data/handler.py`. RD-Agent: GitHub `microsoft/RD-Agent`, quant scenarios. | Study Qlib's expression DSL for factor computation. Study RD-Agent's propose→implement→evaluate loop. Build adapter that runs Qlib factors and converts to signals. | Qlib has its own binary data format. The adapter must convert canonical OHLCV → Qlib format. |
| F-AGT-008 | Market memory | REFERENCE | TradingAgents | TradingAgents: memory system in `tradingagents/agents/utils/agent_utils.py`, ChromaDB integration | Study how TradingAgents stores and retrieves market situations. Build NexusTrade's memory module with configurable retention and similarity threshold. | ChromaDB is the storage backend. Add retention policy (time-based pruning) which TradingAgents lacks. |
| F-AGT-009 | Heterogeneous ensemble | BUILD | None | No project combines LLM+RL+NLP+Vision agents | Design the ensemble that runs different agent paradigms and normalizes their outputs. Key challenge: confidence calibration across paradigms (LLM confidence 0.8 ≠ RL action magnitude 0.8). | Unique to NexusTrade. Must design confidence normalization. |
| F-AGT-010 | Signal aggregation | ADAPT | ai-hedge-fund | ai-hedge-fund: `src/graph/portfolio_manager.py` for portfolio-manager-decides mode. | Study ai-hedge-fund's portfolio manager agent. Build 4 aggregation modes: weighted_confidence (new), majority (new), unanimous (new), portfolio_manager (adapted). | ai-hedge-fund only has portfolio_manager mode. The other 3 modes are new. |
| F-AGT-011 | Agent execution order | BUILD | None (LangGraph supports it) | LangGraph docs: conditional edges, state-based routing | Design DAG executor using LangGraph's conditional edges. No trading project implements this. | Use LangGraph's built-in conditional routing. The innovation is the config-driven DAG definition. |

### LLM configuration

| Feature ID | Feature | Source | Project | Key source references | Approach | Notes |
|-----------|---------|--------|---------|----------------------|----------|-------|
| F-LLM-001 | Multi-provider routing | REFERENCE | ai-hedge-fund + LiteLLM | ai-hedge-fund: `src/utils/llm.py` (model factory supporting 13 providers). LiteLLM: PyPI `litellm` | Study ai-hedge-fund's model factory for the provider switching pattern. Use LiteLLM as the underlying unified API. Build NexusTrade's LLMRouter with 3 channels. | ai-hedge-fund's `get_model()` function is the best reference for multi-provider support. LiteLLM handles the API formatting. |
| F-LLM-002 | Local LLM (Ollama) | REFERENCE | TradingAgents + ai-hedge-fund | Both support Ollama via LiteLLM's `ollama/` prefix | Standard LiteLLM Ollama integration. Nothing novel needed. | Ollama must be running separately. Connection via `base_url` config. |
| F-LLM-003 | Hybrid mode | ADAPT | TradingAgents | TradingAgents: `quick_think_llm` + `deep_think_llm` dual-LLM config | Study TradingAgents' dual-LLM approach. Extend to 3 channels (add vision). Add mode config (local/cloud/hybrid). | TradingAgents has the concept but not the full 3-mode configurability. |
| F-LLM-004 | Per-agent LLM params | ADAPT | ai-hedge-fund + TradingAgents | ai-hedge-fund: per-agent model override in config. TradingAgents: per-agent LLM assignment. | Both have per-agent model selection. Extend with temperature/top_p/max_tokens per agent. | LiteLLM passes all params through natively. Just need the config schema extension. |
| F-LLM-005 | Prompt templates | BUILD | None (prompts exist in projects but not as templates) | ai-hedge-fund: prompts as Python strings in agent files. TradingAgents: prompts in agent .py files. | Extract prompt patterns from both projects. Convert to Jinja2 templates. Design template loading + hot-reload system. | Study the prompts to understand analytical frameworks, then write templates inspired by them. |
| F-LLM-006 | LoRA fine-tuned models | REFERENCE | FinGPT | FinGPT: `fingpt/FinGPT_Others/fingpt-mt/` for multi-task, `fingpt/FinGPT-v3/` for v3 | Study FinGPT's adapter loading pattern. Build thin wrapper for PeftModel loading and inference. | FinGPT models are on HuggingFace. The integration is standard HF + PEFT. |

### Data sources

| Feature ID | Feature | Source | Project | Key source references | Approach | Notes |
|-----------|---------|--------|---------|----------------------|----------|-------|
| F-DAT-001 | Data provider interface | BUILD | Inspired by OpenBB | OpenBB: Provider interface in `openbb_core/provider/abstract/fetcher.py` | Study OpenBB's Fetcher ABC pattern (query → extract → transform). Design NexusTrade's own DataProviderInterface that's simpler (no query model, just method args). | OpenBB's Fetcher is over-engineered for our needs. Simplify to direct method calls. |
| F-DAT-002 | OpenBB adapter | REFERENCE | OpenBB | OpenBB: `openbb` PyPI package. Python client: `from openbb import obb` | Standard OpenBB Python SDK usage. Wrap `obb.equity.price.historical()`, `obb.currency.price.historical()`, etc. behind DataProviderInterface. | OpenBB handles all sub-provider routing internally. Our adapter just calls obb methods. |
| F-DAT-003 | TradingView MCP adapter | ADAPT | Multiple TV MCP projects | `atilaahmettaner/tradingview-mcp` (technicals), `ertugrul59/tradingview-chart-mcp` (chart images), `fiale-plus/tradingview-mcp-server` (screener) | Study all three MCP servers' tool schemas. Build NexusTrade adapter that connects to each as an MCP client and maps responses to our data models. | The 3 TV MCP servers run as separate processes. NexusTrade connects as an MCP client. |
| F-DAT-004 | Broker data adapter | REFERENCE | OpenAlgo | OpenAlgo: historical data API, WebSocket via ZeroMQ | Study OpenAlgo's data endpoints (`/api/v1/history`, WebSocket). Build data adapter that fetches from OpenAlgo. | Same OpenAlgo instance serves both data and execution. |
| F-DAT-005 | CCXT data adapter | REFERENCE | CCXT | CCXT: `ccxt` PyPI. Unified API: `exchange.fetch_ohlcv()`, `exchange.watch_ticker()` | Standard CCXT usage. Convert CCXT array format to canonical OHLCV. | CCXT is very well documented. Straightforward adapter. |
| F-DAT-006 | Smart routing | BUILD | None (inspired by OpenBB's provider routing) | OpenBB routes between sub-providers internally, but not across provider types | Design routing engine that picks best provider per market/data-type. Use config priority lists with fallback. | New design. The routing config pattern is defined in the PRD. |
| F-DAT-007 | Data caching | ADAPT | Qlib + OpenBB | Qlib: multi-level cache in data module. OpenBB: per-provider TTL caching | Study Qlib's memory→disk cache pattern. Study OpenBB's TTL approach. Build NexusTrade's 3-level cache (memory→Redis→disk) with configurable TTL per data type. | Qlib's binary cache is fast for historical replay (backtesting). Redis cache is better for live data. |

### Execution

| Feature ID | Feature | Source | Project | Key source references | Approach | Notes |
|-----------|---------|--------|---------|----------------------|----------|-------|
| F-EXE-001 | Broker backend interface | BUILD | Inspired by CCXT + OpenAlgo | CCXT: unified exchange methods. OpenAlgo: unified broker API. | Study both projects' unified interface patterns. Design NexusTrade's BrokerBackendInterface as defined in PRD. | The interface design is in the PRD. |
| F-EXE-002 | OpenAlgo backend | REFERENCE | OpenAlgo | OpenAlgo: REST API docs at `docs.openalgo.in`. Endpoints: `/api/v1/placeorder`, `/api/v1/cancelorder`, `/api/v1/positionbook`, `/api/v1/funds` | Study OpenAlgo's API documentation. Build HTTP client adapter using httpx. | OpenAlgo is a REST service. The adapter is an HTTP client. |
| F-EXE-003 | Alpaca backend | REFERENCE | FinRL + alpaca-py | FinRL: `finrl/meta/broker_api/alpaca/trade_alpaca.py`. Alpaca: `alpaca-py` SDK | Study FinRL's Alpaca integration for the trading loop pattern. Use alpaca-py SDK directly. | alpaca-py is well-documented. Paper + live modes are built-in. |
| F-EXE-004 | CCXT backend | REFERENCE | CCXT + OctoBot | CCXT: `exchange.create_order()`, `exchange.cancel_order()`. OctoBot: exchange adapters in `octobot/exchanges/` | Study CCXT's unified order methods. Study OctoBot's exchange connector for error handling patterns. | CCXT's unified API is the standard approach. |
| F-EXE-005 | IB backend | REFERENCE | ib_insync | `ib_insync` PyPI package: `IB()`, `Stock()`, `Option()`, `Order()` | Study ib_insync's async connection and order management. Build adapter. | IB's API is complex. ib_insync simplifies it significantly. |
| F-EXE-006 | TradingView webhook | ADAPT | OctoBot + OpenAlgo | OctoBot: TradingView integration guide. OpenAlgo: TradingView webhook receiver | Study OctoBot's webhook receiver pattern. Study OpenAlgo's TV integration (they already support TV alerts → broker execution for India). Build NexusTrade's webhook receiver combining both approaches. | OpenAlgo already has production-tested TV → Indian broker flow. |
| F-EXE-007 | Selectable execution mode | BUILD | None | No project offers TV/Python/Both selection | Design execution router with mode config. In "both" mode, fire to both paths simultaneously. Handle duplicate fill prevention. | Unique to NexusTrade. |
| F-EXE-008 | Paper trading + slippage | ADAPT | FinRL + Qlib | FinRL: `StockTradingEnv` — `transaction_cost_pct`, `turbulence_threshold`. Qlib: `CommonInfrastructure` exchange simulator | Study FinRL's transaction cost model. Study Qlib's exchange simulator for slippage. Build NexusTrade's PaperBackend with configurable slippage model selection. | FinRL's model is percentage-based. Add volume-based and fixed models. |

### Risk management

| Feature ID | Feature | Source | Project | Key source references | Approach | Notes |
|-----------|---------|--------|---------|----------------------|----------|-------|
| F-RSK-001 | Pre-trade checks | ADAPT | ai-hedge-fund + OpenAlgo | ai-hedge-fund: risk manager agent. OpenAlgo: circuit limit data, rate limiting | Study ai-hedge-fund's risk checks. Study OpenAlgo's instrument data for circuit limits. Build comprehensive pre-trade validation. | India-specific checks (circuit limits, lot sizes) come from OpenAlgo's instrument database. |
| F-RSK-002 | Risk debate | REFERENCE | TradingAgents | TradingAgents: `tradingagents/agents/risk_management/` — aggressive, conservative, neutral agents | Study TradingAgents' 3-perspective risk debate. Build NexusTrade's version with configurable rounds and synthesis. | Same LangGraph debate pattern as bull/bear but for risk assessment. |
| F-RSK-003 | Position sizing | ADAPT | FinRL | FinRL: CVaR-PPO reward modification. Also: standard Kelly/ATR formulas | Study FinRL's CVaR implementation. Build 5 sizing models (CVaR, Kelly, fixed_fraction, volatility, max_drawdown) behind a RiskModelInterface. | CVaR comes from FinRL. Other models are standard quant formulas — no OSS reference needed. |
| F-RSK-004 | Circuit breakers | ADAPT | ai-hedge-fund | ai-hedge-fund: basic risk limits in portfolio manager | Study ai-hedge-fund's risk thresholds. Build comprehensive circuit breaker with cooldown, manual override, and notification integration. | ai-hedge-fund has basic limits. NexusTrade adds cooldown timer, notification, and manual override. |
| F-RSK-005 | India risk rules | REFERENCE | OpenAlgo | OpenAlgo: circuit limit data in instrument database, rate limiting per broker, SEBI audit trail | Study OpenAlgo's compliance features. Build India-specific risk rules that query OpenAlgo for instrument limits. | All India-specific data comes from OpenAlgo. NexusTrade adds the validation logic layer. |

### Backtesting & strategy

| Feature ID | Feature | Source | Project | Key source references | Approach | Notes |
|-----------|---------|--------|---------|----------------------|----------|-------|
| F-BKT-001 | Backtesting engine | ADAPT | Qlib + ai-hedge-fund | Qlib: `qlib/backtest/` module — walk-forward, metrics. ai-hedge-fund: `src/backtester.py` — simpler approach | Study Qlib's backtest engine for comprehensive metrics and walk-forward. Study ai-hedge-fund's backtester for simplicity. Build NexusTrade's engine that replays the full agent pipeline. | Qlib's engine is the most complete. But it expects Qlib's data format. NexusTrade's engine must work with canonical OHLCV. |
| F-BKT-002 | Strategy definition | ADAPT | OctoBot + Qlib | OctoBot: evaluator→strategy→trading mode pipeline. Qlib: strategy classes | Study OctoBot's strategy pattern for the evaluation framework. Design NexusTrade's YAML rule DSL that references agent signals + indicators. | The YAML DSL that combines agent signals with technical conditions is new. No project has this. |
| F-BKT-003 | Multi-timeframe | ADAPT | OctoBot | OctoBot: multi-timeframe evaluator config | Study OctoBot's timeframe handling. Build NexusTrade's multi-TF scheduler with per-TF analysis config. | OctoBot's approach is crypto-only. Extend to all markets with session awareness. |

### Infrastructure

| Feature ID | Feature | Source | Project | Key source references | Approach | Notes |
|-----------|---------|--------|---------|----------------------|----------|-------|
| F-INF-001 | Event bus | BUILD | None (Redis Streams standard patterns) | Redis Streams documentation. Python: `redis.asyncio` | Design AsyncEventBus class wrapping Redis Streams. Standard pub/sub with consumer groups. | No trading project uses Redis Streams as an event bus. Standard Redis patterns. |
| F-INF-002 | Docker topology | ADAPT | OctoBot | OctoBot: Dockerfile, docker-compose patterns | Study OctoBot's Docker setup. Design NexusTrade's 9-service topology with GPU sharing. | OctoBot has good Docker practices. Extend to multi-container with gRPC. |
| F-INF-003 | Plugin system | REFERENCE | OpenBB | OpenBB: extension discovery via entry_points, `openbb_core/app/extension_loader.py` | Study OpenBB's extension loading mechanism. Build NexusTrade's plugin registry using same entry_points pattern. | OpenBB has the best plugin system in the financial OSS space. |
| F-INF-004 | Notifications | REFERENCE | OpenAlgo + OctoBot | OpenAlgo: Telegram integration. OctoBot: Telegram bot + web notifications | Study OpenAlgo's Telegram alert format (trade details, PnL). Study OctoBot's notification patterns. Build NexusTrade's NotificationAdapter with multiple channels. | OpenAlgo's Telegram format is production-tested and includes all trade details. |
| F-INF-005 | Observability | REFERENCE | OpenAlgo | OpenAlgo: traffic monitor, latency tracking (`latency.db`), trade audit trail | Study OpenAlgo's observability features. Build NexusTrade's logging + audit trail + optional Prometheus metrics. | OpenAlgo's audit trail is SEBI-compliant. Good reference. |
| F-INF-006 | Scheduling | ADAPT | OctoBot | OctoBot: evaluator scheduling, timeframe-based triggers | Study OctoBot's scheduling approach. Build NexusTrade's cron-based + interval-based + event-based scheduler. | OctoBot's scheduler is crypto-focused (24/7). Extend for market-session-aware scheduling. |

### Configurability

| Feature ID | Feature | Source | Project | Key source references | Approach | Notes |
|-----------|---------|--------|---------|----------------------|----------|-------|
| F-CFG-001 | Config system | ADAPT | Qlib + ai-hedge-fund | Qlib: YAML config with defaults. ai-hedge-fund: environment-based config | Study Qlib's config loading pattern. Build NexusTrade's 4-layer system with Pydantic validation. | Standard Python patterns. Pydantic BaseSettings handles env var override natively. |
| F-CFG-002 | Adapter composability | BUILD | None (NexusTrade's core innovation) | Inspired by OpenBB's extension pattern | Design the universal adapter registry that discovers and instantiates all adapters from entry_points. | This is the glue that makes everything work together. |

---

## 3. Summary statistics

| Category | REFERENCE | ADAPT | BUILD | Total |
|----------|-----------|-------|-------|-------|
| Markets & assets | 4 | 2 | 1 | 7 |
| AI & agents | 7 | 1 | 3 | 11 |
| LLM configuration | 3 | 2 | 1 | 6 |
| Data sources | 3 | 2 | 2 | 7 |
| Execution | 5 | 2 | 1 | 8 |
| Risk management | 2 | 3 | 0 | 5 |
| Backtesting & strategy | 0 | 3 | 0 | 3 |
| Infrastructure | 3 | 2 | 1 | 6 |
| Configurability | 0 | 1 | 1 | 2 |
| **TOTAL** | **27** | **18** | **10** | **55** |

**27 features (49%)** have complete OSS references to study.  
**18 features (33%)** have partial solutions to adapt.  
**10 features (18%)** must be built from scratch.

---

## 4. OSS project quick reference

For Claude Code to quickly look up any referenced project:

| Project | GitHub URL | Stars | License | Primary language | Key contribution to NexusTrade |
|---------|-----------|-------|---------|-----------------|-------------------------------|
| ai-hedge-fund | `virattt/ai-hedge-fund` | ~45.7K | MIT | Python + TypeScript | 18 persona agents, LLM factory, portfolio manager |
| TradingAgents | `TauricResearch/TradingAgents` | ~46.6K | Apache 2.0 | Python | Bull/bear debate, risk debate, dual-LLM, ChromaDB memory |
| FinRL | `AI4Finance-Foundation/FinRL` | ~14.7K | MIT | Python | DRL agents (PPO/A2C), Alpaca integration, CVaR risk |
| FinGPT | `AI4Finance-Foundation/FinGPT` | ~19K | MIT | Python | LoRA fine-tuned sentiment models |
| FinBERT | `ProsusAI/finbert` | ~2K | — | Python | Fast sentiment classification (110M params) |
| OpenBB | `OpenBB-finance/OpenBB` | ~65K | Apache 2.0 | Python | Data platform, 30+ providers, MCP server |
| Qlib | `microsoft/qlib` | ~15K | MIT | Python | Factor mining, backtesting, cache, expression DSL |
| RD-Agent | `microsoft/RD-Agent` | ~11.2K | MIT | Python | LLM-driven autonomous factor discovery |
| OctoBot | `Drakkar-Software/OctoBot` | ~5K | GPL-3.0 | Python | Crypto bot, TradingView integration, Docker, notifications |
| QuantAgent | `Y-Research-SBU/QuantAgent` | ~1.3K | MIT | Python | Vision-based chart pattern recognition |
| OpenAlgo | `marketcalls/openalgo` | ~3K+ | AGPL-3.0 | Python | 30+ Indian broker unified API, TradingView webhooks, audit trail |
| CCXT | `ccxt/ccxt` | ~33K+ | MIT | Python/JS | 100+ crypto exchange unified API |
| LiteLLM | `BerriAI/litellm` | ~15K+ | MIT | Python | 100+ LLM provider unified API |

**License note:** OctoBot (GPL-3.0) and OpenAlgo (AGPL-3.0) — NexusTrade does NOT copy their code. We study their patterns and build our own implementations. NexusTrade's license should be MIT or Apache 2.0.
