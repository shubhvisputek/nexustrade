"""Email notification adapter."""

from __future__ import annotations

import logging
from email.mime.text import MIMEText

from nexustrade.core.interfaces import NotificationAdapter

logger = logging.getLogger(__name__)


class EmailNotifier(NotificationAdapter):
    """Send notifications via SMTP email.

    Prefers *aiosmtplib* for async delivery.  If not installed, logs a
    warning and returns ``False``.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        from_addr: str,
        to_addr: str,
        password: str,
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._from_addr = from_addr
        self._to_addr = to_addr
        self._password = password

    @property
    def name(self) -> str:
        return "email"

    async def send(
        self,
        title: str,
        message: str,
        level: str = "info",
    ) -> bool:
        try:
            import aiosmtplib  # type: ignore[import-untyped]
        except ImportError:
            logger.warning(
                "aiosmtplib is not installed — email notification skipped. "
                "Install with: pip install aiosmtplib"
            )
            return False

        msg = MIMEText(message)
        msg["Subject"] = f"[{level.upper()}] {title}"
        msg["From"] = self._from_addr
        msg["To"] = self._to_addr

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._smtp_host,
                port=self._smtp_port,
                username=self._from_addr,
                password=self._password,
                use_tls=True,
            )
            return True
        except Exception:
            logger.exception("Failed to send email notification")
            return False
