<p align="center">
  <h1 align="center">NexusTrade</h1>
  <p align="center">
    <strong>The unified open-source AI trading platform that combines 18 investor persona agents, multi-market execution, and enterprise-grade risk management into a single YAML-configurable system.</strong>
  </p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> &bull;
    <a href="#features">Features</a> &bull;
    <a href="#comparison">Comparison</a> &bull;
    <a href="#architecture">Architecture</a> &bull;
    <a href="#documentation">Docs</a> &bull;
    <a href="#contributing">Contributing</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+">
    <img src="https://img.shields.io/badge/license-Apache%202.0-green.svg" alt="License">
    <img src="https://img.shields.io/badge/tests-485%20passed-brightgreen.svg" alt="Tests">
    <img src="https://img.shields.io/badge/features-55%2F55-brightgreen.svg" alt="Features">
    <img src="https://img.shields.io/badge/agents-18%20personas-purple.svg" alt="Agents">
    <img src="https://img.shields.io/badge/markets-US%20%7C%20India%20%7C%20Crypto%20%7C%20Forex%20%7C%20Options%20%7C%20Commodities-orange.svg" alt="Markets">
  </p>
</p>

---

## What is NexusTrade?

NexusTrade is the **first platform to unify AI-powered multi-agent analysis, multi-market execution, and institutional-grade risk management** into a single open-source system. It combines the best ideas from 13 leading open-source trading projects (ai-hedge-fund, TradingAgents, FinRL, FinGPT, OpenBB, Qlib, CCXT, and more) behind clean, adapter-based interfaces.

**One YAML file. Any market. Any LLM. Any broker.**

```yaml
# Switch from paper to live trading — zero code changes
execution:
  mode: python          # python | tradingview | both
  brokers:
    - name: alpaca      # US equities
    - name: openalgo    # India (30+ brokers via OpenAlgo)
    - name: ccxt        # Crypto (100+ exchanges)

# Switch from local to cloud LLM — zero code changes
llm:
  mode: hybrid          # local | cloud | hybrid
  fast: ollama/llama3:8b
  deep: anthropic/claude-sonnet-4-20250514
```

---

## Why NexusTrade?

| Problem | How NexusTrade Solves It |
|---------|------------------------|
| Trading bots are single-market | Trade US stocks, Indian equities, crypto, forex, options, and commodities from one platform |
| AI trading projects are demos, not systems | 55 production features with 485 tests, Docker deployment, CI/CD pipeline |
| No project combines LLM + RL + NLP agents | 18 investor persona agents + bull/bear debate + FinBERT sentiment + FinRL deep RL + vision analysis |
| Switching brokers requires code changes | YAML-driven adapter system — change one line to switch brokers |
| Indian market support is an afterthought | First-class NSE/BSE support with SEBI-compliant audit trail, circuit limit validation, F&O lot sizes |
| Risk management is bolted on | Built-in pre-trade checks, 5 position sizing models, circuit breakers, multi-perspective risk debate |

---

<a name="comparison"></a>
## Comparison with Existing Projects

### Feature Comparison

