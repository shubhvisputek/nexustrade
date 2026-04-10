"""Unit tests for notification adapters."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from nexustrade.notifications.discord import DiscordNotifier
from nexustrade.notifications.telegram import TelegramNotifier
from nexustrade.notifications.webhook import WebhookNotifier


# ---------------------------------------------------------------------------
# TelegramNotifier
# ---------------------------------------------------------------------------


class TestTelegramNotifier:
    """Tests for TelegramNotifier."""

    def test_name(self) -> None:
        notifier = TelegramNotifier(bot_token="tok123", chat_id="456")
        assert notifier.name == "telegram"

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        notifier = TelegramNotifier(bot_token="tok123", chat_id="456")

        mock_response = httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("POST", "https://api.telegram.org/bottok123/sendMessage"),
        )

        with patch("nexustrade.notifications.telegram.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await notifier.send("Test Title", "Test message", level="warning")

        assert result is True
        mock_client.post.assert_called_once()

        call_args = mock_client.post.call_args
        url = call_args[0][0]
        payload = call_args[1]["json"]

        assert url == "https://api.telegram.org/bottok123/sendMessage"
        assert payload["chat_id"] == "456"
        assert "Test Title" in payload["text"]
        assert payload["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_send_failure_returns_false(self) -> None:
        notifier = TelegramNotifier(bot_token="tok123", chat_id="456")

        with patch("nexustrade.notifications.telegram.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "error",
                request=httpx.Request("POST", "http://x"),
                response=httpx.Response(500),
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await notifier.send("Fail", "msg")

        assert result is False


# ---------------------------------------------------------------------------
# DiscordNotifier
# ---------------------------------------------------------------------------


class TestDiscordNotifier:
    """Tests for DiscordNotifier."""

    def test_name(self) -> None:
        notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/123/abc")
        assert notifier.name == "discord"

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/123/abc")

        mock_response = httpx.Response(
            204,
            request=httpx.Request("POST", "https://discord.com/api/webhooks/123/abc"),
        )

        with patch("nexustrade.notifications.discord.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await notifier.send("Trade Alert", "BUY AAPL", level="info")

        assert result is True
        mock_client.post.assert_called_once()

        call_args = mock_client.post.call_args
        url = call_args[0][0]
        payload = call_args[1]["json"]

        assert url == "https://discord.com/api/webhooks/123/abc"
        assert "content" in payload
        assert "Trade Alert" in payload["content"]

    @pytest.mark.asyncio
    async def test_send_failure_returns_false(self) -> None:
        notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/123/abc")

        with patch("nexustrade.notifications.discord.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await notifier.send("Fail", "msg")

        assert result is False


# ---------------------------------------------------------------------------
# WebhookNotifier
# ---------------------------------------------------------------------------


class TestWebhookNotifier:
    """Tests for WebhookNotifier."""

    def test_name(self) -> None:
        notifier = WebhookNotifier(url="https://example.com/hook")
        assert notifier.name == "webhook"

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        notifier = WebhookNotifier(
            url="https://example.com/hook",
            headers={"X-Custom": "val"},
        )

        mock_response = httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.com/hook"),
        )

        with patch("nexustrade.notifications.webhook.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await notifier.send("Signal", "BUY TSLA", level="info")

        assert result is True
        mock_client.post.assert_called_once()

        call_args = mock_client.post.call_args
        url = call_args[0][0]
        payload = call_args[1]["json"]
        headers = call_args[1]["headers"]

        assert url == "https://example.com/hook"
        assert payload == {"title": "Signal", "message": "BUY TSLA", "level": "info"}
        assert headers == {"X-Custom": "val"}

    @pytest.mark.asyncio
    async def test_send_failure_returns_false(self) -> None:
        notifier = WebhookNotifier(url="https://example.com/hook")

        with patch("nexustrade.notifications.webhook.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("boom")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await notifier.send("Fail", "msg")

        assert result is False
