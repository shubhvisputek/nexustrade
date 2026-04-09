"""Tests for strategy parser and engine."""

import pytest
from datetime import datetime, timezone

from nexustrade.core.models import (
    AgentSignal, MarketContext, Position, PortfolioState,
    SignalDirection, TechnicalIndicators,
)
from nexustrade.strategy.parser import parse_strategy_from_dict, StrategyDefinition
from nexustrade.strategy.engine import YAMLStrategy, StrategyEngine
from nexustrade.strategy.conditions import evaluate_condition


UTC_NOW = datetime.now(timezone.utc)


def make_context(
    symbol: str = "AAPL",
    rsi: float | None = None,
    sma_50: float | None = None,
    current_price: float = 185.0,
) -> MarketContext:
    technicals = {}
    if rsi is not None or sma_50 is not None:
        technicals["1d"] = TechnicalIndicators(
            symbol=symbol, timeframe="1d", timestamp=UTC_NOW,
            rsi=rsi, sma_50=sma_50,
        )
    return MarketContext(
        symbol=symbol, current_price=current_price,
        ohlcv={}, technicals=technicals, news=[],
        fundamentals={}, sentiment_scores=[], factor_signals={},
        recent_signals=[], memory=[],
        portfolio=PortfolioState(
            cash=100000, positions=[], total_value=100000,
            daily_pnl=0, total_pnl=0, open_orders=[],
        ),
        config={},
    )


def make_signal(agent_name: str, direction: str, confidence: float = 0.8) -> AgentSignal:
    return AgentSignal(
        direction=direction, confidence=confidence,
        reasoning="test", agent_name=agent_name, agent_type="test",
    )


class TestConditions:
    def test_indicator_rsi_below(self):
        ctx = make_context(rsi=25.0)
        cond = {"type": "indicator", "name": "rsi", "timeframe": "1d", "op": "<", "value": 30}
        assert evaluate_condition(cond, ctx, []) is True

    def test_indicator_rsi_above(self):
        ctx = make_context(rsi=75.0)
        cond = {"type": "indicator", "name": "rsi", "timeframe": "1d", "op": "<", "value": 30}
        assert evaluate_condition(cond, ctx, []) is False

    def test_agent_direction_match(self):
        signals = [make_signal("warren_buffett", "buy")]
        cond = {"type": "agent", "name": "warren_buffett", "direction": "buy"}
        assert evaluate_condition(cond, make_context(), signals) is True

    def test_agent_direction_mismatch(self):
        signals = [make_signal("warren_buffett", "sell")]
        cond = {"type": "agent", "name": "warren_buffett", "direction": "buy"}
        assert evaluate_condition(cond, make_context(), signals) is False

    def test_price_above_sma(self):
        ctx = make_context(sma_50=180.0, current_price=185.0)
        cond = {"type": "price", "op": ">", "field": "sma_50", "timeframe": "1d"}
        assert evaluate_condition(cond, ctx, []) is True

    def test_signal_count(self):
        signals = [
            make_signal("a", "buy"),
            make_signal("b", "buy"),
            make_signal("c", "sell"),
        ]
        cond = {"type": "signal_count", "direction": "buy", "min_count": 2}
        assert evaluate_condition(cond, make_context(), signals) is True

    def test_composite_and(self):
        ctx = make_context(rsi=25.0, sma_50=180.0, current_price=185.0)
        cond = {
            "type": "composite",
            "logic": "and",
            "conditions": [
                {"type": "indicator", "name": "rsi", "timeframe": "1d", "op": "<", "value": 30},
                {"type": "price", "op": ">", "field": "sma_50", "timeframe": "1d"},
            ],
        }
        assert evaluate_condition(cond, ctx, []) is True

    def test_composite_and_one_false(self):
        ctx = make_context(rsi=50.0, sma_50=180.0, current_price=185.0)
        cond = {
            "type": "composite",
            "logic": "and",
            "conditions": [
                {"type": "indicator", "name": "rsi", "timeframe": "1d", "op": "<", "value": 30},
                {"type": "price", "op": ">", "field": "sma_50", "timeframe": "1d"},
            ],
        }
        assert evaluate_condition(cond, ctx, []) is False


class TestStrategyParser:
    def test_parse_valid(self):
        data = {
            "name": "test_strategy",
            "rules": [{
                "name": "rsi_oversold",
                "entry_conditions": [
                    {"type": "indicator", "name": "rsi", "op": "<", "value": 30},
                ],
                "exit_conditions": [
                    {"type": "indicator", "name": "rsi", "op": ">", "value": 70},
                ],
            }],
        }
        definition = parse_strategy_from_dict(data)
        assert definition.name == "test_strategy"
        assert len(definition.rules) == 1

    def test_parse_missing_name_raises(self):
        with pytest.raises(Exception):
            parse_strategy_from_dict({"rules": [{"name": "r", "entry_conditions": [], "exit_conditions": []}]})


class TestYAMLStrategy:
    def test_entry_triggered(self):
        definition = parse_strategy_from_dict({
            "name": "test",
            "rules": [{
                "name": "buy_rule",
                "entry_conditions": [
                    {"type": "indicator", "name": "rsi", "timeframe": "1d", "op": "<", "value": 30},
                ],
                "exit_conditions": [],
            }],
        })
        strategy = YAMLStrategy(definition)
        ctx = make_context(rsi=25.0)
        assert strategy.evaluate_entry(ctx, []) is True

    def test_entry_not_triggered(self):
        definition = parse_strategy_from_dict({
            "name": "test",
            "rules": [{
                "name": "buy_rule",
                "entry_conditions": [
                    {"type": "indicator", "name": "rsi", "timeframe": "1d", "op": "<", "value": 30},
                ],
                "exit_conditions": [],
            }],
        })
        strategy = YAMLStrategy(definition)
        ctx = make_context(rsi=50.0)
        assert strategy.evaluate_entry(ctx, []) is False

    def test_exit_triggered(self):
        definition = parse_strategy_from_dict({
            "name": "test",
            "rules": [{
                "name": "sell_rule",
                "entry_conditions": [],
                "exit_conditions": [
                    {"type": "indicator", "name": "rsi", "timeframe": "1d", "op": ">", "value": 70},
                ],
            }],
        })
        strategy = YAMLStrategy(definition)
        ctx = make_context(rsi=75.0)
        pos = Position(
            symbol="AAPL", quantity=100, avg_entry_price=180.0,
            current_price=185.0, unrealized_pnl=500.0,
        )
        assert strategy.evaluate_exit(ctx, [], pos) is True