| Feature | NexusTrade | ai-hedge-fund | TradingAgents | FinRL | OctoBot | Qlib |
|---------|:----------:|:-------------:|:-------------:|:-----:|:-------:|:----:|
| **Multi-agent ensemble** | 18 agents + debate + RL + NLP + vision | 18 agents (LLM only) | Bull/bear debate | RL only | Rule-based | Factor-based |
| **US equities** | Alpaca | Alpaca | - | Alpaca | - | - |
| **Indian equities (NSE/BSE)** | 30+ brokers via OpenAlgo | - | - | - | - | - |
| **Crypto (100+ exchanges)** | CCXT | - | - | CCXT | CCXT | - |
| **Forex** | TradingView + OpenBB | - | - | - | - | - |
| **Options (Greeks, multi-leg)** | IB + OpenBB | - | - | - | - | - |
| **Commodities (futures)** | IB + rollover mgmt | - | - | - | - | - |
| **TradingView integration** | MCP + webhooks | - | - | - | Webhooks | - |
| **Local LLM (Ollama)** | Full support | Partial | Partial | - | - | - |
| **Hybrid LLM (local + cloud)** | 3-channel routing | - | Dual LLM | - | - | - |
| **Per-agent LLM config** | YAML override per agent | - | - | - | - | - |
| **Bull/bear debate** | Configurable rounds + early termination | - | Fixed rounds | - | - | - |
| **FinBERT sentiment** | Recency-weighted | - | - | - | - | - |
| **Deep RL (PPO/A2C)** | Docker-isolated FinRL | - | - | Native | - | - |
| **Vision chart analysis** | Via vision LLM | - | - | - | - | - |
| **Factor mining** | Docker-isolated Qlib | - | - | - | - | Native |
| **Market memory (ChromaDB)** | Configurable retention | - | Basic | - | - | - |
| **Signal aggregation** | 4 modes | Portfolio manager only | - | - | - | - |
| **DAG execution order** | Topological sort | Sequential | Sequential | - | - | - |
| **Pre-trade risk checks** | Configurable thresholds | Basic | - | - | - | - |
| **Position sizing models** | Kelly, CVaR, fixed, volatility, max DD | - | - | CVaR | Fixed | - |
| **Circuit breakers** | With cooldown timer | - | - | - | - | - |
| **India-specific risk (SEBI)** | Circuit limits, F&O lots, audit trail | - | - | - | - | - |
| **Multi-perspective risk debate** | 3-perspective LLM debate | - | - | - | - | - |
| **Backtesting engine** | With strategy metrics | Basic | - | Advanced | - | Advanced |
| **YAML strategy DSL** | Conditions + agent signals | - | - | - | Python | Python |
| **Multi-timeframe analysis** | Concurrent weighted merge | - | - | - | - | - |
| **Paper trading** | Configurable slippage + commission | - | - | Simulated | Virtual | Simulated |
| **Event bus (Redis Streams)** | Pub/sub with consumer groups | - | - | - | - | - |
| **Docker Compose deployment** | 9 services, GPU profiles | - | - | Docker | Docker | - |
| **Plugin system (entry_points)** | Auto-discovery | - | - | - | Tentacles | - |
| **Notifications** | Telegram, Discord, Email, Webhook | - | - | - | Telegram | - |
| **Prometheus metrics** | Counters, histograms, gauges | - | - | - | - | - |
| **Web dashboard** | Streamlit (5 pages) | - | - | - | Web UI | - |
| **CLI** | Typer with Rich output | - | - | - | CLI | CLI |
| **CI/CD pipeline** | GitHub Actions | - | - | - | - | - |
| **Config system** | 4-layer YAML + env + Pydantic | - | Env vars | Config | JSON | YAML |
| **Total features** | **55** | **~15** | **~10** | **~20** | **~25** | **~20** |
| **Test count** | **485** | ~50 | ~20 | ~100 | ~200 | ~300 |
| **License** | Apache-2.0 | MIT | Apache-2.0 | MIT | GPL-3.0 | MIT |

### Architecture Comparison

| Aspect | NexusTrade | Others |
|--------|-----------|--------|
| **Design pattern** | Everything is an adapter behind ABCs | Monolithic or tightly coupled |
| **Config-driven** | Change behavior via YAML, no code changes | Requires code changes to switch providers |
| **Multi-market** | Simultaneous US + India + Crypto + Forex | Single market per instance |
| **LLM routing** | Fast/Deep/Vision channels with fallback | Single provider |
| **Risk management** | Integrated pipeline (pre-trade + sizing + circuit breaker) | Separate or missing |
| **Deployment** | `make up` (Docker) or `pip install` | Manual setup |

---

<a name="features"></a>
## Features (55 total)

### Markets & Assets (7)
- US equities via Alpaca (paper + live)
- Indian equities via OpenAlgo (Zerodha, Dhan, Angel One, and 27+ more)
- Crypto via CCXT (Binance, Coinbase, Kraken, and 100+ exchanges)
- Forex via OpenBB + TradingView MCP
- Options with Greeks (delta, gamma, theta, vega, IV), multi-leg orders
- Commodities with futures contracts, rollover management, symbol resolution
- Multi-market simultaneous operation with per-market broker routing

