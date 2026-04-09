# NexusTrade — Product Requirements Document (PRD)

> **Version:** 1.0  
> **Last Updated:** 2026-04-07  
> **Purpose:** This document defines EVERY feature, specification, acceptance criterion, and test requirement for the NexusTrade platform. It is the single source of truth for autonomous development by Claude Code.  
> **Audience:** Claude Code (autonomous AI developer). This document must be self-contained — no human clarification should be needed.

---

## 1. Product overview

**NexusTrade** is a unified, open-source LLM-powered algorithmic trading platform that combines the best capabilities from 10+ existing open-source projects into a single composable system. It supports all major markets (Forex, crypto, US equities, Indian equities, options, commodities), offers user-configurable execution (TradingView webhooks, Python direct broker APIs, or both simultaneously), and provides fully configurable LLM routing (local Ollama, cloud APIs, or hybrid).

### 1.1 Core design principles

1. **Everything is an adapter** — Data sources, brokers, agents, LLM providers, risk models, and notification channels are all pluggable behind abstract interfaces. Adding a new component = implement 1 interface + register via entry_points.
2. **Configuration over code** — All behavior is driven by YAML config with Pydantic validation. Changing a broker, LLM, agent, or market requires editing config, not source code.
3. **Microservice isolation** — Incompatible dependencies (FinRL/Stable Baselines, FinGPT/HuggingFace PEFT, Qlib/Cython) run in separate Docker containers communicating via Redis Streams and gRPC.
4. **Specs-driven development** — Claude Code designs and implements all code. This PRD defines WHAT to build and HOW TO VERIFY it, not HOW to implement it.

### 1.2 Target users

- **Primary:** Developer-traders who write Python and want full control over their trading system.
- **Secondary:** Quant researchers who want to backtest LLM-augmented strategies.
- **Tertiary:** Indian retail traders automating strategies via TradingView + OpenAlgo.

---

## 2. Feature catalog

Each feature has: unique ID, category, name, detailed specification, acceptance criteria, and test specifications.

Priority levels: **P0** = Must have for MVP, **P1** = Important, **P2** = Nice-to-have.

---

### CATEGORY: Markets & assets

#### F-MKT-001: US equity support
- **Priority:** P0
- **Spec:** The system must ingest OHLCV data, fundamentals, and news for US equities (NYSE, NASDAQ). Data comes through the DataProviderInterface. Execution routes through Alpaca (paper + live).
- **Symbols:** Standard ticker format: `AAPL`, `MSFT`, `NVDA`, `TSLA`, etc.
- **Data requirements:** Historical OHLCV (1m to 1M timeframes), real-time quotes, fundamentals (P/E, EPS, revenue), and news.
- **Acceptance criteria:**
  - User configures `markets.us_equities.symbols: ["AAPL", "MSFT"]` in YAML.
  - System fetches OHLCV for configured symbols at configured timeframes.
  - Agents produce signals for US equities.
  - Orders execute through Alpaca backend (paper mode by default).
- **Test specs:**
  - Unit: Mock DataProviderInterface returns OHLCV for `AAPL`; verify canonical format (UTC timestamp, float fields, symbol string).
  - Integration: Fetch real AAPL daily data from OpenBB; verify >250 bars for 1-year request.
  - E2E: Full pipeline — fetch AAPL data → run 1 agent → produce signal → place paper order on Alpaca → verify fill returned.

#### F-MKT-002: Indian equity support (NSE/BSE)
- **Priority:** P0
- **Spec:** Support NSE and BSE listed equities and F&O instruments. Data ingestion via OpenAlgo's historical data API or OpenBB (where available). Execution via OpenAlgo unified API connecting to any of 30+ Indian brokers.
- **Symbols:** OpenAlgo common format: `RELIANCE`, `TCS`, `INFY`, `BANKNIFTY25APRFUT`.
- **Special requirements:**
  - Market sessions: Pre-open (9:00-9:15 IST), Regular (9:15-15:30 IST), Post-close auction (15:30-15:40 IST).
  - Circuit limits: Per-stock 2-20% limits. Market-wide circuit breakers at 10/15/20% on Nifty.
  - Daily token refresh: Indian broker API tokens expire at ~6 AM IST. System must auto-refresh.
  - F&O lot sizes: Must validate quantity against exchange-mandated lot sizes before placing orders.
  - SEBI audit trail: All automated trades must be logged with timestamp, order ID, strategy name, and outcome.
- **Acceptance criteria:**
  - User configures `execution.india.broker: "zerodha"` (or dhan, fyers, angel, etc.) in YAML.
  - System connects to OpenAlgo, authenticates with configured broker.
  - Historical data fetched via OpenAlgo's data API.
  - Orders placed through OpenAlgo's unified placeorder endpoint.
  - Circuit limit checker prevents orders that would breach limits.
- **Test specs:**
  - Unit: Verify symbol format translation (RELIANCE → Zerodha format, RELIANCE → Dhan format, etc.).
  - Unit: Verify circuit limit checker rejects order when stock is at circuit limit.
  - Unit: Verify F&O lot size validation rejects invalid quantities.
  - Integration: Connect to OpenAlgo sandbox/paper, place RELIANCE buy order, verify fill.
  - E2E: Full pipeline with Indian equity — data → agents → signal → OpenAlgo order → fill confirmation.

#### F-MKT-003: Forex support
- **Priority:** P0
- **Spec:** Support major, minor, and exotic forex pairs. Data primarily from TradingView MCP (pre-computed technicals) and OpenBB (OHLCV). Execution via TradingView webhooks (primary for forex) or CCXT (for crypto-forex pairs on exchanges).
- **Symbols:** Standard format: `EUR/USD`, `GBP/USD`, `USD/JPY`, `AUD/CAD`, etc.
- **Special requirements:**
  - 24/5 market (Sunday 5 PM ET to Friday 5 PM ET). Must handle session-based analysis (Asian, London, New York sessions).
  - Pip calculation varies by pair (JPY pairs = 0.01, others = 0.0001).
  - Spread tracking: System must log bid-ask spread alongside signals.
- **Acceptance criteria:**
  - User configures `markets.forex.symbols: ["EUR/USD", "GBP/USD"]`.
  - System fetches OHLCV data for forex pairs.
  - TradingView MCP adapter returns pre-computed RSI, MACD, Bollinger Bands for forex.
  - Execution routes to TradingView webhook or configured forex broker.
- **Test specs:**
  - Unit: Verify pip calculation for JPY pairs (0.01) vs standard pairs (0.0001).
  - Unit: Verify session detection (Asian/London/NY) based on UTC timestamp.
  - Integration: Fetch EUR/USD 1H data from TradingView MCP, verify technicals returned.
  - E2E: Signal → TradingView webhook relay → verify webhook payload matches expected format.

#### F-MKT-004: Crypto support
- **Priority:** P0
- **Spec:** Support cryptocurrency trading across 100+ exchanges via CCXT. Data from CCXT (real-time WebSocket, OHLCV, order book) and TradingView MCP (technicals, screening).
- **Symbols:** CCXT format: `BTC/USDT`, `ETH/USDT`, `SOL/USDT`, etc.
- **Special requirements:**
  - 24/7 market — no sessions, no holidays.
  - High volatility — circuit breakers must be configurable per-asset.
  - Exchange-specific fee structures (maker/taker).
  - Leverage/margin for futures (configurable, default 1x = spot).
- **Acceptance criteria:**
  - User configures `execution.crypto.exchange: "binance"` with API keys.
  - System fetches real-time and historical data via CCXT.
  - Orders placed through CCXT backend.
  - WebSocket streaming for real-time price updates.
- **Test specs:**
  - Unit: Verify CCXT OHLCV array `[timestamp_ms, O, H, L, C, V]` converts to canonical OHLCV format.
  - Unit: Verify fee calculation (maker/taker) for Binance.
  - Integration: Fetch BTC/USDT 1H candles from Binance testnet; verify data integrity.
  - E2E: Full pipeline on Binance testnet — data → agent → signal → order → fill.

