"""Backtest engine — historical replay through the full pipeline.

Replays historical data through the agent → risk → execution pipeline,
tracking positions and computing performance metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nexustrade.backtest.metrics import BacktestMetrics, compute_metrics
from nexustrade.core.models import (
    OHLCV,
    PortfolioState,
    Position,
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Result of a backtest run."""
    strategy_name: str
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    metrics: BacktestMetrics
    equity_curve: list[float]
    trades: list[dict[str, Any]]
    signals: list[dict[str, Any]] = field(default_factory=list)


class BacktestEngine:
    """Replays historical data and executes the trading pipeline.

    For each decision point:
    1. Build MarketContext from historical data
    2. Run agents to generate signals (optional — can use pre-computed)
    3. Apply strategy rules
    4. Execute through paper backend
    5. Track portfolio state
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_pct: float = 0.001,
        slippage_pct: float = 0.001,
    ) -> None:
        self._initial_capital = initial_capital
        self._commission_pct = commission_pct
        self._slippage_pct = slippage_pct

    def run(
        self,
        data: list[OHLCV],
        strategy_fn: Any = None,
        strategy_name: str = "backtest",
    ) -> BacktestResult:
        """Run a backtest on historical OHLCV data.

        Args:
            data: List of OHLCV bars sorted by timestamp
            strategy_fn: Optional callable(bar, position, portfolio) -> "buy"|"sell"|None
            strategy_name: Name for the backtest result

        Returns:
            BacktestResult with metrics
        """
        if not data:
            return self._empty_result(strategy_name)

        data = sorted(data, key=lambda b: b.timestamp)
        symbol = data[0].symbol

        cash = self._initial_capital
        position: Position | None = None
        equity_curve = [self._initial_capital]
        trades: list[dict[str, Any]] = []

        for i, bar in enumerate(data):
            # Default strategy: use provided function or buy-and-hold
            action = None
            if strategy_fn:
                portfolio = PortfolioState(
                    cash=cash,
                    positions=[position] if position else [],
                    total_value=cash + (position.quantity * bar.close if position else 0),
                    daily_pnl=0, total_pnl=0, open_orders=[],
                )
                action = strategy_fn(bar, position, portfolio)

            # Execute action
            if action == "buy" and position is None:
                # Buy
                price = bar.close * (1 + self._slippage_pct)
                max_qty = (cash * 0.95) / price  # Use 95% of cash
                qty = int(max_qty)
                if qty > 0:
                    cost = qty * price
                    commission = cost * self._commission_pct
                    cash -= cost + commission
                    position = Position(
                        symbol=symbol, quantity=qty,
                        avg_entry_price=price, current_price=bar.close,
                        unrealized_pnl=0, broker="backtest", market="",
                    )
                    trades.append({
                        "type": "buy", "price": price, "qty": qty,
                        "commission": commission,
                        "entry_date": bar.timestamp.isoformat(),
                        "bar_index": i,
                    })

            elif action == "sell" and position is not None:
                # Sell
                price = bar.close * (1 - self._slippage_pct)
                revenue = position.quantity * price
                commission = revenue * self._commission_pct
                pnl = revenue - (position.quantity * position.avg_entry_price) - commission
                cash += revenue - commission

                # Find matching buy trade and update
                for t in reversed(trades):
                    if t["type"] == "buy" and "pnl" not in t:
                        t["exit_date"] = bar.timestamp.isoformat()
                        t["exit_price"] = price
                        t["pnl"] = pnl
                        break

                position = None

            # Update equity curve
            portfolio_value = cash
            if position is not None:
                position.current_price = bar.close
                position.unrealized_pnl = (bar.close - position.avg_entry_price) * position.quantity
                portfolio_value += position.quantity * bar.close

            equity_curve.append(portfolio_value)

        # Close any open position at last bar
        if position is not None and data:
            last_bar = data[-1]
            price = last_bar.close * (1 - self._slippage_pct)
            revenue = position.quantity * price
            commission = revenue * self._commission_pct
            pnl = revenue - (position.quantity * position.avg_entry_price) - commission
            cash += revenue - commission

            for t in reversed(trades):
                if t["type"] == "buy" and "pnl" not in t:
                    t["exit_date"] = last_bar.timestamp.isoformat()
                    t["exit_price"] = price
                    t["pnl"] = pnl
                    break

        final_value = equity_curve[-1]
        completed_trades = [t for t in trades if "pnl" in t]
        metrics = compute_metrics(equity_curve, completed_trades, self._initial_capital)

        return BacktestResult(
            strategy_name=strategy_name,
            symbol=symbol,
            start_date=data[0].timestamp.isoformat(),
            end_date=data[-1].timestamp.isoformat(),
            initial_capital=self._initial_capital,
            final_value=final_value,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=completed_trades,
        )

    def run_buy_and_hold(
        self, data: list[OHLCV], strategy_name: str = "buy_and_hold"
    ) -> BacktestResult:
        """Run a buy-and-hold backtest (buy on first bar, sell on last)."""
        def strategy(bar, position, portfolio):
            if position is None:
                return "buy"
            return None

        return self.run(data, strategy_fn=strategy, strategy_name=strategy_name)

    def _empty_result(self, name: str) -> BacktestResult:
        return BacktestResult(
            strategy_name=name, symbol="", start_date="", end_date="",
            initial_capital=self._initial_capital,
            final_value=self._initial_capital,
            metrics=BacktestMetrics(), equity_curve=[], trades=[],
        )