### AI Agents (11)
- Universal agent interface (ABC) with entry_points plugin discovery
- 18 investor persona agents (Warren Buffett, Charlie Munger, Ray Dalio, George Soros, Jim Simons, and 13 more)
- Bull/bear adversarial debate with configurable rounds and early termination
- Deep reinforcement learning agents via FinRL (PPO, A2C, TD3)
- FinBERT + FinGPT sentiment analysis with recency-weighted aggregation
- Vision-based chart analysis via vision LLM
- Auto factor mining via Qlib + RD-Agent
- Market situation memory with ChromaDB (similarity search, retention policy)
- Heterogeneous agent ensemble (LLM + RL + NLP + Vision + Factor)
- Signal aggregation (4 modes: weighted confidence, majority, unanimous, portfolio manager)
- Configurable execution order (parallel, sequential, DAG with dependency resolution)

### LLM Configuration (6)
- Multi-provider routing via LiteLLM (OpenAI, Anthropic, Google, Groq, DeepSeek, Ollama)
- Local LLM support (Ollama — runs entirely offline)
- Hybrid mode (fast tasks on local, deep analysis on cloud)
- Per-agent LLM configuration (model, temperature, max_tokens per agent)
- Customizable Jinja2 prompt templates with hot-reload
- LoRA fine-tuned financial models via FinGPT

### Data Sources (7)
- Unified data provider interface (ABC)
- OpenBB adapter (30+ sub-providers, all asset classes)
- TradingView MCP adapter (stdio transport, real-time chart data via Chrome DevTools)
- Broker data adapter (OpenAlgo historical data for Indian markets)
- CCXT data adapter (100+ crypto exchanges)
- Smart data routing (priority-based provider selection with automatic fallback)
- 3-level data caching (memory LRU -> Redis -> disk, configurable TTL per data type)

### Execution (8)
- Unified broker backend interface (ABC)
- OpenAlgo backend (30+ Indian brokers through one API)
- Alpaca backend (US equities, paper + live, fractional shares)
- CCXT broker backend (100+ crypto exchanges, sandbox/testnet support)
- Interactive Brokers backend (US equities, forex, options, commodities)
- TradingView webhook execution (send/receive alerts, HMAC validation)
- User-selectable execution mode (Python API / TradingView / Both simultaneously)
- Paper trading with configurable slippage and commission models

### Risk Management (5)
- Pre-trade risk checks (position size limits, portfolio exposure, market hours)
- Multi-perspective risk debate (aggressive/conservative/neutral LLM agents)
- 5 quantitative position sizing models (Kelly Criterion, CVaR, fixed fraction, volatility-based, max drawdown)
- Circuit breakers (daily loss limit, consecutive loss limit, cooldown timer, manual override)
- India-specific risk rules (circuit limit validation, F&O lot sizes, rate limiting, SEBI audit trail)

### Backtesting & Strategy (3)
- Backtesting engine (Sharpe ratio, max drawdown, win rate, profit factor, buy-and-hold benchmark)
- YAML-based strategy definition (entry/exit rules with AND/OR logic, agent signal + indicator conditions)
- Multi-timeframe analysis (concurrent data fetch, weighted signal merging across timeframes)

### Infrastructure (6)
- Event bus (Redis Streams with consumer groups, event acknowledgment)
- Docker Compose topology (9 services, cpu-only and full GPU profiles)
- Plugin system (importlib entry_points auto-discovery for all adapter types)
- Notification system (Telegram, Discord, Email, Webhook with configurable routing)
- Observability (structured logging, Prometheus metrics, SEBI-compliant audit trail)
- Scheduling system (cron, interval, market-session-based triggers with timezone support)

### User Experience (2)
- Streamlit web dashboard (5 pages: overview, portfolio, agents, config, health)
- Typer CLI with Rich output (trade, backtest, paper, agents, plugins, health)

### Configuration (2)
- 4-layer config system (YAML defaults -> env overrides -> .env file -> CLI flags, Pydantic validated)
- Full adapter composability (swap any component via YAML — zero code changes)

---

<a name="quick-start"></a>
## Quick Start

### Option 1: Local Development

```bash
# Clone
git clone https://github.com/shubhvisputek/NexusTrade.git
cd NexusTrade

# Install (requires Python 3.12+)
pip install uv
uv sync --extra all

# Run tests
uv run pytest tests/ -v

# Start paper trading
uv run nexus paper --config config/examples/us_equities_basic.yaml

# Start dashboard
uv run streamlit run src/nexustrade/web/dashboard.py

# Run backtest
uv run nexus backtest --strategy config/examples/strategy_basic.yaml --from 2024-01-01 --to 2024-12-31
```

### Option 2: Docker Deployment