#### F-MKT-005: Options support
- **Priority:** P1
- **Spec:** Support options trading for US equities via Interactive Brokers and Indian F&O via OpenAlgo. Include options chain data, Greeks (delta, gamma, theta, vega), and options-specific order types (spreads, straddles).
- **Acceptance criteria:**
  - User configures `execution.options.backend: "interactive_brokers"`.
  - System fetches options chain with strikes, expiries, and Greeks.
  - Agents can analyze options data alongside equity data.
  - Orders support multi-leg strategies (vertical spreads, iron condors).
- **Test specs:**
  - Unit: Verify options chain data model includes strike, expiry, type (call/put), bid, ask, and Greeks.
  - Unit: Verify multi-leg order construction (e.g., bull call spread = buy lower strike call + sell higher strike call).
  - Integration: Fetch AAPL options chain from IB paper account.

#### F-MKT-006: Commodity support
- **Priority:** P1
- **Spec:** Support commodity futures (gold, silver, crude oil, natural gas) via Interactive Brokers or TradingView webhooks for Indian MCX commodities via OpenAlgo.
- **Acceptance criteria:**
  - System fetches commodity OHLCV data.
  - Agents produce signals for commodity instruments.
  - Execution routes to appropriate backend based on market.
- **Test specs:**
  - Unit: Verify commodity symbol resolution (GC=F for gold futures, CL=F for crude oil).
  - Integration: Fetch gold futures data; verify OHLCV format.

#### F-MKT-007: Multi-market simultaneous operation
- **Priority:** P0
- **Spec:** The system must support running strategies across multiple markets simultaneously. A single NexusTrade instance can monitor US equities, Indian equities, forex, and crypto at the same time, with each market routing to its appropriate data provider and execution backend.
- **Acceptance criteria:**
  - User configures symbols across all markets in a single YAML file.
  - System runs analysis for all markets concurrently.
  - Execution routes correctly: US equity → Alpaca, India equity → OpenAlgo, Crypto → CCXT, Forex → TradingView webhook.
  - Portfolio-level risk management spans all markets.
- **Test specs:**
  - Integration: Configure AAPL + RELIANCE + BTC/USDT + EUR/USD. Verify data fetched from 4 different providers.
  - Integration: Verify execution routing: AAPL order → Alpaca, RELIANCE order → OpenAlgo.
  - E2E: Full multi-market pipeline with paper trading across all backends.

---

### CATEGORY: AI & agents

#### F-AGT-001: Universal agent interface
- **Priority:** P0
- **Spec:** Define an `AgentInterface` ABC that ALL agents (from any source project) must implement. The interface has a single core method: `analyze(context: MarketContext) -> AgentSignal`. MarketContext contains OHLCV data, enriched signals (sentiment, technicals, factors), and agent memory. AgentSignal contains: direction (strong_buy/buy/hold/sell/strong_sell), confidence (0.0-1.0), reasoning (str), agent_name, agent_type, timestamp, and metadata dict.
- **Acceptance criteria:**
  - All agent adapters implement AgentInterface.
  - Agents are auto-discovered via Python entry_points under `nexustrade.agents` group.
  - New agents can be added by implementing 1 class + registering in pyproject.toml.
  - Agent registry discovers and instantiates all registered agents at startup.
- **Test specs:**
  - Unit: Create a mock agent implementing AgentInterface. Call analyze(). Verify return type is AgentSignal.
  - Unit: Verify agent registry discovers entry_points-registered agents.
  - Unit: Verify AgentSignal validation — confidence must be 0.0-1.0, direction must be valid enum value.

#### F-AGT-002: ai-hedge-fund investor persona agents
- **Priority:** P0
- **Spec:** Adapt 18 investor persona agents from the ai-hedge-fund project (virattt/ai-hedge-fund). Each agent analyzes markets through the lens of a legendary investor. Agents include: Warren Buffett (value), Charlie Munger (quality), Ben Graham (deep value), Bill Ackman (activist), Cathie Wood (growth/innovation), Michael Burry (contrarian), Stanley Druckenmiller (macro), Aswath Damodaran (valuation), Peter Lynch (GARP), Philip Fisher (growth), Rakesh Jhunjhunwala (India value — especially relevant for NSE), and more. Each agent is wrapped in an `AIHedgeFundAdapter` that translates between ai-hedge-fund's AgentState format and NexusTrade's MarketContext/AgentSignal format.
- **Acceptance criteria:**
  - Each of the 18 agents runs independently and produces an AgentSignal.
  - Agents are selectively enabled via YAML config: `agents.enabled: [{name: "warren_buffett", source: "ai_hedge_fund"}]`.
  - Each agent can have per-agent LLM override (model + temperature + max_tokens).
  - Agents handle missing data gracefully (e.g., no fundamentals for crypto → skip fundamental analysis, still produce signal from available data).
- **Test specs:**
  - Unit: Mock LLM returns a structured response. Verify AIHedgeFundAdapter extracts direction and confidence.
  - Unit: Test each of 18 agents with mock data containing: OHLCV, financials, news. Verify each produces valid AgentSignal.
  - Unit: Verify per-agent LLM config override (agent uses temperature=0.3 when configured, not global default).
  - Integration: Run Buffett agent with real AAPL data against a real LLM. Verify reasoning references value metrics.

#### F-AGT-003: TradingAgents bull/bear adversarial debate
- **Priority:** P0
- **Spec:** Adapt the bull/bear debate mechanism from TradingAgents (TauricResearch/TradingAgents). Two researcher agents (bull and bear) argue for and against a trade. A research manager synthesizes the debate using the deep_think LLM. The debate runs for a configurable number of rounds (default: 2, configurable via `agents.debate.rounds: 3`). Early termination if both sides reach consensus above `early_termination_confidence` threshold.
- **Acceptance criteria:**
  - Bull researcher produces a bullish thesis with evidence.
  - Bear researcher produces a bearish counterargument.
  - Research manager synthesizes into a final AgentSignal with direction and confidence.
  - Number of debate rounds is configurable in YAML.
  - Early termination works when confidence exceeds threshold.
  - Debate uses the `deep` LLM (cloud model) while individual researchers use the `fast` LLM.
- **Test specs:**
  - Unit: Mock bull agent returns bullish signal, mock bear returns bearish. Verify manager produces a synthesized signal.
  - Unit: Verify debate runs exactly N rounds when configured with `rounds: N`.
  - Unit: Verify early termination triggers when both agents report confidence > threshold.
  - Integration: Run full debate with real LLM on AAPL data. Verify both perspectives represented in reasoning.

#### F-AGT-004: DRL trading agents (FinRL)
- **Priority:** P1
- **Spec:** Adapt reinforcement learning agents from FinRL. These are pre-trained SB3 models (PPO, A2C, DDPG, TD3, SAC) that take an observation vector `[balance, prices, holdings, technical_indicators]` and output continuous action values representing buy/sell fractions. Models are stored as `.zip` files and loaded via `PPO.load("model_path")`. The adapter converts `model.predict(obs)` output to an AgentSignal (positive action = buy signal, negative = sell signal, magnitude = confidence).
- **Acceptance criteria:**
  - Pre-trained models load from configurable `model_path`.
  - Adapter constructs observation vector from MarketContext (OHLCV + indicators).
  - Continuous action output maps to SignalDirection + confidence.
  - Runs in a separate Docker container (GPU) with gRPC interface for inference calls.
- **Test specs:**
  - Unit: Verify observation vector construction from canonical OHLCV (correct shape, normalized values).
  - Unit: Verify action-to-signal mapping: action > 0.5 → STRONG_BUY, 0.0-0.5 → BUY, -0.5-0.0 → SELL, < -0.5 → STRONG_SELL.
  - Integration: Load a pre-trained PPO model, pass real observation, verify prediction returns valid shape.

