# AGENTS.md — Task orchestration for autonomous execution

> This file defines how to manage multi-session development.
> Each session: read this file → check progress → pick next task → execute → verify → commit.

---

## Progress tracking

Check which phase is complete by running:

```bash
# Quick status check
python -c "
import subprocess, json, pathlib

phases = {
    'Phase 0': 'src/nexustrade/__init__.py',
    'Phase 1': 'src/nexustrade/core/events.py',
    'Phase 2': 'src/nexustrade/data/router.py', 
    'Phase 3': 'src/nexustrade/agents/aggregator.py',
    'Phase 4': 'src/nexustrade/risk/engine.py',
    'Phase 5': 'src/nexustrade/execution/engine.py',
    'Phase 6': 'src/nexustrade/backtest/engine.py',
    'Phase 7': 'src/nexustrade/notifications/telegram.py',
    'Phase 8': 'services/finrl/server.py',
    'Phase 9': 'src/nexustrade/web/dashboard.py',
    'Phase 10': 'tests/integration/test_full_pipeline.py',
}

for phase, marker in phases.items():
    exists = pathlib.Path(marker).exists()
    has_content = exists and pathlib.Path(marker).stat().st_size > 100
    status = '✅ Done' if has_content else ('📝 Started' if exists else '⬜ Not started')
    print(f'{status}  {phase}')
"

# Run tests to verify completeness
pytest tests/ -v --tb=line 2>&1 | tail -20
```

---

## Session startup checklist

Every time you start a new session:

1. **Read CLAUDE.md** (your operating manual)
2. **Check progress** (run the script above)
3. **Check git status** (`git status`, `git log --oneline -5`)
4. **Verify services running:**
   ```bash
   # Redis
   redis-cli ping || docker start nexus-redis || docker run -d --name nexus-redis -p 6379:6379 redis:7-alpine
   
   # Ollama
   curl -s http://localhost:11434/api/tags > /dev/null || ollama serve &
   ```
5. **Pick next incomplete phase** from `05_INTEGRATION_GUIDE.md`
6. **Execute steps in order** within that phase
7. **Run tests after each step**
8. **Commit after each successful step**
9. **Push at end of session**

---

## Service health checks

Before running integration tests, verify all services:

```bash
echo "=== Service Health ==="

# Redis
redis-cli ping 2>/dev/null && echo "✅ Redis" || echo "❌ Redis — run: docker start nexus-redis"

# Ollama  
curl -s http://localhost:11434/api/tags > /dev/null 2>&1 && echo "✅ Ollama" || echo "❌ Ollama — run: ollama serve"

# Ollama models
ollama list 2>/dev/null | grep -q "llama3:8b" && echo "✅ llama3:8b model" || echo "❌ Model — run: ollama pull llama3:8b"

# OpenAlgo (optional)
curl -s http://localhost:5000/ > /dev/null 2>&1 && echo "✅ OpenAlgo" || echo "⚠️ OpenAlgo not running (optional for non-India features)"

# Check .env
[ -f .env ] && echo "✅ .env exists" || echo "❌ .env missing — create from CLAUDE.md template"
```

---

## Task priority when time is limited

If you can only do ONE thing per session, prioritize in this order:

1. **Fix failing tests** from previous session (never leave broken tests)
2. **Complete current phase** (don't start a new phase mid-session)
3. **Write tests for untested code** (coverage gaps are technical debt)
4. **Move to next phase** (only after current phase is fully green)

---

## Common recovery scenarios

### "Tests were passing, now they fail after changes"
```bash
git stash                    # Save current changes
pytest tests/ -v             # Verify tests pass on clean state  
git stash pop                # Restore changes
# Now isolate which change broke things
```

### "External service went down mid-test"
```bash
# Restart services
docker restart nexus-redis
ollama serve &
# Re-run only failed tests
pytest tests/ --lf -v        # --lf = last failed only
```

### "Context lost between sessions"
Read these files in order:
1. `CLAUDE.md` — overall instructions
2. `git log --oneline -20` — what was done recently
3. `pytest tests/ -v --tb=line` — what's currently working/broken
4. `05_INTEGRATION_GUIDE.md` — find the next incomplete step

---

## Credential placeholders

Until the user provides real credentials, use these patterns:

```python
# In tests - skip if no real credentials
import os
import pytest

ALPACA_KEY = os.getenv("ALPACA_API_KEY", "")
HAS_ALPACA = ALPACA_KEY and not ALPACA_KEY.startswith("placeholder")

@pytest.mark.integration
@pytest.mark.skipif(not HAS_ALPACA, reason="No Alpaca API key configured")
def test_alpaca_paper_order():
    ...
```

This way ALL unit tests pass immediately, and integration tests gracefully skip until credentials appear.
