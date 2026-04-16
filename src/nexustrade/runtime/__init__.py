"""NexusTrade runtime — the orchestrator that wires components together.

This package contains:

- :mod:`state` — process-singleton state holder. The FastAPI endpoints,
  Streamlit dashboard, and orchestrator all read/write the same instance.
- :mod:`paper_loop` — the actual paper-trading orchestrator. Wires data
  providers, agents, signal aggregation, risk, and a broker into one
  asynchronous tick loop.
- :mod:`audit` — structured audit-log buffer that fans events into
  notifications and dashboard widgets.
- :mod:`alerts` — alert dispatch (Telegram/Discord/Email/Webhook).
"""

from __future__ import annotations

from nexustrade.runtime.state import RuntimeState, get_runtime_state

__all__ = ["RuntimeState", "get_runtime_state"]