#### F-AGT-005: Financial sentiment analysis (FinBERT + FinGPT)
- **Priority:** P0
- **Spec:** Dual sentiment pipeline. **Fast path:** FinBERT (ProsusAI/finbert, 110M params) runs on CPU at 1-5ms/sentence for real-time sentiment scoring. Returns `[P(negative), P(neutral), P(positive)]` for each headline. **Deep path:** FinGPT fine-tuned LoRA models provide more nuanced analysis with context, running in a separate GPU container. The sentiment adapter aggregates scores from all recent news items into a single AgentSignal.
- **Acceptance criteria:**
  - FinBERT loads from HuggingFace and classifies headlines in <10ms each.
  - FinGPT loads base model + LoRA adapter and provides directional forecast.
  - Combined sentiment score aggregates multiple headlines with recency weighting.
  - Both models run in the `fingpt-service` Docker container.
- **Test specs:**
  - Unit: FinBERT classifies "Company beats earnings expectations" as positive (P(positive) > 0.7).
  - Unit: FinBERT classifies "Company announces massive layoffs" as negative (P(negative) > 0.7).
  - Unit: Verify recency-weighted aggregation: latest headline gets weight 1.0, 24h old gets 0.5, 48h old gets 0.25.
  - Integration: Fetch real news for AAPL from OpenBB, run through FinBERT, verify sentiment scores for each.

#### F-AGT-006: Vision-based chart analysis (QuantAgent)
- **Priority:** P1
- **Spec:** Adapt QuantAgent's pattern recognition. Generate candlestick chart images from OHLCV data (via matplotlib or TradingView MCP chart screenshot), then feed to a multimodal LLM (GPT-4o, Claude) for pattern detection. The PatternAgent identifies formations (head & shoulders, double top/bottom, flags, wedges). The TrendAgent annotates support/resistance levels and trend channels.
- **Acceptance criteria:**
  - Chart image generated from OHLCV data (minimum 100 candles).
  - Image sent to vision-capable LLM via LLM Router (vision channel).
  - LLM returns pattern identification + directional bias.
  - Adapter wraps LLM response into AgentSignal.
- **Test specs:**
  - Unit: Verify chart image generation from OHLCV (PNG format, readable by LLM).
  - Unit: Verify LLM Router routes to vision model when agent requires_vision=true.
  - Integration: Generate AAPL chart, send to GPT-4o vision, verify structured pattern response.

#### F-AGT-007: Auto factor mining (Qlib + RD-Agent)
- **Priority:** P1
- **Spec:** Integrate Qlib's expression DSL for computing Alpha158 (158 indicators) and Alpha360 (360 features) from OHLCV data. Qlib's factor outputs export as pandas DataFrames. Optionally integrate RD-Agent for LLM-driven autonomous factor discovery (propose → implement → backtest → evolve). Factor signals convert to AgentSignal via thresholding (top decile = BUY, bottom decile = SELL).
- **Acceptance criteria:**
  - Qlib computes Alpha158 factors from canonical OHLCV data.
  - Factors export as structured signal (DataFrame with symbol, date, factor values).
  - Factor-to-signal adapter maps factor ranks to directional signals.
  - Runs in `qlib-service` Docker container.
- **Test specs:**
  - Unit: Verify Alpha158 computation produces 158 columns from OHLCV input.
  - Unit: Verify top-decile/bottom-decile thresholding produces correct signals.
  - Integration: Compute factors for AAPL 1-year data; verify no NaN values in output.

#### F-AGT-008: Market situation memory
- **Priority:** P1
- **Spec:** Adapt TradingAgents' ChromaDB-based FinancialSituationMemory. After each trade decision, store the market context (OHLCV snapshot, agent signals, final decision, outcome) as an embedding in ChromaDB. Before future decisions, query for similar historical situations and include them in the agent context. Configurable: `memory.retention_days`, `memory.max_entries`, `memory.similarity_threshold`.
- **Acceptance criteria:**
  - Market situations stored in ChromaDB with embeddings.
  - Similar situations retrieved before new analysis (top-K by similarity).
  - Retention policy enforced: entries older than `retention_days` are pruned.
  - Memory retrieval adds context to MarketContext for agents.
- **Test specs:**
  - Unit: Store a situation, query for similar, verify retrieved situation matches.
  - Unit: Verify retention pruning removes entries older than configured days.
  - Unit: Verify similarity threshold filters out low-relevance memories.

#### F-AGT-009: Heterogeneous agent ensemble
- **Priority:** P0
- **Spec:** This is NexusTrade's unique capability — running agents from fundamentally different paradigms (LLM-based persona agents, RL-based DRL agents, NLP-based sentiment models, and vision-based chart analyzers) simultaneously on the same trade decision, then aggregating their signals. No existing system does this.
- **Acceptance criteria:**
  - Agents from 4+ different paradigms run in parallel on the same symbol.
  - All produce the same AgentSignal format regardless of underlying technology.
  - Signal aggregator handles heterogeneous confidence scales (calibrate across paradigms).
- **Test specs:**
  - Integration: Run Buffett agent (LLM) + FinRL PPO (RL) + FinBERT (NLP) on AAPL simultaneously. Verify all produce valid AgentSignals.
  - Integration: Verify aggregator correctly weights signals from different paradigms.

#### F-AGT-010: Signal aggregation
- **Priority:** P0
- **Spec:** Configurable signal aggregation from multiple agents. Modes: (1) `weighted_confidence` — weighted average of all signals by confidence (default), (2) `majority_vote` — direction with most votes wins, (3) `unanimous` — all must agree or HOLD, (4) `portfolio_manager` — a dedicated LLM agent receives all signals and makes the final call. Minimum confidence threshold: signals below `min_confidence` are ignored. Agent-specific weights configurable in YAML.
- **Acceptance criteria:**
  - All 4 aggregation modes implemented and selectable via config.
  - Per-agent weight overrides work.
  - Minimum confidence threshold filters weak signals.
  - Aggregated signal includes reasoning from contributing agents.
- **Test specs:**
  - Unit: 3 agents: BUY(0.8), BUY(0.6), SELL(0.9). Weighted confidence → depends on weights. Majority → BUY. Unanimous → HOLD (no unanimity).
  - Unit: Verify min_confidence=0.5 filters out BUY(0.3) signal.
  - Unit: Verify per-agent weight: agent_a weight=2.0, agent_b weight=1.0 → agent_a's signal counts double.

#### F-AGT-011: Configurable agent execution order
- **Priority:** P1
- **Spec:** Support three execution modes: (1) `parallel` — all agents run simultaneously (default), (2) `sequential` — agents run one after another in configured order, (3) `dag` — dependency graph where agent_b depends on agent_a's output. DAG mode enables "run sentiment first, then only run technical agents if sentiment is bullish."
- **Acceptance criteria:**
  - Parallel mode runs all agents concurrently.
  - Sequential mode respects configured order.
  - DAG mode evaluates dependencies and skips agents whose dependencies produced HOLD/SELL (configurable).
  - Execution mode configurable in YAML.
- **Test specs:**
  - Unit: DAG with agent_b depends on agent_a. agent_a returns SELL. Verify agent_b is skipped.
  - Unit: Sequential mode — verify agent_b receives agent_a's signal in its MarketContext.

---

### CATEGORY: LLM configuration

#### F-LLM-001: Multi-provider LLM routing
- **Priority:** P0
- **Spec:** Route LLM calls to any provider through a unified interface powered by LiteLLM. Support: OpenAI (GPT-4o, GPT-4o-mini, o3), Anthropic (Claude Sonnet 4, Claude Opus 4), DeepSeek (deepseek-chat, deepseek-reasoner), Google (Gemini 2.5), Groq (fast inference), and Ollama (any local model). The router maintains three channels: `fast` (high-volume analyst calls), `deep` (low-volume reasoning calls), `vision` (multimodal image analysis).
- **Acceptance criteria:**
  - All 6+ providers accessible through single `llm.complete(messages, channel="fast")` call.
  - Provider-specific formatting handled automatically (Anthropic tool format vs OpenAI format).
  - Fallback chain: if primary provider fails, falls through to configured fallbacks.
  - Model capabilities tracked: function_calling, vision, json_mode, streaming.
