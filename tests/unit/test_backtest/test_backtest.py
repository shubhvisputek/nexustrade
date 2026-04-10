"""Tests for backtest engine and metrics."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from nexustrade.backtest.engine import BacktestEngine
from nexustrade.backtest.metrics import compute_metrics, BacktestMetrics
from nexustrade.backtest.report import format_report
from nexustrade.core.models import OHLCV


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"


def load_aapl_data() -> list[OHLCV]:
    data = json.loads((FIXTURES_DIR / "ohlcv_aapl.json").read_text())
    return [OHLCV.from_dict(d) for d in data]


class TestBacktestMetrics:
    def test_compute_from_equity_curve(self):
        # Simple upward curve
        equity = [100000, 101000, 102000, 101500, 103000, 104000]
        trades = [{"pnl": 1000}, {"pnl": -500}, {"pnl": 1500}]
        metrics = compute_metrics(equity, trades, initial_capital=100000)

        assert metrics.total_return == pytest.approx(0.04, abs=0.001)
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.win_rate == pytest.approx(2 / 3, abs=0.01)
        assert metrics.profit_factor > 0

    def test_sharpe_ratio_positive(self):
        # Steadily increasing equity
        equity = [100000 + i * 100 for i in range(252)]
        metrics = compute_metrics(equity, [], initial_capital=100000)
        assert metrics.sharpe_ratio > 0

    def test_max_drawdown(self):
        equity = [100000, 105000, 95000, 98000, 102000]
        metrics = compute_metrics(equity, [], initial_capital=100000)
        # Max drawdown: (105000 - 95000) / 105000 ≈ 9.5%
        assert metrics.max_drawdown == pytest.approx(0.0952, abs=0.01)

    def test_empty_curve(self):
        metrics = compute_metrics([], [])
        assert metrics.total_return == 0.0
        assert metrics.total_trades == 0

    def test_profit_factor(self):
        trades = [
            {"pnl": 1000}, {"pnl": 2000}, {"pnl": -500},
        ]
        metrics = compute_metrics([100000, 103000, 102500], trades, initial_capital=100000)
        assert metrics.profit_factor == pytest.approx(6.0, abs=0.1)


class TestBacktestEngine:
    def test_buy_and_hold(self):
        data = load_aapl_data()
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run_buy_and_hold(data)

        assert result.strategy_name == "buy_and_hold"
        assert result.symbol == "AAPL"
        assert result.initial_capital == 100000
        assert result.final_value > 0
        assert len(result.equity_curve) > 0
        assert result.metrics.total_trades >= 1

    def test_custom_strategy(self):
        data = load_aapl_data()
        call_count = 0

        def simple_strategy(bar, position, portfolio):
            nonlocal call_count
            call_count += 1
            if position is None and call_count == 5:
                return "buy"
            if position is not None and call_count == 20:
                return "sell"
            return None

        engine = BacktestEngine(initial_capital=100000)
        result = engine.run(data, strategy_fn=simple_strategy, strategy_name="test")

        assert result.strategy_name == "test"
        assert len(result.trades) >= 1

    def test_slippage_applied(self):
        data = load_aapl_data()[:5]

        engine_no_slip = BacktestEngine(slippage_pct=0.0, commission_pct=0.0)
        engine_with_slip = BacktestEngine(slippage_pct=0.01, commission_pct=0.0)

        def always_buy(bar, pos, port):
            return "buy" if pos is None else None

        r1 = engine_no_slip.run(data, strategy_fn=always_buy)
        r2 = engine_with_slip.run(data, strategy_fn=always_buy)

        # With slippage, should buy at higher price → lower final value
        assert r1.final_value >= r2.final_value

    def test_empty_data(self):
        engine = BacktestEngine()
        result = engine.run([])
        assert result.final_value == 100000
        assert result.metrics.total_trades == 0


class TestBacktestReport:
    def test_report_generation(self):
        data = load_aapl_data()
        engine = BacktestEngine()
        result = engine.run_buy_and_hold(data)
        report = format_report(result)

        assert "Backtest Report" in report
        assert "AAPL" in report
        assert "Total Return" in report
        assert "Sharpe Ratio" in report
