"""Alert dispatcher — fans events to user-configured notification channels.

Reads `notifications.channels` and `notifications.events` from config and
maps event categories (trade, fill, circuit_breaker, error, signal,
risk_blocked, etc.) to one or more channels (telegram, discord, email,
webhook). Records each dispatch into :class:`RuntimeState.alerts` so the
dashboard can show what was sent.

Channels gracefully degrade: if a channel is misconfigured or its env
vars are missing, it is skipped silently and an audit entry is logged.
This keeps the orchestrator running in demo mode where most users have
no real notification credentials.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

from nexustrade.core.interfaces import NotificationAdapter
from nexustrade.runtime.state import AlertRecord, RuntimeState

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _build_channel(spec: dict[str, Any]) -> NotificationAdapter | None:
    """Construct a notification adapter from a config dict.

    Recognised shapes::

        {name: telegram, bot_token: ..., chat_id: ...}
        {name: telegram, bot_token_env: TELEGRAM_BOT_TOKEN, chat_id_env: TELEGRAM_CHAT_ID}
        {name: discord, webhook_url: ...}
        {name: webhook, url: ..., headers: {...}}
        {name: email, smtp_host: ..., smtp_port: ..., username: ..., password: ..., to: ...}

    All credential fields support ``*_env`` siblings that read from the
    process environment so YAML never contains secrets.
    """

    name = spec.get("name", "").lower()

    def _resolve(key: str) -> str | None:
        if spec.get(key):
            return str(spec[key])
        env_key = spec.get(f"{key}_env")
        if env_key:
            return os.environ.get(str(env_key))
        return None

    try:
        if name == "telegram":
            from nexustrade.notifications.telegram import TelegramNotifier

            token = _resolve("bot_token")
            chat = _resolve("chat_id")
            if not token or not chat:
                return None
            return TelegramNotifier(token, chat)

        if name == "discord":
            from nexustrade.notifications.discord import DiscordNotifier

            url = _resolve("webhook_url")
            if not url:
                return None
            return DiscordNotifier(url)

        if name == "webhook":
            from nexustrade.notifications.webhook import WebhookNotifier

            url = _resolve("url")
            if not url:
                return None
            return WebhookNotifier(url, headers=spec.get("headers") or {})

        if name == "email":
            from nexustrade.notifications.email import EmailNotifier

            host = _resolve("smtp_host") or "localhost"
            port = int(spec.get("smtp_port") or 587)
            user = _resolve("username") or ""
            pwd = _resolve("password") or ""
            to = _resolve("to") or ""
            sender = _resolve("from") or user
            if not to:
                return None
            return EmailNotifier(
                smtp_host=host,
                smtp_port=port,
                username=user,
                password=pwd,
                from_address=sender,
                to_address=to,
            )
    except Exception:
        logger.exception("Failed to build notification channel for %s", spec)

    return None


class AlertDispatcher:
    """Routes events to one or more notification channels."""

    DEFAULT_ROUTES: dict[str, list[str]] = {
        "fill": ["telegram"],
        "trade": ["telegram"],
        "circuit_breaker": ["telegram", "email"],
        "risk_blocked": ["telegram"],
        "error": ["email"],
        "system": [],
    }

    def __init__(
        self,
        state: RuntimeState,
        channels: list[NotificationAdapter],
        routes: dict[str, list[str]] | None = None,
    ) -> None:
        self._state = state
        self._channels: dict[str, NotificationAdapter] = {c.name: c for c in channels}
        self._routes = routes or self.DEFAULT_ROUTES

    @classmethod
    def from_config(cls, state: RuntimeState, notifications_cfg: Any) -> AlertDispatcher:
        """Build a dispatcher from a :class:`NotificationConfig`."""
        channels: list[NotificationAdapter] = []
        for spec in getattr(notifications_cfg, "channels", []) or []:
            adapter = _build_channel(spec if isinstance(spec, dict) else dict(spec))
            if adapter is not None:
                channels.append(adapter)
        routes = dict(getattr(notifications_cfg, "events", {}) or {})
        return cls(state, channels, routes or None)

    @property
    def configured_channels(self) -> list[str]:
        return list(self._channels)

    async def dispatch(
        self,
        category: str,
        title: str,
        message: str,
        level: str = "info",
        channels: list[str] | None = None,
    ) -> AlertRecord:
        """Send an alert. Records the result regardless of delivery success."""
        target_names = channels if channels is not None else self._routes.get(category, [])
        targets = [self._channels[n] for n in target_names if n in self._channels]

        delivered: dict[str, bool] = {}
        if targets:
            results = await asyncio.gather(
                *(t.send(title, message, level=level) for t in targets),
                return_exceptions=True,
            )
            for tgt, res in zip(targets, results):
                delivered[tgt.name] = bool(res) if not isinstance(res, Exception) else False

        record = AlertRecord(
            timestamp=_now(),
            title=title,
            message=message,
            level=level,
            channels=[t.name for t in targets],
            delivered=delivered,
        )
        self._state.record_alert(record)
        return record