- **Test specs:**
  - Unit: Mock LiteLLM completion call. Verify correct model string passed for each provider.
  - Unit: Verify fallback: primary returns error, fallback model called successfully.
  - Unit: Verify capability registry: request vision model, router selects vision-capable model.
  - Integration: Call each provider (OpenAI, Anthropic, Ollama) with a simple prompt; verify responses.

#### F-LLM-002: Local LLM support (Ollama)
- **Priority:** P0
- **Spec:** Full support for local LLM inference via Ollama. User runs Ollama separately (or NexusTrade Docker Compose includes it). System connects to Ollama at configurable `base_url` (default: `http://localhost:11434`). Support any Ollama model: llama3:8b, llama3:70b, qwen2.5:72b, mistral, codestral, llava (vision), etc.
- **Acceptance criteria:**
  - LLM Router connects to Ollama via LiteLLM's Ollama provider.
  - Local inference works without any internet connection (after model download).
  - Zero trading data sent to external APIs when in `local` mode.
  - Vision models (llava) work for chart analysis.
- **Test specs:**
  - Unit: Verify LiteLLM formats Ollama model string correctly: `ollama/llama3:8b`.
  - Integration: Send prompt to local Ollama; verify response received.
  - Integration: Verify no network calls to external APIs when mode=local.

#### F-LLM-003: Hybrid LLM mode
- **Priority:** P0
- **Spec:** Three operating modes: (1) `local` — both fast and deep use Ollama, (2) `cloud` — both use cloud APIs, (3) `hybrid` — fast uses local Ollama (high volume, low cost), deep uses cloud API (low volume, high quality). Mode is configurable via `llm.mode: "hybrid"`. In hybrid mode, analyst agents use the fast/local LLM for high-volume screening, while debate synthesis, risk assessment, and portfolio decisions use the deep/cloud LLM for quality reasoning.
- **Acceptance criteria:**
  - Three modes selectable via config.
  - In hybrid mode, agents tagged with `llm_channel: "fast"` use Ollama, agents tagged `llm_channel: "deep"` use cloud.
  - Vision requests always route to vision-capable model regardless of mode.
  - Cost tracking: log estimated token costs per provider.
- **Test specs:**
  - Unit: In hybrid mode, verify fast channel routes to Ollama, deep channel routes to Anthropic.
  - Unit: Verify vision request in `local` mode routes to `ollama/llava`, in `cloud` mode to `openai/gpt-4o`.

#### F-LLM-004: Per-agent LLM configuration
- **Priority:** P0
- **Spec:** Each agent can override the global LLM settings. Override hierarchy: agent-specific config → global channel config → system default. Overridable parameters: `model`, `temperature`, `top_p`, `max_tokens`, `presence_penalty`, `frequency_penalty`.
- **Acceptance criteria:**
  - Agent config includes optional `llm_override` block with any combination of parameters.
  - Risk agent uses temperature=0.1 (conservative) while research agent uses 0.7 (creative).
  - Unspecified parameters inherit from global config.
- **Test specs:**
  - Unit: Agent with `llm_override.temperature: 0.1`. Verify LiteLLM called with temperature=0.1.
  - Unit: Agent with only `llm_override.model: "gpt-4o"`. Verify temperature inherits from global (not reset to default).

#### F-LLM-005: Customizable prompt templates
- **Priority:** P0
- **Spec:** ALL agent prompts stored as Jinja2 templates in `config/prompts/` directory. Templates receive MarketContext variables (symbol, price, indicators, news, fundamentals) and render into the final prompt. Users can modify templates without changing any Python code. Templates include: system prompts, analysis instructions, debate prompts, risk assessment prompts, and aggregation prompts.
- **Acceptance criteria:**
  - All prompts loaded from `.j2` template files at runtime.
  - Template variables include all MarketContext fields.
  - Modified template takes effect on next analysis cycle (no restart needed with hot-reload).
  - Default templates ship with the project (extracted from ai-hedge-fund and TradingAgents).
- **Test specs:**
  - Unit: Render Buffett agent template with mock MarketContext. Verify output contains symbol name and price data.
  - Unit: Modify template file on disk. Verify next call uses updated template.
  - Unit: Verify template with missing variable raises clear error (not silent failure).

#### F-LLM-006: LoRA fine-tuned financial models
- **Priority:** P1
- **Spec:** Support loading FinGPT's LoRA fine-tuned adapters on top of base models (LLaMA-2/3, ChatGLM2, Falcon). Adapters are small (~10-15MB) files loaded via `PeftModel.from_pretrained()`. System includes a fine-tuning pipeline for users to train their own adapters on custom financial data.
- **Acceptance criteria:**
  - Pre-trained FinGPT adapters load and produce sentiment predictions.
  - Fine-tuning pipeline accepts user's financial dataset and produces new adapter.
  - Runs in `fingpt-service` GPU container.
- **Test specs:**
  - Unit: Verify LoRA adapter loads on top of base model without errors.
  - Integration: Run sentiment inference with FinGPT adapter; verify output format.

---

### CATEGORY: Data sources

#### F-DAT-001: Data provider interface
- **Priority:** P0
- **Spec:** Define `DataProviderInterface` ABC with methods: `get_ohlcv(symbol, timeframe, start, end) -> list[OHLCV]` (required), `get_quote(symbol) -> Quote` (required), `get_news(symbol) -> list[NewsItem]` (optional), `get_fundamentals(symbol) -> dict` (optional), `get_technicals(symbol, tf) -> dict` (optional), `get_chart_image(symbol, tf) -> bytes` (optional), `screen(filters) -> list[dict]` (optional), `stream(symbols) -> AsyncIterator[Quote]` (optional). All providers auto-discovered via entry_points.
- **Acceptance criteria:**
  - Interface defined as ABC with clear type hints.
  - Required methods raise NotImplementedError if not implemented.
  - Optional methods return empty defaults.
  - Registry discovers all registered providers.
  - Canonical data models: OHLCV (UTC timestamp, float OHLCV, str symbol, str timeframe, str source), Quote, NewsItem.
- **Test specs:**
  - Unit: Create stub provider implementing only required methods. Verify optional methods return defaults.
  - Unit: Verify canonical OHLCV model validates UTC timestamps, rejects non-float prices.

#### F-DAT-002: OpenBB data adapter
- **Priority:** P0
- **Spec:** Primary data provider wrapping OpenBB Platform's Fetcher interface. Supports 30+ sub-providers (FMP, Yahoo Finance, Alpha Vantage, FRED, SEC, Polygon, etc.) via OpenBB's extension system. Covers equities, forex, crypto, derivatives, commodities, and economic data. Also provides MCP server for LLM agent direct data querying.
- **Acceptance criteria:**
  - Fetches OHLCV for US equities, forex, crypto from OpenBB.
  - Sub-provider selectable in config: `data.providers[0].config.provider: "fmp"`.
  - Fundamentals, news, and economic data accessible.
  - MCP server exposes all endpoints as AI-callable tools.
- **Test specs:**
  - Integration: Fetch AAPL daily OHLCV for 2024 via OpenBB FMP provider. Verify >250 bars.
  - Integration: Fetch EUR/USD daily OHLCV. Verify data returned.
  - Integration: Fetch AAPL fundamentals (P/E, EPS). Verify non-null values.

#### F-DAT-003: TradingView MCP data adapter
- **Priority:** P0
- **Spec:** Data provider wrapping TradingView MCP servers (3 complementary servers): (1) `tradingview-mcp` (atilaahmettaner) — real-time screening, Bollinger intelligence, multi-timeframe analysis for crypto and stocks, (2) `tradingview-chart-mcp` (ertugrul59) — chart image capture via Selenium browser pooling (70-80% faster for concurrent requests) for QuantAgent vision analysis, (3) `tradingview-mcp-server` (fiale-plus) — 100+ screener fields, golden cross detection, Piotroski F-Score, multi-asset coverage (stocks, forex, crypto, ETFs). This adapter is the PRIMARY source for pre-computed technical indicators and market screening. It is the PRIMARY source for chart images used in vision-based analysis.
- **Acceptance criteria:**
  - Pre-computed technicals returned: RSI, MACD, Bollinger Bands, SMA/EMA crossovers, pivot points.
  - Market screener filters 11,000+ instruments with 100+ fields.
  - Chart images captured for QuantAgent vision pipeline.
  - All three MCP servers configurable independently.
