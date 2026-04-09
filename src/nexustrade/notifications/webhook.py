"""Generic webhook notification adapter."""

from __future__ import annotations

import logging

import httpx

from nexustrade.core.interfaces import NotificationAdapter

logger = logging.getLogger(__name__)


class WebhookNotifier(NotificationAdapter):
    """POST JSON notifications to an arbitrary webhook URL."""

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._headers = headers or {}

    @property
    def name(self) -> str:
        return "webhook"

    async def send(
        self,
        title: str,
        message: str,
        level: str = "info",
    ) -> bool:
        payload = {
            "title": title,
            "message": message,
            "level": level,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._url,
                    json=payload,
                    headers=self._headers,
                    timeout=10,
                )
                resp.raise_for_status()
                return True
        except Exception:
            logger.exception("Failed to send webhook notification")
            return False
