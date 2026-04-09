"""Backtest performance metrics.

Computes Sharpe ratio, max drawdown, win rate, profit factor,
and other standard trading metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BacktestMetrics:
    """Comprehensive backtest performance metrics."""
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration_days: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_holding_period_days: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    volatility: float = 0.0
    calmar_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


def compute_metrics(
    equity_curve: list[float],
    trades: list[dict[str, Any]],
    initial_capital: float = 100000.0,
    trading_days_per_year: int = 252,
    risk_free_rate: float = 0.04,
) -> BacktestMetrics:
    """Compute comprehensive metrics from equity curve and trade list.

    Args:
        equity_curve: Daily portfolio values
        trades: List of trade dicts with 'pnl', 'entry_date', 'exit_date'
        initial_capital: Starting capital
        trading_days_per_year: Trading days in a year
        risk_free_rate: Annual risk-free rate for Sharpe

    Returns:
        BacktestMetrics
    """
    metrics = BacktestMetrics()

    if not equity_curve or len(equity_curve) < 2:
        return metrics

    # Total return
    metrics.total_return = (equity_curve[-1] - initial_capital) / initial_capital

    # Annualized return
    n_days = len(equity_curve)
    n_years = n_days / trading_days_per_year
    if n_years > 0 and equity_curve[-1] > 0:
        metrics.annualized_return = (equity_curve[-1] / initial_capital) ** (1 / n_years) - 1

    # Daily returns
    daily_returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] > 0
    ]

    # Volatility
    if daily_returns:
        mean_return = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns)
        daily_vol = math.sqrt(variance)
        metrics.volatility = daily_vol * math.sqrt(trading_days_per_year)

        # Sharpe ratio
        daily_rf = risk_free_rate / trading_days_per_year
        if daily_vol > 0:
            metrics.sharpe_ratio = (mean_return - daily_rf) / daily_vol * math.sqrt(trading_days_per_year)

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    dd_start = 0
    max_dd_duration = 0
    current_dd_start = 0

    for i, value in enumerate(equity_curve):
        if value > peak:
            peak = value
            duration = i - current_dd_start
            if duration > max_dd_duration:
                max_dd_duration = duration
            current_dd_start = i
        dd = (peak - value) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    metrics.max_drawdown = max_dd
    metrics.max_drawdown_duration_days = max_dd_duration

    # Calmar ratio
    if max_dd > 0:
        metrics.calmar_ratio = metrics.annualized_return / max_dd

    # Trade metrics
    if trades:
        pnls = [t.get("pnl", 0) for t in trades]
        metrics.total_trades = len(trades)

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)

        if metrics.total_trades > 0:
            metrics.win_rate = metrics.winning_trades / metrics.total_trades

        if wins:
            metrics.avg_win = sum(wins) / len(wins)
            metrics.best_trade = max(wins)

        if losses:
            metrics.avg_loss = sum(losses) / len(losses)
            metrics.worst_trade = min(losses)

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        if gross_loss > 0:
            metrics.profit_factor = gross_profit / gross_loss

        # Average holding period
        holding_days = []
        for t in trades:
            if "entry_date" in t and "exit_date" in t:
                try:
                    from datetime import datetime
                    entry = datetime.fromisoformat(str(t["entry_date"]))
                    exit_ = datetime.fromisoformat(str(t["exit_date"]))
                    holding_days.append((exit_ - entry).days)
                except Exception:
                    pass
        if holding_days:
            metrics.avg_holding_period_days = sum(holding_days) / len(holding_days)

    return metrics