- **Test specs:**
  - Integration: Get technicals for AAPL from TradingView MCP. Verify RSI, MACD values returned.
  - Integration: Screen for stocks with RSI < 30 and P/E < 15. Verify filtered results.
  - Integration: Capture AAPL 4H chart image. Verify PNG data returned and is valid image.

#### F-DAT-004: Broker data adapter
- **Priority:** P0
- **Spec:** Data provider using broker APIs (via OpenAlgo) for Indian market data. Provides historical candles, real-time quotes, and Level 2 market depth for NSE/BSE instruments. Falls back to OpenBB when broker data is unavailable.
- **Acceptance criteria:**
  - Fetches historical candles for NSE equities via OpenAlgo.
  - Real-time quotes via OpenAlgo's WebSocket (ZeroMQ distribution).
  - Market depth (Level 5) available for subscribed instruments.
- **Test specs:**
  - Integration: Fetch RELIANCE daily candles via OpenAlgo. Verify OHLCV format.
  - Integration: Subscribe to real-time quotes for INFY. Verify streaming updates received.

#### F-DAT-005: CCXT data adapter
- **Priority:** P0
- **Spec:** Data provider wrapping CCXT for 100+ cryptocurrency exchanges. Provides OHLCV, real-time WebSocket streaming, order book depth, and trade history. Primary source for all crypto market data.
- **Acceptance criteria:**
  - OHLCV fetched for any pair on any CCXT-supported exchange.
  - WebSocket streaming for real-time price updates.
  - Order book depth (configurable levels).
  - CCXT's unified format converted to canonical OHLCV.
- **Test specs:**
  - Unit: Verify CCXT `[timestamp_ms, O, H, L, C, V]` array converts to canonical OHLCV.
  - Integration: Fetch BTC/USDT 1H candles from Binance. Verify data integrity.
  - Integration: Open WebSocket stream for ETH/USDT. Verify real-time quotes received within 5s.

#### F-DAT-006: Smart data routing
- **Priority:** P0
- **Spec:** The data layer automatically routes requests to the best provider for each market/data type based on configurable priority. Config defines provider priority per market and per data type. Example routing: `us_equity: [openbb, yahoo]`, `forex: [tradingview_mcp, openbb]`, `technicals: [tradingview_mcp]`, `chart_images: [tradingview_mcp]`. If the primary provider fails, fallback to the next in the priority list.
- **Acceptance criteria:**
  - Routing config defines priority lists per market and per data type.
  - System automatically uses highest-priority available provider.
  - Fallback on failure with retry.
  - Provider health checks determine availability.
- **Test specs:**
  - Unit: Configure routing `us_equity: [openbb, yahoo]`. Mock openbb as healthy. Verify openbb called.
  - Unit: Mock openbb as unhealthy. Verify yahoo called as fallback.
  - Unit: Verify `technicals` routing always goes to TradingView MCP regardless of market.

#### F-DAT-007: Multi-level data caching
- **Priority:** P1
- **Spec:** Three-level cache: (1) In-memory LRU cache for hot data (configurable size), (2) Redis cache for warm data (configurable TTL per data type), (3) Disk cache for historical data (Qlib-style binary format for fast replay). Cache is transparent to consumers — same interface whether data is cached or fresh. Configurable TTL per data type: real-time quotes = 0s (no cache), 1m bars = 60s, daily bars = 1h, fundamentals = 24h.
- **Acceptance criteria:**
  - Cache reduces API calls for repeated requests.
  - TTL configurable per data type in YAML.
  - Cache can be disabled entirely (`cache.enabled: false`).
  - Cache warming on startup for configured symbols.
- **Test specs:**
  - Unit: Request same OHLCV twice within TTL. Verify provider called only once.
  - Unit: Request OHLCV after TTL expires. Verify provider called again.
  - Unit: Verify cache disabled mode: provider called every time.

---

### CATEGORY: Execution

#### F-EXE-001: Broker backend interface
- **Priority:** P0
- **Spec:** Define `BrokerBackendInterface` ABC with methods: `place_order(Order) -> Fill` (required), `cancel_order(order_id) -> bool` (required), `get_positions() -> list[Position]` (required), `get_account() -> dict` (required), `modify_order(order_id, changes) -> Fill` (optional), `get_order_history(limit) -> list[Fill]` (optional). All brokers auto-discovered via entry_points under `nexustrade.brokers` group.
- **Canonical models:** Order (symbol, side, type, quantity, price, stop_price, take_profit, stop_loss, time_in_force, metadata), Fill (order_id, symbol, side, filled_qty, avg_price, timestamp, broker, status, fees), Position (symbol, quantity, avg_entry_price, current_price, unrealized_pnl, broker).
- **Acceptance criteria:**
  - All broker backends implement BrokerBackendInterface.
  - Auto-discovered via entry_points.
  - Canonical Order/Fill/Position models used across all backends.
- **Test specs:**
  - Unit: Create mock broker implementing interface. Place order, verify Fill returned.
  - Unit: Verify entry_point discovery finds registered brokers.

#### F-EXE-002: OpenAlgo broker backend (30+ Indian brokers)
- **Priority:** P0
- **Spec:** Broker backend wrapping OpenAlgo's unified REST API. OpenAlgo runs as a separate self-hosted service (Flask, port 5000) and handles all broker-specific quirks internally. NexusTrade's adapter communicates via OpenAlgo's `/api/v1/placeorder`, `/api/v1/cancelorder`, `/api/v1/positionbook`, `/api/v1/funds` endpoints. User selects broker in config: `execution.india.broker: "zerodha"`. OpenAlgo handles: common symbol format, daily token refresh, TOTP automation, circuit limit validation, rate limiting per broker (Zerodha 3/sec, Angel 10/sec).
- **Acceptance criteria:**
  - Adapter connects to OpenAlgo at configured host.
  - Orders placed via REST API with apikey authentication.
  - Symbol format uses OpenAlgo common format (no broker-specific translation needed in NexusTrade).
  - Position and account data retrieved correctly.
  - Works with any of 30+ supported Indian brokers by changing config.
- **Test specs:**
  - Unit: Mock OpenAlgo API response. Verify Fill model constructed correctly from JSON.
  - Unit: Verify error handling for rejected orders (insufficient margin, circuit limit).
  - Integration: Connect to OpenAlgo with Dhan sandbox. Place paper order. Verify fill.
  - Integration: Switch config to Zerodha. Verify same adapter works without code changes.

#### F-EXE-003: Alpaca broker backend
- **Priority:** P0
- **Spec:** Broker backend for US equities + crypto via Alpaca's API. Supports paper trading (default) and live trading. Uses `alpaca-py` SDK. Handles fractional shares, extended hours, and crypto 24/7.
- **Acceptance criteria:**
  - Paper and live trading modes configurable.
  - Fractional share support for equities.
  - Crypto trading via Alpaca's crypto endpoints.
- **Test specs:**
  - Integration: Place AAPL paper buy order via Alpaca. Verify fill.
  - Integration: Get positions after order. Verify AAPL appears with correct quantity.

#### F-EXE-004: CCXT broker backend
- **Priority:** P0
- **Spec:** Broker backend for 100+ cryptocurrency exchanges via CCXT unified API. Exchange selectable in config. Handles exchange-specific order types, fee structures, and rate limits.
- **Acceptance criteria:**
  - Any CCXT-supported exchange configurable.
  - Spot and futures order support.
  - Fee calculation per exchange.
- **Test specs:**
  - Integration: Place BTC/USDT limit buy on Binance testnet. Verify fill.

#### F-EXE-005: Interactive Brokers backend
- **Priority:** P1
- **Spec:** Broker backend for options, commodities, and global equities via Interactive Brokers TWS/Gateway API. Handles complex order types (spreads, brackets, conditional orders).
- **Acceptance criteria:**
  - Connects to IB TWS/Gateway at configured host:port.
  - Options multi-leg order support.
  - Commodity futures support.
