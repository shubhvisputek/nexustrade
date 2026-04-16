"""Backtest runner that wires the agent pipeline + YAML strategy
into the existing :class:`BacktestEngine`.

The base ``BacktestEngine.run()`` accepts a ``strategy_fn(bar, position,
portfolio) -> "buy" | "sell" | None`` callable. This module builds such
a callable from either:

- A :class:`YAMLStrategy` (rule-based on indicators / agent signals)
- A list of agent adapters with a :class:`SignalAggregator`

Results are stored in :class:`RuntimeState.backtests` so the dashboard
can render the equity curve, trade ledger, and metrics.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nexustrade.agents.aggregator import SignalAggregator
from nexustrade.backtest.engine import BacktestEngine, BacktestResult
from nexustrade.core.interfaces import AgentInterface, DataProviderInterface
from nexustrade.core.models import (
    OHLCV,
    AgentSignal,
    MarketContext,
    PortfolioState,
    Position,
    SignalDirection,
)
from nexustrade.runtime.state import RuntimeState, get_runtime_state
from nexustrade.strategy.engine import YAMLStrategy
from nexustrade.strategy.parser import parse_strategy

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _result_to_dict(r: BacktestResult) -> dict[str, Any]:
    metrics = r.metrics
    return {
        "strategy_name": r.strategy_name,
        "symbol": r.symbol,
        "start_date": r.start_date,
        "end_date": r.end_date,
        "initial_capital": r.initial_capital,
        "final_value": r.final_value,
        "metrics": {
            "total_return_pct": getattr(metrics, "total_return_pct", 0.0),
            "annualized_return_pct": getattr(metrics, "annualized_return_pct", 0.0),
            "sharpe_ratio": getattr(metrics, "sharpe_ratio", 0.0),
            "sortino_ratio": getattr(metrics, "sortino_ratio", 0.0),
            "max_drawdown_pct": getattr(metrics, "max_drawdown_pct", 0.0),
            "win_rate_pct": getattr(metrics, "win_rate_pct", 0.0),
            "profit_factor": getattr(metrics, "profit_factor", 0.0),
            "num_trades": getattr(metrics, "num_trades", 0),
            "avg_trade_pct": getattr(metrics, "avg_trade_pct", 0.0),
        },
        "equity_curve": list(r.equity_curve),
        "trades": list(r.trades),
        "signals": list(r.signals),
    }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def make_sma_crossover_strategy(short: int = 20, long: int = 50) -> Any:
    """A canonical SMA crossover strategy as the demo default."""

    closes: list[float] = []

    def _strategy(bar, position, portfolio):  # type: ignore[no-untyped-def]
        closes.append(bar.close)
        if len(closes) < long:
            return None
        sma_short = sum(closes[-short:]) / short
        sma_long = sum(closes[-long:]) / long
        if position is None and sma_short > sma_long:
            return "buy"
        if position is not None and sma_short < sma_long:
            return "sell"
        return None

    return _strategy


def make_yaml_strategy_fn(
    strategy: YAMLStrategy,
    agents: list[AgentInterface] | None = None,
    aggregator: SignalAggregator | None = None,
) -> Any:
    """Build a backtest-compatible callable from a YAMLStrategy.

    On each bar, we run the configured agents (if any), evaluate the
    YAML rules against the resulting signals + the bar's price, and
    return ``"buy" | "sell" | None``.
    """

    bars_seen: list[OHLCV] = []

    def _strategy(bar, position, portfolio):  # type: ignore[no-untyped-def]
        bars_seen.append(bar)
        # Build a minimal MarketContext (synchronous; agent calls would be async
        # — rule evaluation only needs the bar, so we skip agents in backtest
        # by default for performance unless explicitly enabled below).
        context = MarketContext(
            symbol=bar.symbol,
            current_price=bar.close,
            ohlcv={bar.timeframe: list(bars_seen)},
            technicals={},
            news=[],
            fundamentals={},
            sentiment_scores=[],
            factor_signals={},
            recent_signals=[],
            memory=[],
            portfolio=portfolio,
            config={},
        )

        # Optionally execute agents synchronously via asyncio.run
        signals: list[AgentSignal] = []
        if agents:
            try:
                signals = asyncio.run(_run_agents(agents, context))
            except RuntimeError:
                # Already in event loop — skip; rule still works without agents.
                signals = []

        if position is None:
            if strategy.evaluate_entry(context, signals):
                return "buy"
        else:
            if strategy.evaluate_exit(context, signals, position):
                return "sell"
        return None

    return _strategy


async def _run_agents(
    agents: list[AgentInterface], context: MarketContext
) -> list[AgentSignal]:
    results = await asyncio.gather(*(a.analyze(context) for a in agents), return_exceptions=True)
    out: list[AgentSignal] = []
    for r in results:
        if isinstance(r, AgentSignal):
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


async def run_backtest(
    *,
    symbol: str,
    timeframe: str = "1d",
    start: datetime,
    end: datetime,
    data_provider: DataProviderInterface,
    initial_capital: float = 100_000.0,
    commission_pct: float = 0.001,
    slippage_pct: float = 0.001,
    strategy_yaml: str | Path | None = None,
    name: str | None = None,
    state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Fetch historical data and run a backtest.

    Parameters
    ----------
    symbol, timeframe, start, end:
        Identify the data slice to fetch.
    data_provider:
        Used to fetch OHLCV bars. Yahoo works without credentials.
    strategy_yaml:
        Optional path to a YAML strategy. When ``None``, a default
        SMA(20/50) crossover strategy is used so the demo always runs.
    name:
        Backtest result name. Defaults to ``f"{strategy_name}-{symbol}"``.
    state:
        Runtime state to write results into. Defaults to the singleton.
    """
    state = state or get_runtime_state()

    bars = await data_provider.get_ohlcv(symbol, timeframe, start, end)
    if not bars:
        result_dict = {
            "strategy_name": name or "backtest",
            "symbol": symbol,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "initial_capital": initial_capital,
            "final_value": initial_capital,
            "metrics": {"num_trades": 0},
            "equity_curve": [initial_capital],
            "trades": [],
            "signals": [],
            "error": "No bars returned by data provider",
        }
        state.store_backtest_result(name or symbol, result_dict)
        return result_dict

    if strategy_yaml is not None:
        definition = parse_strategy(strategy_yaml)
        yaml_strategy = YAMLStrategy(definition)
        strategy_fn = make_yaml_strategy_fn(yaml_strategy)
        strategy_name = definition.name
    else:
        strategy_fn = make_sma_crossover_strategy()
        strategy_name = name or "sma_crossover_20_50"

    engine = BacktestEngine(
        initial_capital=initial_capital,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
    )
    raw = engine.run(bars, strategy_fn=strategy_fn, strategy_name=strategy_name)

    result_dict = _result_to_dict(raw)
    result_dict["timeframe"] = timeframe
    result_dict["data_source"] = data_provider.name

    state.store_backtest_result(name or strategy_name, result_dict)
    state.record_audit(
        "system",
        "info",
        f"Backtest completed: {strategy_name} on {symbol} → "
        f"{result_dict['metrics'].get('total_return_pct', 0.0):.2f}% return, "
        f"{result_dict['metrics'].get('num_trades', 0)} trades",
    )
    return result_dict


def run_backtest_sync(**kwargs: Any) -> dict[str, Any]:
    """Synchronous wrapper for use from CLI / Streamlit."""
    return asyncio.run(run_backtest(**kwargs))