```bash
# Clone
git clone https://github.com/shubhvisputek/NexusTrade.git
cd NexusTrade
cp .env.example .env  # Edit with your API keys

# Start all services (CPU-only profile)
make up

# Or with GPU support (FinRL, FinGPT, Qlib)
make up-full

# Check health
make logs
curl http://localhost:8085/health
```

### Option 3: Production Deployment

```bash
# Build and deploy
./scripts/deploy.sh cpu-only --build

# Access
# Dashboard:  http://localhost:8501
# API:        http://localhost:8085
# Metrics:    http://localhost:8085/metrics
# Webhook:    http://localhost:8888/webhook
```

### Available Make Targets

```
make help            Show all targets
make setup           Install all dependencies
make dev             Start dev services (Redis + Ollama)
make test            Run all tests
make test-unit       Run unit tests only
make lint            Run ruff + mypy
make build           Build Docker images
make up              Start services (cpu-only)
make up-full         Start services (with GPU)
make down            Stop all services
make deploy          Build + start production
make clean           Remove containers and caches
```

---

<a name="architecture"></a>
## Architecture

```
                          YAML Config
                              |
                    +---------+---------+
                    |   Config Layer    |  Pydantic validation
                    |  (4-layer merge)  |  env var override
                    +---------+---------+
                              |
              +---------------+----------------+
              |               |                |
      +-------+-------+ +----+----+  +--------+--------+
      | Data Layer     | | Agent   |  | Execution Layer |
      | (5 adapters)   | | Engine  |  | (6 backends)    |
      +-------+-------+ +----+----+  +--------+--------+
              |               |                |
   +----------+----------+   |     +----------+----------+
   | OpenBB | CCXT | Yahoo|  |     | Alpaca | OpenAlgo   |
   | TV MCP | Broker Data |  |     | CCXT   | IB | Paper |
   +---------+------------+  |     | TradingView Webhook |
              |               |     +---------------------+
   +----------+----------+   |
   | 3-Level Cache       |   |     +---------------------+
   | Memory->Redis->Disk |   |     | Risk Engine         |
   +---------------------+   |     | Pre-trade + Sizing  |
                              |     | Circuit Breakers    |
              +---------------+     | India Rules         |
              |                     +---------------------+
   +----------+-------------------------------------------+
   | 18 Persona Agents  | Bull/Bear Debate  | FinBERT    |
   | FinRL (Docker/gRPC) | FinGPT (Docker)  | Qlib       |
   | Vision Analysis     | Market Memory    |            |
   +--------------------+------------------+-------------+
              |
   +----------+----------+
   | Signal Aggregation  |  4 modes: weighted, majority,
   | + DAG Executor      |  unanimous, portfolio_manager
   +---------------------+
              |
   +----------+----------+
   | Event Bus           |  Redis Streams
   | (pub/sub + groups)  |  consumer groups
   +---------------------+
              |
   +----------+----------+     +---------------------+
   | Scheduler           |     | Notifications       |
   | cron/interval/market |     | Telegram | Discord  |
   +---------------------+     | Email | Webhook     |
                                +---------------------+
              |
   +----------+-----------------------------------------+
   | Web Layer                                          |
   | FastAPI REST API  |  Streamlit Dashboard  |  CLI   |
   | /health /signals  |  5-page UI            |  nexus |
   | /portfolio /config |  portfolio, agents    |  trade |
   | /metrics          |  config, health       |  paper |
   +----------------------------------------------------+
```

### Key Design Principles

1. **Everything is an adapter** — Data, brokers, agents, notifications, risk models — all behind ABCs
2. **Config drives behavior** — YAML -> env vars -> CLI flags. Pydantic validates everything
3. **Redis Streams as event bus** — All inter-service communication goes through Redis
4. **Entry_points for plugins** — All adapters registered in pyproject.toml, auto-discovered
5. **Docker for dependency isolation** — FinRL, FinGPT, Qlib in separate containers with gRPC
6. **LiteLLM for LLM routing** — One API for all providers, 3 channels: fast/deep/vision
7. **asyncio throughout** — All I/O-bound operations are async

---

## Example Configurations

<details>
<summary><b>US Equities with Alpaca (Paper Trading)</b></summary>