- **Test specs:**
  - Integration: Connect to IB paper account. Fetch account data. Verify balance returned.

#### F-EXE-006: TradingView webhook execution
- **Priority:** P0
- **Spec:** Bidirectional TradingView integration. **Inbound:** FastAPI webhook endpoint at `/webhook` receives TradingView alert JSON payloads (`{action, ticker, close, passphrase}`), validates HMAC passphrase, normalizes symbol, and routes to appropriate broker backend. **Outbound:** Python-generated signals relay to TradingView alert format for chart-based monitoring. Webhook supports ngrok for local development and direct hosting for production. Multiple TradingView alert formats supported (standard, pine script, custom JSON).
- **Acceptance criteria:**
  - Webhook server starts on configurable port.
  - HMAC passphrase validation rejects invalid alerts.
  - Incoming alerts parsed and routed to correct broker.
  - For Indian markets: TradingView alert → OpenAlgo → broker execution.
  - For US markets: TradingView alert → Alpaca.
- **Test specs:**
  - Unit: Send mock webhook with valid passphrase. Verify order routed to correct backend.
  - Unit: Send mock webhook with invalid passphrase. Verify rejected with 401.
  - Integration: Send real TradingView-format JSON to webhook. Verify parsing and routing.

#### F-EXE-007: User-selectable execution mode
- **Priority:** P0
- **Spec:** User configures `execution.mode: "both"` (or `"tradingview"` or `"python"`). In `both` mode, every signal generates BOTH a TradingView webhook alert AND a direct broker API order simultaneously. In `tradingview` mode, only webhooks fire. In `python` mode, only direct API calls execute. This is unique to NexusTrade — no other platform offers this flexibility.
- **Acceptance criteria:**
  - Three modes work correctly.
  - In `both` mode, orders fire to both paths simultaneously.
  - Duplicate fill prevention: if same order fills via both paths, only count once in portfolio.
- **Test specs:**
  - Unit: Mode=both. Verify both TradingView webhook AND broker API called.
  - Unit: Mode=tradingview. Verify only webhook called, broker API not called.
  - Unit: Mode=python. Verify only broker API called, webhook not called.

#### F-EXE-008: Paper trading with configurable slippage
- **Priority:** P0
- **Spec:** Built-in paper trading backend that simulates realistic execution. Configurable slippage models: (1) `fixed` — constant slippage per trade (e.g., 0.01%), (2) `percentage` — percentage of price (e.g., 0.05%), (3) `volume_based` — slippage increases with order size relative to volume, (4) `none` — perfect fills (default for quick testing). Also configurable: `fill_probability` (default 1.0), `latency_ms` (simulated execution delay), and commission structure per market.
- **Acceptance criteria:**
  - Paper backend tracks positions, PnL, and account balance in memory (and Redis for persistence).
  - Slippage model applied to all paper fills.
  - Fill probability can simulate partial fills and rejections.
  - Commission deducted from account on each trade.
- **Test specs:**
  - Unit: Place buy order with slippage=0.1%. Verify fill price is 0.1% worse than requested.
  - Unit: Place order with fill_probability=0.5. Verify ~50% rejection rate over 100 orders.
  - Unit: Verify PnL calculation: buy 100 shares at $150, sell at $160 = $1000 profit minus commissions.

---

### CATEGORY: Risk management

#### F-RSK-001: Pre-trade risk checks
- **Priority:** P0
- **Spec:** Before every order, validate: (1) max position size (default 5% of portfolio per position), (2) max portfolio risk (default 20% total drawdown), (3) market hours (reject orders outside trading hours unless crypto), (4) India circuit limit check (verify stock not at circuit limit), (5) F&O lot size validation (for Indian derivatives), (6) minimum cash reserve (keep configurable % in cash). All thresholds configurable in YAML.
- **Acceptance criteria:**
  - Orders rejected with clear reason when any check fails.
  - All thresholds configurable.
  - Checks run in <10ms (must not add latency to execution).
- **Test specs:**
  - Unit: Position would be 10% of portfolio, max is 5%. Verify rejection with message.
  - Unit: Market closed (Saturday). Equity order rejected. Crypto order allowed.
  - Unit: Stock at upper circuit limit. Buy order rejected.
  - Unit: F&O quantity 73, lot size 25. Verify rejection (must be multiple of lot size).

#### F-RSK-002: Multi-perspective risk debate
- **Priority:** P0
- **Spec:** Adapted from TradingAgents. Three risk assessment agents — Aggressive (pushes for larger positions), Conservative (reduces exposure), Neutral (balanced) — debate each proposed trade. A manager agent synthesizes the debate into final position sizing and risk parameters. Uses the `deep` LLM for high-quality reasoning.
- **Acceptance criteria:**
  - Three risk agents produce independent assessments.
  - Manager synthesizes into: approved/rejected, position size, stop-loss, take-profit.
  - Debate rounds configurable.
  - Can be disabled for speed (skip to quantitative sizing only).
- **Test specs:**
  - Unit: Mock three risk agents with different recommendations. Verify manager produces synthesized output.
  - Unit: Verify disabled mode skips debate entirely.

#### F-RSK-003: Quantitative position sizing
- **Priority:** P0
- **Spec:** Multiple sizing models selectable in config: (1) `cvar` — CVaR (Conditional VaR) at configurable confidence level, adapted from FinRL's CVaR-PPO, (2) `kelly` — Kelly Criterion optimal fraction based on win rate and payoff ratio, (3) `fixed_fraction` — fixed percentage of portfolio per trade, (4) `volatility` — ATR-based sizing (larger position in low-vol, smaller in high-vol), (5) `max_drawdown` — size based on maximum acceptable drawdown. Model selectable via `risk.sizing_model: "kelly"`.
- **Acceptance criteria:**
  - All 5 models implemented and selectable.
  - Models receive portfolio state and market data as inputs.
  - Output: position_size (quantity), stop_loss_price, take_profit_price.
- **Test specs:**
  - Unit: Kelly with 60% win rate, 2:1 payoff → optimal fraction = 0.2. Verify.
  - Unit: ATR-based with ATR=2.5, risk_per_trade=1% of $100K. Verify position size.
  - Unit: CVaR at 95% confidence with mock return distribution. Verify sizing respects tail risk.

#### F-RSK-004: Circuit breakers
- **Priority:** P0
- **Spec:** Automatic trading halt when configurable thresholds are breached: (1) `max_daily_loss_pct` — halt all trading when daily PnL drops below threshold (default: -3%), (2) `max_consecutive_losses` — halt after N consecutive losing trades (default: 5), (3) `max_open_positions` — prevent new positions when limit reached (default: 10), (4) `cooldown_minutes` — how long to halt before resuming (default: 60). Manual override available via CLI/API.
- **Acceptance criteria:**
  - Circuit breaker triggers automatically when threshold breached.
  - All trading halted (no new orders, existing positions maintained).
  - Cooldown timer counts down and auto-resumes.
  - Manual override to resume early or halt indefinitely.
  - Notification sent when circuit breaker triggers.
- **Test specs:**
  - Unit: Daily PnL = -3.5%, threshold = -3%. Verify circuit breaker triggers.
  - Unit: 5 consecutive losses, threshold = 5. Verify halt triggered.
  - Unit: Verify cooldown: breaker triggers, wait 60 min, verify auto-resume.
  - Unit: Verify manual override resumes trading before cooldown expires.

#### F-RSK-005: India-specific risk rules
- **Priority:** P0
- **Spec:** Additional risk checks for Indian markets: (1) Per-stock circuit limits (2-20%, fetched from exchange), (2) Market-wide circuit breakers (Nifty 10/15/20%), (3) Pre-open session restrictions (9:00-9:15 IST — only limit orders), (4) Broker rate limiting (Zerodha: 3 orders/sec, Angel: 10 orders/sec), (5) SEBI audit trail (log all automated trades with strategy name, order details, outcome), (6) F&O margin validation.
- **Acceptance criteria:**
  - Circuit limits auto-fetched from OpenAlgo's instruments data.
  - Rate limiter enforces broker-specific limits.
  - Audit trail logged to configurable path in structured format (JSON).
