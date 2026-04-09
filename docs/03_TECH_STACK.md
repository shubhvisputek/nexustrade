# NexusTrade — Technology stack

> **Version:** 1.0  
> **Purpose:** Every technology choice, exact version, rationale for selection, alternatives considered, and how each connects to other components. Claude Code should use this to set up the development environment and resolve dependency decisions.

---

## 1. Language & runtime

| Technology | Version | Purpose | Rationale |
|-----------|---------|---------|-----------|
| **Python** | 3.12+ | Primary language for all services | Ecosystem: all referenced OSS projects are Python. AI/ML libraries are Python-first. Type hints with 3.12 features. |
| **TypeScript** | 5.x | TradingView MCP servers (if running locally) | Some TV MCP servers are TypeScript. NexusTrade core is Python-only. |
| **Node.js** | 20 LTS | Required for TradingView MCP servers | Only for external tool execution, not NexusTrade core. |

---

## 2. Core framework & libraries

### 2.1 Agent orchestration

| Library | Version | Purpose | Used by |
|---------|---------|---------|---------|
| **LangGraph** | >=0.2.0 | Multi-agent workflow orchestration: agent DAGs, debate loops, conditional routing | Agent engine service — all multi-agent workflows |
| **LangChain Core** | >=0.3.0 | Base abstractions (messages, prompts, output parsers) | Agent engine service |
| **LiteLLM** | >=1.50.0 | Unified LLM API across 100+ providers (OpenAI, Anthropic, Ollama, DeepSeek, Gemini, Groq) | LLM router service |
| **ChromaDB** | >=0.5.0 | Vector database for market situation memory (embeddings storage + similarity search) | Agent engine service (memory module) |

**Why LangGraph over alternatives:** LangGraph supports stateful multi-agent workflows with conditional edges — required for the debate mechanism and DAG-based agent execution. AutoGen and CrewAI were considered but have less flexibility for custom state management.

**Why LiteLLM over direct SDKs:** LiteLLM provides ONE function (`completion()`) that works with ALL providers, handling API format differences automatically. Without it, we'd need separate SDKs for each provider and custom retry/fallback logic.

### 2.2 Data & market access

| Library | Version | Purpose | Used by |
|---------|---------|---------|---------|
| **OpenBB** | >=4.3.0 | Financial data platform (equities, forex, crypto, commodities, fundamentals, news) | Data service |
| **CCXT** | >=4.4.0 | Cryptocurrency exchange unified API (100+ exchanges) | Data service + execution engine (crypto) |
| **alpaca-py** | >=0.30.0 | US equity + crypto broker API (paper + live) | Execution engine (US) |
| **httpx** | >=0.27.0 | Async HTTP client for OpenAlgo REST API calls | Execution engine (India) |
| **yfinance** | >=0.2.40 | Fallback data provider (free, no API key) | Data service (fallback) |

**Why OpenBB as primary data layer:** 300K+ symbols, 30+ sub-providers, Pydantic-validated outputs, and built-in MCP server. No other single library covers this breadth. OpenBB also handles provider fallback internally.

**Why CCXT:** De facto standard for crypto exchange access. 100+ exchanges through one unified API. FinRL and OctoBot both use it.

### 2.3 Machine learning & NLP

| Library | Version | Purpose | Used by | Container |
|---------|---------|---------|---------|-----------|
| **PyTorch** | >=2.2.0 | Deep learning runtime for FinBERT and FinGPT inference | fingpt-service | GPU container |
| **transformers** | >=4.44.0 | HuggingFace model loading (FinBERT, base models for FinGPT) | fingpt-service | GPU container |
| **PEFT** | >=0.12.0 | LoRA adapter loading for FinGPT fine-tuned models | fingpt-service | GPU container |
| **bitsandbytes** | >=0.43.0 | 4/8-bit quantization for running large models on consumer GPUs | fingpt-service | GPU container |
| **stable-baselines3** | >=2.3.0 | Reinforcement learning algorithms (PPO, A2C, DDPG, TD3, SAC) | finrl-service | GPU container |
| **gymnasium** | >=0.29.0 | RL environment interface for trading environments | finrl-service | GPU container |
| **qlib** | >=0.9.6 | Quantitative factor computation (Alpha158/360), backtesting | qlib-service | CPU container |

**Critical dependency isolation:** PyTorch + transformers + PEFT + bitsandbytes (FinGPT) and stable-baselines3 + gymnasium (FinRL) have conflicting transitive dependencies. They MUST run in separate Docker containers.

### 2.4 Web framework & API

