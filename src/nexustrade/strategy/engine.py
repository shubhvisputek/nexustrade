"""Strategy evaluation engine.

Evaluates entry/exit conditions against MarketContext and agent signals.
Supports hot-reload of strategy YAML files.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from nexustrade.core.interfaces import StrategyInterface
from nexustrade.core.models import AgentSignal, MarketContext, Position
from nexustrade.strategy.conditions import evaluate_condition
from nexustrade.strategy.parser import StrategyDefinition, parse_strategy

logger = logging.getLogger(__name__)


class YAMLStrategy(StrategyInterface):
    """Strategy driven by YAML rule definitions.

    Evaluates entry and exit conditions defined in YAML against
    current market context and agent signals.
    """

    def __init__(self, definition: StrategyDefinition) -> None:
        self._definition = definition
        self._rules = definition.rules

    @property
    def name(self) -> str:
        return self._definition.name

    def evaluate_entry(
        self,
        context: MarketContext,
        signals: list[AgentSignal],
    ) -> bool:
        """Check if entry conditions are met for any rule.

        All conditions in a rule must be true (AND logic).
        Any rule being true triggers entry (OR across rules).
        """
        for rule in self._rules:
            if rule.symbols and context.symbol not in rule.symbols:
                continue

            if self._evaluate_conditions(rule.entry_conditions, context, signals):
                logger.info(
                    "Entry triggered for %s by rule '%s'",
                    context.symbol, rule.name,
                )
                return True

        return False

    def evaluate_exit(
        self,
        context: MarketContext,
        signals: list[AgentSignal],
        position: Position,
    ) -> bool:
        """Check if exit conditions are met for any rule."""
        for rule in self._rules:
            if rule.symbols and context.symbol not in rule.symbols:
                continue

            if self._evaluate_conditions(rule.exit_conditions, context, signals):
                logger.info(
                    "Exit triggered for %s by rule '%s'",
                    context.symbol, rule.name,
                )
                return True

        return False

    def _evaluate_conditions(
        self,
        conditions: list[dict[str, Any]],
        context: MarketContext,
        signals: list[AgentSignal],
    ) -> bool:
        """Evaluate all conditions (AND logic)."""
        if not conditions:
            return False
        return all(
            evaluate_condition(c, context, signals)
            for c in conditions
        )


class StrategyEngine:
    """Manages strategy loading, hot-reload, and evaluation."""

    def __init__(self) -> None:
        self._strategies: dict[str, YAMLStrategy] = {}
        self._file_mtimes: dict[str, float] = {}

    def load_strategy(self, yaml_path: str | Path) -> YAMLStrategy:
        """Load a strategy from YAML file."""
        path = Path(yaml_path)
        definition = parse_strategy(path)
        strategy = YAMLStrategy(definition)
        self._strategies[definition.name] = strategy
        self._file_mtimes[definition.name] = os.path.getmtime(path)
        logger.info("Loaded strategy: %s", definition.name)
        return strategy

    def load_from_definition(self, definition: StrategyDefinition) -> YAMLStrategy:
        """Load a strategy from a pre-parsed definition."""
        strategy = YAMLStrategy(definition)
        self._strategies[definition.name] = strategy
        return strategy

    def get_strategy(self, name: str) -> YAMLStrategy | None:
        return self._strategies.get(name)

    def evaluate_all(
        self,
        context: MarketContext,
        signals: list[AgentSignal],
    ) -> dict[str, bool]:
        """Evaluate all loaded strategies for entry."""
        return {
            name: strategy.evaluate_entry(context, signals)
            for name, strategy in self._strategies.items()
        }

    @property
    def strategy_names(self) -> list[str]:
        return list(self._strategies.keys())
