"""Discord notification adapter."""

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


class DiscordNotifier(NotificationAdapter):
    """Send notifications to a Discord channel via webhook."""

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    @property
    def name(self) -> str:
        return "discord"

    async def send(
        self,
        title: str,
        message: str,
        level: str = "info",
    ) -> bool:
        emoji = _LEVEL_EMOJI.get(level, _LEVEL_EMOJI["info"])
        content = f"{emoji} **{title}**\n{message}"

        payload = {"content": content}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._webhook_url,
                    json=payload,
                    timeout=10,
                )
                resp.raise_for_status()
                return True
        except Exception:
            logger.exception("Failed to send Discord notification")
            return False
