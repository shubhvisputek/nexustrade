"""Telegram notification adapter."""

from __future__ import annotations

import logging

import httpx

from nexustrade.core.interfaces import NotificationAdapter

logger = logging.getLogger(__name__)

_LEVEL_EMOJI = {
    "info": "\u2139\ufe0f",
    "warning": "\u26a0\ufe0f",
    "error": "\u274c",
    "critical": "\U0001f6a8",
}


class TelegramNotifier(NotificationAdapter):
    """Send notifications via the Telegram Bot API.

    Uses raw HTTP calls via *httpx* so the heavy ``python-telegram-bot``
    package is not required at runtime.
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    @property
    def name(self) -> str:
        return "telegram"

    async def send(
        self,
        title: str,
        message: str,
        level: str = "info",
    ) -> bool:
        emoji = _LEVEL_EMOJI.get(level, _LEVEL_EMOJI["info"])
        text = f"{emoji} *{title}*\n{message}"

        url = f"{self._base_url}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10)
                resp.raise_for_status()
                return True
        except Exception:
            logger.exception("Failed to send Telegram notification")
            return False
