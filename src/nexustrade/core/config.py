"""NexusTrade configuration system.

Loads from: YAML file → environment variables → CLI flags.
All settings validated by Pydantic.
Environment variables use NEXUS__ prefix with __ nesting delimiter.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Sub-models ---

class LLMProviderConfig(BaseModel):
    provider: str  # "ollama", "anthropic", "openai", "deepseek", "gemini", "groq"
    model: str  # "llama3:8b", "claude-sonnet-4-20250514", "gpt-4o"
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 4096


class LLMConfig(BaseModel):
    mode: Literal["local", "cloud", "hybrid"] = "hybrid"
    fast: LLMProviderConfig
    deep: LLMProviderConfig
    vision: LLMProviderConfig | None = None
    fallbacks: list[LLMProviderConfig] = []


class AgentEntry(BaseModel):
    name: str
    source: str = ""  # "ai_hedge_fund", "trading_agents", "finrl", etc.
    enabled: bool = True
    llm_override: dict[str, Any] | None = None
    config: dict[str, Any] = {}


class AgentConfig(BaseModel):
    enabled: list[AgentEntry] = []
    aggregation_mode: Literal[
        "weighted_confidence", "majority", "unanimous", "portfolio_manager"
    ] = "weighted_confidence"
    min_confidence: float = 0.6
    execution_mode: Literal["parallel", "sequential", "dag"] = "parallel"
    debate_rounds: int = 2
    early_termination_confidence: float = 0.9


class TradingViewConfig(BaseModel):
    enabled: bool = False
    webhook_port: int = 8888
    passphrase: str = ""
    india_route: str = "openalgo"
    us_route: str = "alpaca"


class BrokerEntry(BaseModel):
    name: str  # "alpaca", "openalgo", "ccxt_broker", "paper"
    enabled: bool = True
    markets: list[str] = []  # ["us_equity"], ["india_equity", "india_fno"]
    config: dict[str, Any] = {}


class ExecutionConfig(BaseModel):
    mode: Literal["tradingview", "python", "both"] = "python"
    brokers: list[BrokerEntry] = []
    tradingview: TradingViewConfig = TradingViewConfig()


class MarketConfig(BaseModel):
    symbols: list[str] = []
    data_provider: str = "openbb"
    exchange: str | None = None


class CircuitBreakerConfig(BaseModel):
    max_daily_loss_pct: float = 0.03
    max_consecutive_losses: int = 5
    max_open_positions: int = 10
    cooldown_minutes: int = 60


class RiskConfig(BaseModel):
    max_position_pct: float = 0.05
    max_portfolio_risk: float = 0.20
    sizing_model: Literal[
        "cvar", "kelly", "fixed_fraction", "volatility", "max_drawdown"
    ] = "kelly"
    cvar_confidence: float = 0.95
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()


class SchedulerConfig(BaseModel):
    analysis_interval: str = "4h"
    timeframes: list[str] = Field(default_factory=lambda: ["1h", "4h", "1d"])
    risk_check_interval: str = "15m"


class DataProviderEntry(BaseModel):
    name: str
    enabled: bool = True
    priority: int = 1
    config: dict[str, Any] = {}


class CacheConfig(BaseModel):
    enabled: bool = True
    ttl_seconds: dict[str, int] = Field(default_factory=lambda: {
        "quote": 0,
        "ohlcv_1m": 60,
        "ohlcv_1h": 300,
        "ohlcv_1d": 3600,
        "fundamentals": 86400,
        "news": 300,
    })
    warm_on_start: bool = True


class DataConfig(BaseModel):
    providers: list[DataProviderEntry] = []
    routing: dict[str, list[str]] = {}  # market → provider priority list
    cache: CacheConfig = CacheConfig()


class MemoryConfig(BaseModel):
    enabled: bool = True
    retention_days: int = 90
    max_entries: int = 10000
    similarity_threshold: float = 0.75


class NotificationConfig(BaseModel):
    channels: list[dict[str, Any]] = []
    events: dict[str, list[str]] = Field(default_factory=lambda: {
        "trade": ["telegram"],
        "circuit_breaker": ["telegram", "email"],
        "error": ["email"],
    })


# --- Root configuration ---

class NexusTradeConfig(BaseSettings):
    """Root configuration — all settings validated by Pydantic."""
    llm: LLMConfig
    agents: AgentConfig = AgentConfig()
    execution: ExecutionConfig = ExecutionConfig()
    markets: dict[str, MarketConfig] = {}
    risk: RiskConfig = RiskConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    data: DataConfig = DataConfig()
    memory: MemoryConfig = MemoryConfig()
    notifications: NotificationConfig = NotificationConfig()
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="NEXUS__",
        env_nested_delimiter="__",
    )


def load_config(
    yaml_path: str | Path = "config/default.yaml",
    overrides: dict[str, Any] | None = None,
) -> NexusTradeConfig:
    """Load configuration from YAML file, with optional overrides.

    Priority: overrides > env vars > YAML file defaults.
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        yaml_data = yaml.safe_load(f) or {}

    if overrides:
        _deep_merge(yaml_data, overrides)

    # Env vars override YAML: read env vars and merge on top
    env_overrides = _extract_env_overrides("NEXUS__", "__")
    if env_overrides:
        _deep_merge(yaml_data, env_overrides)

    return NexusTradeConfig(**yaml_data)


def _extract_env_overrides(prefix: str, delimiter: str) -> dict[str, Any]:
    """Extract environment variables with given prefix into nested dict."""
    result: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].lower().split(delimiter)
        d = result
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return result


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base dict."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