```yaml
markets:
  us_equity:
    symbols: [AAPL, MSFT, GOOGL, AMZN, TSLA]
    timeframes: [1h, 1d]

llm:
  mode: local
  fast: ollama/llama3:8b

agents:
  enabled:
    - {name: warren_buffett, type: ai_hedge_fund}
    - {name: technical_analyst, type: ai_hedge_fund}
    - {name: bull_bear_debate, type: trading_agents}

execution:
  mode: python
  brokers:
    - {name: alpaca, paper: true}
```
</details>

<details>
<summary><b>Indian Equities with Zerodha via OpenAlgo</b></summary>

```yaml
markets:
  india_equity:
    symbols: [RELIANCE, TCS, INFY, HDFCBANK]
    timeframes: [1h, 1d]

execution:
  mode: python
  brokers:
    - {name: openalgo, broker: zerodha}

risk:
  india_rules:
    circuit_limit_check: true
    fno_lot_validation: true
    sebi_audit_trail: true
```
</details>

<details>
<summary><b>Multi-Market (US + India + Crypto)</b></summary>

```yaml
markets:
  us_equity:
    symbols: [AAPL, MSFT]
  india_equity:
    symbols: [RELIANCE, TCS]
  crypto:
    symbols: [BTC/USDT, ETH/USDT]

execution:
  mode: python
  brokers:
    - {name: alpaca, markets: [us_equity]}
    - {name: openalgo, markets: [india_equity], broker: zerodha}
    - {name: ccxt, markets: [crypto], exchange: binance, sandbox: true}
```
</details>

<details>
<summary><b>Crypto with CCXT on Binance</b></summary>

```yaml
markets:
  crypto:
    symbols: [BTC/USDT, ETH/USDT, SOL/USDT]
    timeframes: [1h, 4h, 1d]

execution:
  brokers:
    - {name: ccxt, exchange: binance, sandbox: true}

agents:
  enabled:
    - {name: technical_analyst, type: ai_hedge_fund}
    - {name: finbert, type: finbert}
```
</details>

---

## Supported Brokers & Exchanges

### US Markets
| Broker | Type | Paper Trading | Live Trading |
|--------|------|:---:|:---:|
| Alpaca | Stocks + Crypto | Yes | Yes |
| Interactive Brokers | Stocks + Options + Forex + Commodities | Yes | Yes |

### Indian Markets (via OpenAlgo)
| Broker | Type | Status |
|--------|------|--------|
| Zerodha (Kite) | Equity + F&O | Supported |
| Dhan | Equity + F&O | Supported |
| Angel One | Equity + F&O | Supported |
| Fyers | Equity + F&O | Supported |
| Upstox | Equity + F&O | Supported |
| ICICI Direct | Equity | Supported |
| Kotak Neo | Equity + F&O | Supported |
| **+ 23 more** | Via OpenAlgo | Supported |

### Crypto Exchanges (via CCXT)
Binance, Coinbase, Kraken, Bybit, OKX, KuCoin, Bitfinex, Gate.io, and **100+ more**.

### Universal
| Backend | Markets | Notes |
|---------|---------|-------|
| TradingView Webhooks | Any TV-supported market | Send/receive alerts |
| Paper Trading | All markets | Built-in with configurable slippage |

---

## Standing on the Shoulders of Giants

NexusTrade is built by studying the architectures and patterns of these outstanding open-source projects. We don't copy code — we learn from the best and build our own clean implementations behind universal interfaces.

