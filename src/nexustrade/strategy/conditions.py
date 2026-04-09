"""Condition evaluators for strategy rules.

Evaluates conditions referencing agent signals, technical indicators,
and price-based rules.
"""

from __future__ import annotations

import operator
from typing import Any

from nexustrade.core.models import AgentSignal, MarketContext, TechnicalIndicators

OPERATORS = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


def evaluate_condition(
    condition: dict[str, Any],
    context: MarketContext,
    signals: list[AgentSignal],
) -> bool:
    """Evaluate a single condition from a strategy definition.

    Condition format:
        {"type": "indicator", "name": "rsi", "timeframe": "1d", "op": "<", "value": 30}
        {"type": "agent", "name": "warren_buffett", "direction": "buy"}
        {"type": "price", "op": ">", "field": "sma_50"}
        {"type": "signal_count", "direction": "buy", "min_count": 2}
    """
    ctype = condition.get("type", "")

    if ctype == "indicator":
        return _eval_indicator(condition, context)
    elif ctype == "agent":
        return _eval_agent(condition, signals)
    elif ctype == "price":
        return _eval_price(condition, context)
    elif ctype == "signal_count":
        return _eval_signal_count(condition, signals)
    elif ctype == "composite":
        return _eval_composite(condition, context, signals)

    return False


def _eval_indicator(condition: dict, context: MarketContext) -> bool:
    """Evaluate a technical indicator condition."""
    name = condition.get("name", "")
    timeframe = condition.get("timeframe", "1d")
    op_str = condition.get("op", ">")
    target = condition.get("value")

    if target is None:
        return False

    technicals = context.technicals.get(timeframe)
    if not technicals:
        return False

    actual = getattr(technicals, name, None)
    if actual is None:
        return False

    op_fn = OPERATORS.get(op_str)
    if not op_fn:
        return False

    return op_fn(actual, target)


def _eval_agent(condition: dict, signals: list[AgentSignal]) -> bool:
    """Check if a specific agent produced a specific direction."""
    agent_name = condition.get("name", "")
    direction = condition.get("direction", "")
    min_confidence = condition.get("min_confidence", 0.0)

    for sig in signals:
        if sig.agent_name == agent_name:
            if sig.direction.value == direction and sig.confidence >= min_confidence:
                return True
    return False


def _eval_price(condition: dict, context: MarketContext) -> bool:
    """Evaluate a price-based condition."""
    op_str = condition.get("op", ">")
    field = condition.get("field", "")
    timeframe = condition.get("timeframe", "1d")

    technicals = context.technicals.get(timeframe)
    if not technicals:
        return False

    target = getattr(technicals, field, None)
    if target is None:
        return False

    op_fn = OPERATORS.get(op_str)
    if not op_fn:
        return False

    return op_fn(context.current_price, target)


def _eval_signal_count(condition: dict, signals: list[AgentSignal]) -> bool:
    """Check if enough agents agree on a direction."""
    direction = condition.get("direction", "buy")
    min_count = condition.get("min_count", 1)

    buy_directions = {"buy", "strong_buy"} if direction == "buy" else {"sell", "strong_sell"}
    count = sum(1 for s in signals if s.direction.value in buy_directions)
    return count >= min_count


def _eval_composite(
    condition: dict, context: MarketContext, signals: list[AgentSignal]
) -> bool:
    """Evaluate a composite condition (AND/OR of sub-conditions)."""
    logic = condition.get("logic", "and")
    sub_conditions = condition.get("conditions", [])

    if logic == "and":
        return all(evaluate_condition(c, context, signals) for c in sub_conditions)
    elif logic == "or":
        return any(evaluate_condition(c, context, signals) for c in sub_conditions)
    return False