- **Test specs:**
  - Unit: Stock at 19% up (20% circuit). Buy order allowed. At 20% up: buy rejected.
  - Unit: 4 orders in 1 second to Zerodha (limit 3/sec). Verify 4th order queued.
  - Unit: Verify audit log entry contains: timestamp, strategy, symbol, action, quantity, price, broker, outcome.

---

### CATEGORY: Backtesting & strategy

#### F-BKT-001: Backtesting engine
- **Priority:** P0
- **Spec:** Historical replay engine that runs the full NexusTrade pipeline (data → agents → aggregation → risk → execution) against historical data. Adapted from Qlib's backtest module (walk-forward) + FinRL's Gym environment (transaction cost simulation). Outputs: total return, annualized return, Sharpe ratio, max drawdown, win rate, profit factor, trade count, average holding period. Configurable: date range, initial capital, commission structure, slippage model, rebalancing frequency.
- **Acceptance criteria:**
  - Replays configured strategy over historical date range.
  - Full agent pipeline runs for each decision point.
  - Transaction costs and slippage applied realistically.
  - Output report includes all standard metrics.
  - Supports walk-forward optimization (in-sample train + out-of-sample test).
- **Test specs:**
  - Unit: Backtest buy-and-hold AAPL 2024. Verify return matches actual AAPL 2024 return (within slippage tolerance).
  - Unit: Verify Sharpe ratio calculation: known returns → known Sharpe.
  - Unit: Verify max drawdown calculation: known price series → known drawdown.
  - Integration: Backtest a multi-agent strategy over 6 months. Verify report generated with all metrics.

#### F-BKT-002: YAML-based strategy definition
- **Priority:** P0
- **Spec:** Users define strategies in YAML combining agent signals with technical conditions and timeframe logic. A `StrategyInterface` ABC evaluates rules against current MarketContext + agent signals to produce entry/exit decisions. Strategy YAML supports: conditions (AND/OR logic), agent signal references (`buffett_agent.direction == "buy"`), technical indicator references (`rsi < 30`), timeframe conditions (`on_timeframe: "4h"`), and position management rules (take_profit, stop_loss, trailing_stop).
- **Example YAML strategy:**
```yaml
strategy:
  name: "Multi-TF Trend Following"
  entry:
    conditions:
      - all:  # AND logic
          - agent: "bull_bear_debate"
            direction: ["buy", "strong_buy"]
            min_confidence: 0.7
          - indicator: "rsi"
            timeframe: "1h"
            operator: "<"
            value: 40
          - indicator: "sma_50"
            timeframe: "4h"
            operator: ">"
            ref: "sma_200"  # golden cross
  exit:
    take_profit_pct: 3.0
    stop_loss_pct: 1.5
    trailing_stop_pct: 1.0
    conditions:
      - any:  # OR logic
          - agent: "risk_debate"
            direction: ["sell", "strong_sell"]
          - indicator: "rsi"
            timeframe: "1h"
            operator: ">"
            value: 80
```
- **Acceptance criteria:**
  - Strategy YAML parsed and validated at startup.
  - Entry and exit conditions evaluated correctly.
  - Agent signal references resolved from latest agent outputs.
  - Technical indicator references resolved from TradingView MCP or computed locally.
  - Strategies hot-reloadable (modify YAML, no restart).
- **Test specs:**
  - Unit: Parse example strategy YAML. Verify all conditions extracted correctly.
  - Unit: Mock agent returns BUY(0.8), RSI=35, SMA50 > SMA200. Verify entry condition = TRUE.
  - Unit: Mock agent returns BUY(0.8), RSI=50. Verify entry condition = FALSE (RSI not < 40).
  - Unit: Verify exit condition: RSI=85 → exit triggered (OR condition).

#### F-BKT-003: Multi-timeframe analysis
- **Priority:** P0
- **Spec:** The system supports analyzing multiple timeframes simultaneously for the same symbol. Configurable timeframe list: `timeframes: ["5m", "15m", "1h", "4h"]`. Each timeframe runs its own analysis cycle independently. Strategy conditions can reference specific timeframes. Scheduler config defines analysis frequency per timeframe.
- **Acceptance criteria:**
  - Multiple timeframes fetched and analyzed concurrently.
  - Strategy conditions reference specific timeframes.
  - Scheduler runs each timeframe's analysis at appropriate intervals.
- **Test specs:**
  - Unit: Configure 4 timeframes. Verify 4 parallel data fetch tasks launched.
  - Unit: Verify strategy condition referencing "4h" uses 4-hour OHLCV data, not 1h.

---

### CATEGORY: Infrastructure

#### F-INF-001: Event bus (Redis Streams)
- **Priority:** P0
- **Spec:** Asynchronous event bus for inter-service communication. Default implementation: Redis Streams (durable, replayable, sub-millisecond latency on single host). Events serialized as JSON (or protobuf for performance-critical paths). Event types: `market.data.{symbol}`, `market.enriched.{symbol}`, `agent.signal.{symbol}`, `signal.composite.{symbol}`, `risk.assessed.{symbol}`, `execution.order.{symbol}`, `execution.fill.{symbol}`, `system.alert`. Future: EventBusInterface ABC allowing Redis, Kafka, or InMemory implementations.
- **Acceptance criteria:**
  - Services publish and subscribe to typed event streams.
  - Events are durable (survive service restart).
  - Consumer groups prevent duplicate processing.
  - Event replay capability for debugging.
- **Test specs:**
  - Unit: Publish event to `market.data.AAPL`. Verify subscriber receives event.
  - Unit: Publish 1000 events. Verify all received in order.
  - Unit: Kill subscriber, publish events, restart subscriber. Verify missed events received.

#### F-INF-002: Docker Compose topology
- **Priority:** P0
- **Spec:** 9-service Docker Compose configuration: (1) `data-service` — OpenBB + TradingView MCP, (2) `agent-engine` — LangGraph agents, (3) `finrl-service` — DRL inference (GPU), (4) `fingpt-service` — sentiment analysis (GPU), (5) `qlib-service` — factor mining, (6) `llm-router` — LiteLLM, (7) `execution-engine` — broker APIs + webhooks, (8) `web-ui` — FastAPI + Streamlit, (9) `redis` — event bus + cache. GPU sharing between finrl-service and fingpt-service via NVIDIA MPS or time-slicing.
- **Acceptance criteria:**
  - `docker compose up` starts all services.
  - Services communicate via Redis and gRPC.
  - GPU services share GPU resource.
  - Health checks for all services.
  - `docker compose up --profile cpu-only` runs without GPU (disables FinRL/FinGPT containers).
- **Test specs:**
  - Integration: `docker compose up` succeeds with no errors.
  - Integration: Health check endpoints for all 9 services return 200.
  - Integration: Event published by data-service received by agent-engine.

#### F-INF-003: Plugin system
- **Priority:** P0
- **Spec:** All adapters (data providers, brokers, agents) discoverable via Python entry_points. Users install third-party plugins via pip: `pip install nexustrade-plugin-oanda`. Plugin registers its entry points in its own `pyproject.toml`. NexusTrade's registry discovers all plugins at startup. Built-in adapters use the same mechanism.
- **Acceptance criteria:**
  - Built-in adapters registered as entry_points in NexusTrade's pyproject.toml.
  - Third-party plugins install via pip and auto-discovered.
  - `nexus plugins list` CLI command shows all discovered plugins.
- **Test specs:**
  - Unit: Register mock entry_point. Verify registry discovers it.
  - Integration: Create a minimal plugin package with one agent. Install via pip. Verify discovered.

#### F-INF-004: Notification system
- **Priority:** P0
- **Spec:** `NotificationAdapter` interface with implementations for: Telegram (via python-telegram-bot), Discord (via discord.py webhooks), Email (via smtplib), and generic webhook (POST JSON to any URL). Notifications sent on: trade execution, circuit breaker trigger, system error, daily PnL summary. Each notification channel independently configurable and selectable per event type.
- **Acceptance criteria:**
  - Multiple channels active simultaneously.
  - Event-to-channel routing configurable (e.g., trades → Telegram, errors → Email).
  - Message templates configurable.
  - Rate limiting to prevent spam (max N notifications per minute per channel).
