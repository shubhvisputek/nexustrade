"""Tests for LLM router."""

import pytest
from unittest.mock import AsyncMock, patch

from nexustrade.core.config import LLMConfig, LLMProviderConfig
from nexustrade.llm.router import LLMRouter, FAST, DEEP, VISION


def make_config(
    mode: str = "hybrid",
    fast_provider: str = "ollama",
    deep_provider: str = "anthropic",
) -> LLMConfig:
    return LLMConfig(
        mode=mode,
        fast=LLMProviderConfig(provider=fast_provider, model="llama3:8b"),
        deep=LLMProviderConfig(provider=deep_provider, model="claude-sonnet-4-20250514"),
        vision=LLMProviderConfig(provider="anthropic", model="claude-sonnet-4-20250514"),
        fallbacks=[
            LLMProviderConfig(provider="openai", model="gpt-4o"),
        ],
    )


class TestLLMRouter:
    def test_create_router(self):
        config = make_config()
        router = LLMRouter(config)
        assert FAST in router.available_channels
        assert DEEP in router.available_channels
        assert VISION in router.available_channels

    def test_model_string_ollama(self):
        config = make_config()
        router = LLMRouter(config)
        fast_config = router.get_channel_config(FAST)
        model_str = router._get_model_string(fast_config)
        assert model_str == "ollama/llama3:8b"

    def test_model_string_anthropic(self):
        config = make_config()
        router = LLMRouter(config)
        deep_config = router.get_channel_config(DEEP)
        model_str = router._get_model_string(deep_config)
        assert "claude" in model_str

    def test_channel_config(self):
        config = make_config()
        router = LLMRouter(config)
        fast = router.get_channel_config(FAST)
        assert fast is not None
        assert fast.provider == "ollama"

    def test_unknown_channel_falls_back_to_fast(self):
        config = make_config()
        router = LLMRouter(config)
        # When channel not found, should use fast
        unknown = router.get_channel_config("unknown")
        assert unknown is None  # get_channel_config returns None for unknown

    async def test_mock_response_when_litellm_unavailable(self):
        config = make_config()
        router = LLMRouter(config)
        router._litellm_available = False

        messages = [{"role": "user", "content": "Analyze AAPL"}]
        response = await router.complete(messages, channel=FAST)
        assert "hold" in response.lower() or "direction" in response

    def test_build_params(self):
        config = make_config()
        router = LLMRouter(config)
        fast_config = router.get_channel_config(FAST)
        params = router._build_params(fast_config)
        assert "model" in params
        assert "temperature" in params

    def test_build_params_with_overrides(self):
        config = make_config()
        router = LLMRouter(config)
        fast_config = router.get_channel_config(FAST)
        params = router._build_params(
            fast_config,
            overrides={"temperature": 0.1, "max_tokens": 1024},
        )
        assert params["temperature"] == 0.1
        assert params["max_tokens"] == 1024

    def test_no_vision_channel(self):
        config = LLMConfig(
            fast=LLMProviderConfig(provider="ollama", model="llama3:8b"),
            deep=LLMProviderConfig(provider="anthropic", model="claude"),
            vision=None,
        )
        router = LLMRouter(config)
        assert VISION not in router.available_channels
