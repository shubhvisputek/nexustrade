"""Tests for configuration system."""

import os
import pytest
from pathlib import Path

from nexustrade.core.config import (
    load_config, NexusTradeConfig, LLMConfig, LLMProviderConfig,
    AgentConfig, ExecutionConfig, RiskConfig, DataConfig,
)


CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
DEFAULT_YAML = CONFIG_DIR / "default.yaml"


class TestLoadDefaultConfig:
    def test_load_default_yaml(self):
        config = load_config(DEFAULT_YAML)
        assert isinstance(config, NexusTradeConfig)
        assert config.log_level == "INFO"

    def test_llm_config(self):
        config = load_config(DEFAULT_YAML)
        assert config.llm.mode in ("local", "cloud", "hybrid")
        assert config.llm.fast.provider == "ollama"
        assert config.llm.fast.model == "llama3:8b"
        assert config.llm.deep.provider == "anthropic"

    def test_nested_config_access(self):
        config = load_config(DEFAULT_YAML)
        assert config.llm.fast.model == "llama3:8b"
        assert config.risk.circuit_breaker.max_daily_loss_pct == 0.03
        assert config.data.cache.enabled is True

    def test_markets_config(self):
        config = load_config(DEFAULT_YAML)
        assert "us_equity" in config.markets
        assert "AAPL" in config.markets["us_equity"].symbols

    def test_agents_config(self):
        config = load_config(DEFAULT_YAML)
        assert len(config.agents.enabled) > 0
        assert config.agents.aggregation_mode == "weighted_confidence"

    def test_execution_brokers(self):
        config = load_config(DEFAULT_YAML)
        assert len(config.execution.brokers) > 0
        broker_names = [b.name for b in config.execution.brokers]
        assert "paper" in broker_names


class TestEnvVarOverride:
    def test_env_var_overrides_yaml(self, monkeypatch):
        monkeypatch.setenv("NEXUS__LOG_LEVEL", "DEBUG")
        config = load_config(DEFAULT_YAML)
        assert config.log_level == "DEBUG"

    def test_nested_env_var(self, monkeypatch):
        monkeypatch.setenv("NEXUS__LLM__MODE", "local")
        config = load_config(DEFAULT_YAML)
        assert config.llm.mode == "local"


class TestConfigValidation:
    def test_missing_config_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")

    def test_invalid_enum_value(self):
        with pytest.raises(Exception):  # Pydantic ValidationError
            NexusTradeConfig(
                llm=LLMConfig(
                    mode="invalid_mode",  # type: ignore
                    fast=LLMProviderConfig(provider="ollama", model="llama3:8b"),
                    deep=LLMProviderConfig(provider="anthropic", model="claude"),
                ),
            )

    def test_valid_minimal_config(self):
        config = NexusTradeConfig(
            llm=LLMConfig(
                fast=LLMProviderConfig(provider="ollama", model="llama3:8b"),
                deep=LLMProviderConfig(provider="anthropic", model="claude-sonnet-4-20250514"),
            ),
        )
        assert config.risk.sizing_model == "kelly"  # default
        assert config.agents.min_confidence == 0.6  # default


class TestConfigOverrides:
    def test_override_dict(self):
        config = load_config(DEFAULT_YAML, overrides={"log_level": "WARNING"})
        assert config.log_level == "WARNING"

    def test_deep_override(self):
        config = load_config(DEFAULT_YAML, overrides={
            "risk": {"max_position_pct": 0.10}
        })
        assert config.risk.max_position_pct == 0.10
        # Other risk values should be preserved from YAML
        assert config.risk.sizing_model == "kelly"


class TestExampleConfigs:
    @pytest.mark.parametrize("config_name", [
        "us_equities_basic.yaml",
        "india_nse_zerodha.yaml",
        "crypto_binance.yaml",
        "forex_with_tv.yaml",
        "multi_market_full.yaml",
        "local_ollama_only.yaml",
    ])
    def test_example_config_loads(self, config_name):
        config_path = CONFIG_DIR / "examples" / config_name
        config = load_config(config_path)
        assert isinstance(config, NexusTradeConfig)
        assert config.llm.fast.provider in ("ollama", "anthropic", "openai")