| Library | Version | Purpose | Used by |
|---------|---------|---------|---------|
| **FastAPI** | >=0.115.0 | REST API server (webhook receiver, management API, health checks) | Execution engine, web UI service |
| **Uvicorn** | >=0.30.0 | ASGI server for FastAPI | All FastAPI services |
| **Streamlit** | >=1.38.0 | Monitoring dashboard (real-time portfolio, signals, risk status) | Web UI service |
| **Typer** | >=0.12.0 | CLI framework (`nexus trade`, `nexus backtest`, `nexus agents list`) | CLI interface |
| **Rich** | >=13.7.0 | Terminal output formatting (colored tables, progress bars) | CLI interface |

### 2.5 Infrastructure & messaging

| Library | Version | Purpose | Used by |
|---------|---------|---------|---------|
| **Redis** | 7.x (server) | Event bus (Redis Streams), caching, state storage | All services |
| **redis[asyncio]** | >=5.0.0 | Async Python Redis client | All services |
| **grpcio** | >=1.66.0 | High-performance RPC for ML inference calls between containers | Agent engine ↔ finrl-service, fingpt-service |
| **grpcio-tools** | >=1.66.0 | Protobuf compiler for gRPC service definitions | Build-time only |
| **Pydantic** | >=2.9.0 | Data validation, settings management, config schema definition | All services (config system) |
| **Pydantic-Settings** | >=2.5.0 | Environment variable loading with nested config support | Config service |

**Why Redis Streams over alternatives:**
- vs Kafka: Redis is simpler to deploy (single binary), sufficient for single-host trading systems, sub-millisecond latency. Kafka is overkill until >10K events/sec.
- vs RabbitMQ: Redis Streams has built-in consumer groups, persistence, and replay. RabbitMQ doesn't persist messages by default.
- vs In-memory queues: Redis survives service restarts. In-memory loses events on crash.

### 2.6 Notifications

| Library | Version | Purpose |
|---------|---------|---------|
| **python-telegram-bot** | >=21.0 | Telegram notifications |
| **aiosmtplib** | >=3.0 | Async email notifications |
| **httpx** | (same as above) | Discord webhook + generic webhook notifications |

### 2.7 Utilities

| Library | Version | Purpose |
|---------|---------|---------|
| **Jinja2** | >=3.1.0 | Prompt template rendering |
| **PyYAML** | >=6.0 | YAML config file loading |
| **tenacity** | >=9.0.0 | Configurable retry logic for broker API calls |
| **schedule** | >=1.2.0 | Lightweight job scheduling (analysis intervals) |
| **pytz** / **zoneinfo** | stdlib | Timezone handling (IST, ET, UTC) |
| **pandas** | >=2.2.0 | DataFrame operations for factor computation and backtesting |
| **numpy** | >=1.26.0 | Numerical operations |
| **matplotlib** | >=3.9.0 | Chart generation for QuantAgent vision analysis |

---

## 3. Development tools

| Tool | Version | Purpose |
|------|---------|---------|
| **uv** | >=0.4.0 | Package manager and workspace management (10-100x faster than pip) |
| **Docker** | >=24.0 | Container runtime |
| **Docker Compose** | >=2.29.0 | Multi-container orchestration |
| **pytest** | >=8.3.0 | Test framework |
| **pytest-asyncio** | >=0.24.0 | Async test support |
| **pytest-cov** | >=5.0.0 | Test coverage reporting |
| **ruff** | >=0.6.0 | Linting + formatting (replaces flake8 + black + isort) |
| **mypy** | >=1.11.0 | Static type checking |
| **pre-commit** | >=3.8.0 | Git hooks for lint/format on commit |

---

## 4. Package structure