- **Test specs:**
  - Unit: Mock Telegram API. Trigger trade notification. Verify message sent with correct format.
  - Unit: Trigger 100 notifications in 1 second. Verify rate limiter caps at configured max.
  - Unit: Verify circuit breaker notification includes: reason, current PnL, threshold, resume time.

#### F-INF-005: Observability (logging, metrics, audit trail)
- **Priority:** P1
- **Spec:** Structured logging with configurable levels per service. Trade audit trail in JSON format for SEBI compliance. Metrics export for Prometheus (optional). Health check endpoints for all services. Adapted from OpenAlgo's traffic monitor pattern.
- **Acceptance criteria:**
  - Log levels configurable per service in YAML.
  - Trade audit trail includes: timestamp, strategy, symbol, action, quantity, price, broker, status, latency_ms.
  - Prometheus metrics endpoint (optional, disabled by default).
  - All services expose `/health` endpoint.
- **Test specs:**
  - Unit: Verify audit trail entry written on order execution.
  - Unit: Verify log level filtering: debug logs hidden when level=INFO.
  - Integration: Verify `/health` endpoints for all services.

#### F-INF-006: Scheduling system
- **Priority:** P0
- **Spec:** Configurable scheduler for analysis cycles. Supports: cron-style scheduling (`analysis_cron: "*/15 * * * *"` = every 15 minutes), interval-based (`analysis_interval: "4h"`), event-triggered (run on new data arrival), and market-session-based (run at market open, mid-day, close). Different schedules per timeframe and per market. Scheduler must handle timezone differences (IST for India, ET for US, UTC for crypto).
- **Acceptance criteria:**
  - Scheduler triggers analysis at configured times.
  - Different schedules per timeframe.
  - Timezone-aware scheduling.
  - Manual trigger via CLI/API.
- **Test specs:**
  - Unit: Configure 15-min interval. Verify analysis triggered every 15 minutes.
  - Unit: Configure market-session trigger for NSE open (9:15 IST). Verify trigger at correct UTC time.

---

### CATEGORY: User experience

#### F-UX-001: Web dashboard (Streamlit)
- **Priority:** P1
- **Spec:** Real-time monitoring dashboard built with Streamlit. Panels: portfolio overview (positions, PnL, balance), agent signals (latest signals from all agents), trade history (recent fills), risk status (circuit breaker state, risk utilization), and system health (service status, latency). Auto-refresh configurable.
- **Acceptance criteria:**
  - Dashboard accessible at configurable port (default 8501).
  - Real-time updates from Redis event bus.
  - All panels display current data.
  - Auto-refresh interval configurable.
- **Test specs:**
  - Integration: Start dashboard. Verify portfolio panel shows current positions from Redis.
  - Integration: Execute a trade. Verify trade appears in trade history panel within 5 seconds.

#### F-UX-002: CLI interface (Typer)
- **Priority:** P0
- **Spec:** Command-line interface via Typer: `nexus trade --config config.yaml` (run live trading), `nexus backtest --strategy strategy.yaml --from 2024-01-01 --to 2024-12-31` (run backtest), `nexus paper --config config.yaml` (paper trading mode), `nexus agents list` (list available agents), `nexus plugins list` (list installed plugins), `nexus webhook start --port 8888` (start webhook server), `nexus health` (check all service health).
- **Acceptance criteria:**
  - All commands work as described.
  - `--config` flag specifies YAML config path.
  - `--dry-run` flag logs actions without executing trades.
  - Colored output for terminal readability.
- **Test specs:**
  - Unit: `nexus agents list` outputs all registered agents.
  - Unit: `nexus health` returns status of all services.
  - Integration: `nexus paper --config examples/us_equities.yaml` starts paper trading.

---

### CATEGORY: Configurability

#### F-CFG-001: Layered configuration system
- **Priority:** P0
- **Spec:** Four-layer configuration with priority: (1) `config/default.yaml` — all defaults, (2) `config/{environment}.yaml` — environment overrides (production, development), (3) `.env` file — secrets (API keys, passwords), (4) CLI flags — runtime overrides. Pydantic BaseSettings validates all config with type safety. Environment variable override format: `NEXUS__LLM__MODE=hybrid` (double underscore for nesting).
- **Acceptance criteria:**
  - All config values have defaults in default.yaml.
  - Higher-priority layers override lower-priority.
  - Pydantic validates types (wrong type → clear error at startup).
  - Missing required values (API keys) → clear error message listing what's needed.
  - Hot-reload for non-critical config (prompts, agent weights) without restart.
- **Test specs:**
  - Unit: default.yaml has `llm.mode: "hybrid"`. Override in env: `NEXUS__LLM__MODE=local`. Verify final config = local.
  - Unit: Missing ALPACA_API_KEY. Verify startup error message includes the missing variable name.
  - Unit: Set `llm.mode: "invalid"`. Verify Pydantic validation error.

#### F-CFG-002: Full adapter composability
- **Priority:** P0
- **Spec:** Every major component is an adapter behind an interface. User can swap any component by changing YAML config — zero code changes required. This applies to: data providers, broker backends, agents, LLM providers, risk models, slippage models, notification channels, and event bus implementations. This is the core architectural principle that makes NexusTrade unique.
- **Acceptance criteria:**
  - Changing `execution.india.broker: "zerodha"` to `"dhan"` works without code changes.
  - Changing `llm.fast.provider: "ollama"` to `"openai"` works without code changes.
  - Adding a new agent requires only: implement AgentInterface + register entry_point.
  - Adding a new broker requires only: implement BrokerBackendInterface + register entry_point.
- **Test specs:**
  - Integration: Start with Alpaca backend. Change config to paper backend. Restart. Verify paper backend active.
  - Integration: Start with Ollama LLM. Change config to OpenAI. Restart. Verify OpenAI model called.

---

## 3. Non-functional requirements

#### NFR-001: Latency
- Analysis pipeline (data → agents → signal): < 30 seconds for a single symbol with 3 agents.
- Order execution (signal → broker API call): < 500ms.
- Pre-trade risk checks: < 10ms.
- FinBERT sentiment per headline: < 10ms.

#### NFR-002: Reliability
- System handles broker API failures gracefully (retry + fallback).
- Event bus survives service restarts (Redis persistence).
- No data loss on crash (all state in Redis/ChromaDB).

#### NFR-003: Security
- API keys stored in .env files, never in YAML or code.
- Webhook passphrase validated via HMAC.
- Local LLM mode ensures zero data leakage to external APIs.
- OpenAlgo handles broker authentication (TOTP, token refresh).

#### NFR-004: Scalability
- Single instance handles 50+ symbols across multiple markets.
- Docker Compose scales to multiple analysis workers.
- Redis Streams consumer groups enable horizontal scaling.

---

## 4. Out of scope (for MVP)

- Mobile app
- Multi-user / multi-tenant
- Plugin marketplace with ratings
- High-frequency trading (sub-second execution)
- Custom dashboard builder
- Social trading / signal sharing

---

## 5. Glossary

- **AgentInterface:** Abstract base class that all trading agents must implement.
- **BrokerBackendInterface:** Abstract base class that all execution broker adapters must implement.
- **DataProviderInterface:** Abstract base class that all data source adapters must implement.
- **MarketContext:** Data object containing all information an agent needs for analysis.
- **AgentSignal:** Standardized output from any agent: direction, confidence, reasoning.
- **OpenAlgo:** Open-source unified API for 30+ Indian brokers.
- **CCXT:** Open-source library for 100+ cryptocurrency exchanges.
- **LiteLLM:** Open-source library for unified LLM API calls across providers.
- **FinBERT:** Pre-trained BERT model for financial sentiment (110M params).
- **FinGPT:** LoRA fine-tuned LLMs for financial tasks.
- **FinRL:** Financial reinforcement learning framework.
- **Qlib:** Microsoft's quantitative investment platform.