| Project | What We Learned | Stars | License |
|---------|----------------|:-----:|---------|
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 18 investor persona agent designs, LLM factory pattern, portfolio manager aggregation | 45.7K+ | MIT |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Bull/bear adversarial debate, dual-LLM architecture, ChromaDB market memory | 46.6K+ | Apache-2.0 |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | Deep reinforcement learning for trading, observation vector construction, CVaR risk | 14.7K+ | MIT |
| [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | LoRA fine-tuned financial LLMs, sentiment analysis pipelines | 19K+ | MIT |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) | Data provider Fetcher pattern, extension system via entry_points, 30+ data sources | 65K+ | Apache-2.0 |
| [Qlib](https://github.com/microsoft/qlib) | Factor mining expression DSL, multi-level cache, walk-forward backtesting | 15K+ | MIT |
| [RD-Agent](https://github.com/microsoft/RD-Agent) | LLM-driven autonomous factor discovery pipeline | 11.2K+ | MIT |
| [OctoBot](https://github.com/Drakkar-Software/OctoBot) | Docker topology, TradingView webhook integration, multi-timeframe evaluators | 5K+ | GPL-3.0 |
| [QuantAgent](https://github.com/Y-Research-SBU/QuantAgent) | Vision-based chart pattern recognition via LLM | 1.3K+ | MIT |
| [OpenAlgo](https://github.com/marketcalls/openalgo) | Unified Indian broker API, SEBI audit trail, TradingView webhook receiver | 3K+ | AGPL-3.0 |
| [CCXT](https://github.com/ccxt/ccxt) | Unified crypto exchange API pattern, 100+ exchange support | 33K+ | MIT |
| [LiteLLM](https://github.com/BerriAI/litellm) | Unified LLM provider API, 100+ provider support | 15K+ | MIT |
| [tradingview-mcp](https://github.com/shubhvisputek/tradingview-mcp) | TradingView Desktop automation via Chrome DevTools Protocol, 78 MCP tools | - | MIT |

**Total combined star count of referenced projects: ~340K+**

---

<a name="documentation"></a>
## Documentation

| Document | Description |
|----------|-------------|
| [Product Requirements](docs/01_PRD.md) | All 55 features with acceptance criteria |
| [Feature Sourcing](docs/02_FEATURE_SOURCING.md) | OSS project references for each feature |
| [Tech Stack](docs/03_TECH_STACK.md) | Packages, versions, dependencies |
| [Architecture](docs/04_ARCHITECTURE.md) | Interfaces, data models, config schemas |
| [Integration Guide](docs/05_INTEGRATION_GUIDE.md) | Step-by-step build order |

---

## Project Stats

| Metric | Value |
|--------|-------|
| Source files | 87 |
| Test files | 49 |
| Total tests | 485 (passing) |
| Features implemented | 55/55 |
| Agent personas | 18 |
| Supported markets | 6 (US, India, Crypto, Forex, Options, Commodities) |
| Broker backends | 6 (Alpaca, OpenAlgo, CCXT, IB, TradingView, Paper) |
| Data providers | 5 (OpenBB, CCXT, Yahoo, TradingView MCP, Broker Data) |
| Position sizing models | 5 (Kelly, CVaR, Fixed, Volatility, Max Drawdown) |
| Aggregation modes | 4 (Weighted, Majority, Unanimous, Portfolio Manager) |
| Notification channels | 4 (Telegram, Discord, Email, Webhook) |
| Docker services | 9 (+Ollama) |

---

<a name="contributing"></a>
## Contributing

We welcome contributions! NexusTrade is designed to be extensible — every component is an adapter behind an ABC.

### Adding a new broker
1. Create `src/nexustrade/execution/backends/your_broker.py`
2. Implement `BrokerBackendInterface`
3. Register in `pyproject.toml` entry-points
4. Done — it's auto-discovered

### Adding a new agent
1. Create `src/nexustrade/agents/adapters/your_agent.py`
2. Implement `AgentInterface`
3. Add a Jinja2 prompt template in `config/prompts/`
4. Register in `pyproject.toml` entry-points

### Adding a new data provider
1. Create `src/nexustrade/data/adapters/your_provider.py`
2. Implement `DataProviderInterface`
3. Register in `pyproject.toml` entry-points

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## Roadmap

- [ ] Live trading loop (data -> agents -> risk -> execution pipeline)
- [ ] Real-time WebSocket streaming for all data providers
- [ ] Mobile companion app (React Native)
- [ ] Community agent marketplace
- [ ] Cloud-hosted version with user authentication
- [ ] Advanced backtesting (walk-forward, Monte Carlo)
- [ ] Portfolio rebalancing strategies
- [ ] Social sentiment (Twitter/Reddit integration)
- [ ] Voice-controlled trading via Claude

---

## License

Licensed under the [Apache License 2.0](LICENSE).

NexusTrade does not copy code from any referenced project. All implementations are original, built by studying open-source architectures and patterns. See [Feature Sourcing](docs/02_FEATURE_SOURCING.md) for the complete attribution map.

---

## Disclaimer

NexusTrade is software for research and educational purposes. Trading financial instruments carries significant risk. Past performance does not guarantee future results. Always paper trade first and understand the risks before using real money. The authors are not responsible for any financial losses incurred through the use of this software.

---

<p align="center">
  <sub>Built with AI assistance by <a href="https://github.com/shubhvisputek">Shubham Vispute</a></sub>
</p>
