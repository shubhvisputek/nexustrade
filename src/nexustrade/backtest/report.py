"""Backtest report generation.

Formats backtest results into human-readable reports.
"""

from __future__ import annotations

from nexustrade.backtest.engine import BacktestResult


def format_report(result: BacktestResult) -> str:
    """Format a backtest result into a text report."""
    m = result.metrics
    lines = [
        f"{'=' * 60}",
        f"Backtest Report: {result.strategy_name}",
        f"{'=' * 60}",
        f"Symbol:           {result.symbol}",
        f"Period:           {result.start_date[:10]} to {result.end_date[:10]}",
        f"Initial Capital:  ${result.initial_capital:,.2f}",
        f"Final Value:      ${result.final_value:,.2f}",
        "",
        "--- Performance ---",
        f"Total Return:     {m.total_return:.2%}",
        f"Annual Return:    {m.annualized_return:.2%}",
        f"Sharpe Ratio:     {m.sharpe_ratio:.2f}",
        f"Max Drawdown:     {m.max_drawdown:.2%}",
        f"Calmar Ratio:     {m.calmar_ratio:.2f}",
        f"Volatility:       {m.volatility:.2%}",
        "",
        "--- Trading ---",
        f"Total Trades:     {m.total_trades}",
        f"Win Rate:         {m.win_rate:.2%}",
        f"Profit Factor:    {m.profit_factor:.2f}",
        f"Avg Win:          ${m.avg_win:,.2f}",
        f"Avg Loss:         ${m.avg_loss:,.2f}",
        f"Best Trade:       ${m.best_trade:,.2f}",
        f"Worst Trade:      ${m.worst_trade:,.2f}",
        f"Avg Holding:      {m.avg_holding_period_days:.1f} days",
        f"{'=' * 60}",
    ]
    return "\n".join(lines)
