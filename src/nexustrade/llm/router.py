"""LLM Router — channel-based routing to different LLM providers.

Routes requests to fast/deep/vision channels based on the calling context.
Uses LiteLLM for the actual API calls, with fallback chains on failure.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nexustrade.core.config import LLMConfig, LLMProviderConfig

logger = logging.getLogger(__name__)

# Channel types
FAST = "fast"
DEEP = "deep"
VISION = "vision"


class LLMRouter:
    """Routes LLM requests to the appropriate provider based on channel.

    Channels:
        - fast: Quick analysis, simple tasks (Ollama/local models)
        - deep: Complex reasoning, synthesis (Claude/GPT-4)
        - vision: Chart and image analysis (vision-capable models)

    Supports per-agent overrides and fallback chains.
    """

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._channels: dict[str, LLMProviderConfig] = {
            FAST: config.fast,
            DEEP: config.deep,
        }
        if config.vision:
            self._channels[VISION] = config.vision
        self._fallbacks = config.fallbacks
        self._litellm_available = self._check_litellm()

    def _check_litellm(self) -> bool:
        try:
            import litellm  # noqa: F401
            return True
        except ImportError:
            logger.warning("LiteLLM not installed. LLM calls will use mock responses.")
            return False

    def _get_model_string(self, provider_config: LLMProviderConfig) -> str:
        """Build LiteLLM model string from provider config.

        LiteLLM format: "provider/model" (e.g., "ollama/llama3:8b", "anthropic/claude-sonnet-4-20250514")
        """
        provider = provider_config.provider
        model = provider_config.model

        if provider == "ollama":
            return f"ollama/{model}"
        elif provider == "anthropic":
            return model  # LiteLLM handles anthropic models natively
        elif provider == "openai":
            return model  # LiteLLM handles openai models natively
        elif provider in ("deepseek", "gemini", "groq"):
            return f"{provider}/{model}"
        return model

    async def complete(
        self,
        messages: list[dict[str, str]],
        channel: str = FAST,
        agent_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Send a completion request through the specified channel.

        Args:
            messages: List of message dicts [{"role": "user", "content": "..."}]
            channel: "fast", "deep", or "vision"
            agent_overrides: Per-agent LLM parameter overrides
            **kwargs: Additional LiteLLM params

        Returns:
            Response text from the LLM.
        """
        provider_config = self._channels.get(channel)
        if not provider_config:
            provider_config = self._channels[FAST]

        # Apply agent overrides
        params = self._build_params(provider_config, agent_overrides, **kwargs)

        # Try primary provider
        try:
            return await self._call_llm(params, messages)
        except Exception as e:
            logger.warning("Primary LLM (%s) failed: %s", channel, e)

        # Try fallbacks
        for fallback_config in self._fallbacks:
            try:
                fallback_params = self._build_params(fallback_config, agent_overrides, **kwargs)
                return await self._call_llm(fallback_params, messages)
            except Exception as e:
                logger.warning("Fallback LLM (%s) failed: %s", fallback_config.model, e)

        raise RuntimeError(f"All LLM providers failed for channel '{channel}'")

    def _build_params(
        self,
        config: LLMProviderConfig,
        overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build LiteLLM call parameters."""
        params: dict[str, Any] = {
            "model": self._get_model_string(config),
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_tokens": config.max_tokens,
        }

        if config.api_key:
            params["api_key"] = config.api_key

        if config.base_url:
            params["api_base"] = config.base_url

        # Apply overrides
        if overrides:
            params.update(overrides)
        params.update(kwargs)

        return params

    async def _call_llm(
        self, params: dict[str, Any], messages: list[dict[str, str]]
    ) -> str:
        """Make the actual LLM call via LiteLLM."""
        if not self._litellm_available:
            return self._mock_response(messages)

        import litellm

        model = params.pop("model")
        response = await asyncio.to_thread(
            litellm.completion,
            model=model,
            messages=messages,
            **params,
        )
        return response.choices[0].message.content

    def _mock_response(self, messages: list[dict[str, str]]) -> str:
        """Generate a mock response when LiteLLM is not available."""
        return '{"direction": "hold", "confidence": 0.5, "reasoning": "LLM not available — mock response"}'

    def get_channel_config(self, channel: str) -> LLMProviderConfig | None:
        """Get the provider config for a channel."""
        return self._channels.get(channel)

    @property
    def available_channels(self) -> list[str]:
        return list(self._channels.keys())
