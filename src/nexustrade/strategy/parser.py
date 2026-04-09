"""YAML strategy definition parser.

Parses strategy YAML files that define entry/exit conditions
using agent signals, technical indicators, and price rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class StrategyCondition(BaseModel):
    """A single condition in a strategy rule."""
    type: str  # "indicator", "agent", "price", "signal_count", "composite"
    name: str = ""
    op: str = ""
    value: float | None = None
    direction: str = ""
    timeframe: str = "1d"
    field: str = ""
    min_count: int = 0
    min_confidence: float = 0.0
    logic: str = "and"  # for composite
    conditions: list[dict[str, Any]] = []


class StrategyRule(BaseModel):
    """A strategy rule with entry and exit conditions."""
    name: str
    description: str = ""
    entry_conditions: list[dict[str, Any]]
    exit_conditions: list[dict[str, Any]]
    symbols: list[str] = []
    timeframes: list[str] = []
    agents: list[str] = []
    risk_overrides: dict[str, Any] = {}


class StrategyDefinition(BaseModel):
    """Complete strategy definition from YAML."""
    name: str
    version: str = "1.0"
    description: str = ""
    rules: list[StrategyRule]
    defaults: dict[str, Any] = {}


def parse_strategy(yaml_path: str | Path) -> StrategyDefinition:
    """Parse a YAML strategy definition file.

    Args:
        yaml_path: Path to strategy YAML file

    Returns:
        Validated StrategyDefinition

    Raises:
        FileNotFoundError: If YAML file doesn't exist
        ValueError: If strategy is invalid
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Strategy file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError(f"Empty strategy file: {path}")

    if "name" not in raw:
        raise ValueError("Strategy must have a 'name' field")

    if "rules" not in raw or not raw["rules"]:
        raise ValueError("Strategy must have at least one rule")

    return StrategyDefinition(**raw)


def parse_strategy_from_dict(data: dict[str, Any]) -> StrategyDefinition:
    """Parse a strategy from a dict (for testing)."""
    return StrategyDefinition(**data)
