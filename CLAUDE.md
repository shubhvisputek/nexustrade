# CLAUDE.md — NexusTrade Autonomous Development Instructions

> **Read this file first. It is your operating manual.**
> You are building NexusTrade — a unified open-source LLM trading platform.
> All design decisions are already made. Your job is to EXECUTE.

---

## Your reference documents (read ALL before starting)

These 5 documents in `docs/` contain everything you need:

| Document | What it tells you | When to reference |
|----------|------------------|-------------------|
| `01_PRD.md` | Every feature spec, acceptance criteria, test specs | When implementing any feature |
| `02_FEATURE_SOURCING.md` | Which OSS project to study for each feature, exact file paths | When deciding HOW to implement |
| `03_TECH_STACK.md` | Every package, version, Docker container, pyproject.toml | When setting up dependencies |
| `04_ARCHITECTURE.md` | All interfaces (ABCs), data models, config schemas, directory structure | When writing any code |
| `05_INTEGRATION_GUIDE.md` | Step-by-step build order with verification criteria | Your execution checklist |

---

## Execution rules

1. **Follow `05_INTEGRATION_GUIDE.md` phase by phase, step by step.** Do not skip ahead.
2. **After each step, run the specified verification tests.** Do not proceed if tests fail. Fix first.
3. **Commit to git after each successful step.** Use conventional commits: `feat:`, `fix:`, `test:`, `chore:`.
4. **Push to GitHub after each phase completes.**
5. **When implementing a feature, check `02_FEATURE_SOURCING.md` first.** If it says REFERENCE — study the source project's approach (don't copy code). If ADAPT — extend the pattern. If BUILD — design from scratch using the PRD spec.
6. **All interfaces, models, and config schemas are defined in `04_ARCHITECTURE.md`.** Use them exactly as specified.
7. **Write tests alongside implementation.** Every feature in the PRD has test specs. Implement them.
8. **Use the tech stack versions from `03_TECH_STACK.md`.** Do not deviate.

---

## Environment setup (do this FIRST before any coding)

### Step 0: System prerequisites

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # or ~/.zshrc

# Install Docker (if not present)
# On Ubuntu:
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Ollama (for local LLM)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3:8b
ollama pull nomic-embed-text  # For ChromaDB embeddings

# Install Node.js 20 LTS (for TradingView MCP servers if needed)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### Step 1: Start persistent services

```bash
# Start Redis (runs in background)
docker run -d --name nexus-redis -p 6379:6379 redis:7-alpine

# Verify Redis
redis-cli ping  # Should return PONG

# Start Ollama (if not already running as service)
ollama serve &  # Runs in background

# Verify Ollama
curl http://localhost:11434/api/tags  # Should list models
```

### Step 2: Clone and setup OpenAlgo (for Indian broker support)

```bash
# Clone OpenAlgo
cd ~
git clone https://github.com/marketcalls/openalgo.git
cd openalgo

# Create OpenAlgo config (paper/sandbox mode initially)
cp .sample.env .env
# Edit .env — for now, leave broker credentials empty
# OpenAlgo will start but won't connect to any broker until credentials are provided

# Install and run OpenAlgo
pip install uv
uv run app.py &  # Runs on port 5000

# Verify OpenAlgo
curl http://localhost:5000/  # Should return OpenAlgo page
```

### Step 3: Create project .env file

```bash
# Create .env in the nexustrade project root
cat > .env << 'EOF'
# LLM API Keys (user will provide these)
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-sk-ant-placeholder}
OPENAI_API_KEY=${OPENAI_API_KEY:-sk-placeholder}

# Broker API Keys (paper trading — user provides before Phase 5)
ALPACA_API_KEY=${ALPACA_API_KEY:-placeholder}
ALPACA_SECRET=${ALPACA_SECRET:-placeholder}

# OpenAlgo (local instance)
OPENALGO_API_KEY=${OPENALGO_API_KEY:-placeholder}
OPENALGO_HOST=http://localhost:5000

# Ollama (local)
OLLAMA_BASE_URL=http://localhost:11434

# Redis (local Docker)
REDIS_URL=redis://localhost:6379

# TradingView webhook
TV_PASSPHRASE=${TV_PASSPHRASE:-nexustrade_dev_secret}

# Notifications (optional — add when ready)
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL:-}
EOF
```

**Note:** Placeholder values allow the system to start and run unit tests without real credentials. Integration tests that need real APIs will be skipped until credentials are provided. Use `pytest -m "not integration"` to run only unit tests.

---

## Task sequencing strategy

### How to chain tasks efficiently

Execute phases sequentially. Within each phase, steps can sometimes be parallelized:

**Phase 0 (scaffold):** All steps sequential — each builds on the previous.

**Phase 1 (core):** Steps 1.1 → 1.2 → 1.3 can be sequential. Steps 1.4 (event bus) and 1.5 (registry) are independent — can be done in any order after 1.2.