```toml
# pyproject.toml — root workspace
[project]
name = "nexustrade"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "pyyaml>=6.0",
    "redis>=5.0.0",
    "jinja2>=3.1.0",
    "typer>=0.12.0",
    "rich>=13.7.0",
    "httpx>=0.27.0",
    "tenacity>=9.0.0",
]

[project.optional-dependencies]
agents = [
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    "litellm>=1.50.0",
    "chromadb>=0.5.0",
]
data = [
    "openbb>=4.3.0",
    "yfinance>=0.2.40",
    "ccxt>=4.4.0",
]
execution = [
    "alpaca-py>=0.30.0",
    "ccxt>=4.4.0",
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
]
ml = [
    "torch>=2.2.0",
    "transformers>=4.44.0",
    "peft>=0.12.0",
    "stable-baselines3>=2.3.0",
    "gymnasium>=0.29.0",
]
qlib = ["qlib>=0.9.6"]
web = ["streamlit>=1.38.0"]
notifications = [
    "python-telegram-bot>=21.0",
    "aiosmtplib>=3.0",
]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
]
all = ["nexustrade[agents,data,execution,ml,qlib,web,notifications,dev]"]

[project.scripts]
nexus = "nexustrade.cli.main:app"

[project.entry-points."nexustrade.data"]
openbb = "nexustrade.data.adapters.openbb_adapter:OpenBBAdapter"
tradingview_mcp = "nexustrade.data.adapters.tradingview_mcp:TradingViewMCPAdapter"
ccxt = "nexustrade.data.adapters.ccxt_data:CCXTDataAdapter"
broker_data = "nexustrade.data.adapters.broker_data:BrokerDataAdapter"
yahoo = "nexustrade.data.adapters.yahoo:YahooFinanceAdapter"

[project.entry-points."nexustrade.brokers"]
alpaca = "nexustrade.execution.backends.alpaca:AlpacaBackend"
openalgo = "nexustrade.execution.backends.openalgo:OpenAlgoBackend"
ccxt_broker = "nexustrade.execution.backends.ccxt_broker:CCXTBrokerBackend"
ib = "nexustrade.execution.backends.ib:IBBackend"
paper = "nexustrade.execution.backends.paper:PaperBackend"
tradingview = "nexustrade.execution.backends.tradingview:TradingViewBackend"

[project.entry-points."nexustrade.agents"]
ai_hedge_fund = "nexustrade.agents.adapters.ai_hedge_fund:AIHedgeFundAgentGroup"
trading_agents_debate = "nexustrade.agents.adapters.trading_agents:TradingAgentsDebateAdapter"
finrl = "nexustrade.agents.adapters.finrl_agent:FinRLAgentAdapter"
fingpt = "nexustrade.agents.adapters.fingpt_sentiment:FinGPTSentimentAdapter"
finbert = "nexustrade.agents.adapters.finbert_agent:FinBERTAdapter"
quantagent = "nexustrade.agents.adapters.quantagent_vision:QuantAgentVisionAdapter"
qlib_alpha = "nexustrade.agents.adapters.qlib_alpha:QlibAlphaAdapter"

[project.entry-points."nexustrade.notifications"]
telegram = "nexustrade.notifications.telegram:TelegramNotifier"
discord = "nexustrade.notifications.discord:DiscordNotifier"
email = "nexustrade.notifications.email:EmailNotifier"
webhook = "nexustrade.notifications.webhook:WebhookNotifier"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## 5. Docker container map

| Container | Base image | Key dependencies | GPU | Ports | Purpose |
|-----------|-----------|-----------------|-----|-------|---------|
| `nexus-data` | `python:3.12-slim` | openbb, ccxt, yfinance, httpx | No | 8081 (API) | Data ingestion + MCP server |
| `nexus-agents` | `python:3.12-slim` | langgraph, langchain, litellm, chromadb | No | 8082 (API) | Multi-agent analysis engine |
| `nexus-finrl` | `pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime` | stable-baselines3, gymnasium, torch | Yes | 50051 (gRPC) | DRL agent inference |
| `nexus-fingpt` | `pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime` | transformers, peft, bitsandbytes, torch | Yes | 50052 (gRPC) | Sentiment analysis |
| `nexus-qlib` | `python:3.12-slim` | qlib, lightgbm, cython | No | 50053 (gRPC) | Factor mining |
| `nexus-llm` | `python:3.12-slim` | litellm | No | 8083 (API) | LLM routing proxy |
| `nexus-execution` | `python:3.12-slim` | alpaca-py, ccxt, httpx, fastapi | No | 8084 (API), 8888 (webhook) | Order management + webhook |
| `nexus-web` | `python:3.12-slim` | fastapi, streamlit | No | 8085 (API), 8501 (Streamlit) | Dashboard + REST API |
| `nexus-redis` | `redis:7-alpine` | — | No | 6379 | Event bus + cache |

---

## 6. External services required

| Service | Required | Purpose | Setup instructions |
|---------|----------|---------|-------------------|
| **Ollama** | For local LLM mode | Local LLM inference | `curl -fsSL https://ollama.com/install.sh \| sh && ollama pull llama3:8b` |
| **OpenAlgo** | For Indian broker execution | Unified Indian broker API | `git clone https://github.com/marketcalls/openalgo && cd openalgo && uv run app.py` |
| **TradingView MCP servers** | For technicals + screening + charts | Market data enrichment | See each project's README for setup |
| **Broker accounts** | For live trading | API credentials | Alpaca, Zerodha, Dhan, Binance, etc. — each requires account creation |

---

## 7. Version compatibility matrix

| NexusTrade | Python | PyTorch | CUDA | Redis | Docker |
|-----------|--------|---------|------|-------|--------|
| 0.1.x | 3.12+ | 2.2+ | 12.1+ | 7.x | 24.0+ |

**Minimum hardware for development:**
- CPU: 4 cores
- RAM: 16 GB (8 GB without ML services)
- GPU: Optional (NVIDIA 8GB+ VRAM for FinRL/FinGPT)
- Disk: 20 GB (models + data cache)

**Minimum hardware for production:**
- CPU: 8 cores
- RAM: 32 GB
- GPU: NVIDIA RTX 3090 or better (24 GB VRAM for concurrent FinRL + FinGPT)
- Disk: 100 GB SSD