**Phase 2 (data):** Step 2.1 (router) first. Then adapters (2.2-2.6) are independent of each other — implement in order of importance: OpenBB → CCXT → Yahoo → TV MCP → Broker data. Step 2.7 (caching) after at least one adapter works.

**Phase 3 (agents):** Step 3.1 (prompts) and 3.2 (LLM router) first. Then agent adapters (3.3-3.5) are independent. Step 3.6 (aggregator) needs at least one agent. Step 3.7 (executor) needs aggregator. Step 3.8 (memory) is independent.

**Phase 4-5 (risk + execution):** Sequential within each phase.

**Phase 6-9:** Mostly independent — can be done in any order.

### After each phase, do this:

```bash
# Run all tests
pytest tests/ -v --tb=short

# Check coverage
pytest tests/ --cov=nexustrade --cov-report=term-missing

# Lint and type check
ruff check src/
mypy src/nexustrade/

# Commit and push
git add -A
git commit -m "feat: complete Phase N — [description]"
git push origin main
```

---

## Testing strategy

### Test markers

```python
# In conftest.py, define markers:
# @pytest.mark.unit — runs without any external service
# @pytest.mark.integration — needs Redis, maybe Ollama, maybe broker APIs  
# @pytest.mark.e2e — needs full stack running
# @pytest.mark.slow — takes > 30 seconds (LLM calls)
```

### Running tests at different stages

```bash
# During development (fast, no external deps):
pytest -m unit -v

# After Redis is up:
pytest -m "unit or integration" -v

# Full test suite (all services running):
pytest -v

# Skip slow LLM tests during rapid iteration:
pytest -m "not slow" -v
```

### Mock strategy

- **Unit tests:** Mock ALL external calls (LLM, brokers, data providers, Redis).
- **Integration tests:** Use real Redis, real Ollama (llama3:8b), mock brokers.
- **E2E tests:** Use real everything with paper trading backends.

---

## Credential management

The user will provide credentials by updating the `.env` file. When credentials are placeholders:

- **Unit tests:** Always pass (everything is mocked).
- **Integration tests with data:** Skip with `@pytest.mark.skipif(not API_KEY, reason="No API key")`.
- **Integration tests with brokers:** Skip until real keys provided.
- **Paper trading:** Works with Alpaca paper keys (free signup).

When the user says "here are my credentials," update `.env` and re-run integration tests.

---

## Git workflow

```
main branch — always stable, all tests pass
  └── feat/phase-0-scaffold
  └── feat/phase-1-core
  └── feat/phase-2-data
  └── feat/phase-3-agents
  └── ... (one branch per phase, merge to main when phase tests pass)
```

---

## Key architectural decisions (do not deviate)

1. **Everything is an adapter.** Data, brokers, agents, notifications, risk models — all behind ABCs.
2. **Config drives behavior.** YAML → env vars → CLI flags. Pydantic validates.
3. **Redis Streams is the event bus.** All inter-service communication goes through Redis.
4. **Entry_points for plugin discovery.** All adapters registered in pyproject.toml.
5. **Docker for dependency isolation.** FinRL, FinGPT, Qlib in separate containers.
6. **LiteLLM for LLM routing.** One API for all providers. 3 channels: fast/deep/vision.
7. **OpenAlgo for Indian brokers.** NexusTrade is a CLIENT of OpenAlgo, not a replacement.
8. **CCXT for crypto.** Unified API for 100+ exchanges.
9. **asyncio throughout.** All I/O-bound operations are async.
10. **Canonical data models.** Every adapter converts to/from the models in `core/models.py`.

---

## When you get stuck

1. Re-read the relevant section of `01_PRD.md` for the exact spec.
2. Check `02_FEATURE_SOURCING.md` for which OSS project to study.
3. Check `04_ARCHITECTURE.md` for the interface definition.
4. If a test fails, fix the implementation, don't weaken the test.
5. If a dependency conflict arises, that component goes in a Docker container.
6. If an external service is unavailable, write the adapter anyway with mocks, and mark integration tests as skippable.

---

## Success criteria

The project is DONE when:

1. `pytest tests/` passes with >85% coverage.
2. `nexus paper --config examples/us_equities_basic.yaml` runs a full paper trading cycle.
3. `nexus backtest --strategy examples/basic_strategy.yaml --from 2024-01-01 --to 2024-12-31` produces a report.
4. `docker compose up` starts all 9 services with health checks passing.
5. Changing `execution.mode` from `python` to `tradingview` to `both` in YAML works without code changes.
6. Changing `llm.mode` from `local` to `cloud` to `hybrid` in YAML works without code changes.
7. Changing `execution.india.broker` from `zerodha` to `dhan` in YAML works without code changes.
8. All 55 features from the PRD have passing tests.
