"""Lightweight async scheduler for NexusTrade.

Implements interval, cron, and market-session scheduling using only
``asyncio`` — no external scheduling libraries required.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Type alias for an async callback with no arguments.
AsyncCallback = Callable[[], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# Market session definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MarketSession:
    """Trading hours for a single market."""

    open_time: time
    close_time: time
    timezone: ZoneInfo
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)  # Mon-Fri by default


MARKET_SESSIONS: dict[str, MarketSession] = {
    "us": MarketSession(
        open_time=time(9, 30),
        close_time=time(16, 0),
        timezone=ZoneInfo("America/New_York"),
    ),
    "india_nse": MarketSession(
        open_time=time(9, 15),
        close_time=time(15, 30),
        timezone=ZoneInfo("Asia/Kolkata"),
    ),
    "crypto": MarketSession(
        open_time=time(0, 0),
        close_time=time(23, 59, 59),
        timezone=ZoneInfo("UTC"),
        weekdays=(0, 1, 2, 3, 4, 5, 6),  # 24/7
    ),
}


# ---------------------------------------------------------------------------
# Job definitions
# ---------------------------------------------------------------------------

@dataclass
class _Job:
    """Internal representation of a scheduled job."""

    name: str
    callback: AsyncCallback
    next_run: datetime
    task: asyncio.Task[None] | None = field(default=None, repr=False)


@dataclass
class _IntervalJob(_Job):
    interval_seconds: float = 60.0


@dataclass
class _CronJob(_Job):
    minute: int | None = None  # None → every minute
    hour: int | None = None  # None → every hour


@dataclass
class _MarketSessionJob(_Job):
    market: str = "us"
    event: str = "open"  # "open" or "close"


# ---------------------------------------------------------------------------
# Cron helpers
# ---------------------------------------------------------------------------

def _parse_cron_field(field_str: str) -> int | None:
    """Parse a single cron field.  ``'*'`` → ``None``, else ``int``."""
    return None if field_str.strip() == "*" else int(field_str.strip())


def _next_cron_occurrence(
    minute: int | None,
    hour: int | None,
    after: datetime,
) -> datetime:
    """Return the next datetime matching *minute* and *hour* after *after*."""
    candidate = after.replace(second=0, microsecond=0)

    # Start from the next minute
    candidate += timedelta(minutes=1)

    # Search up to 48 hours (safety bound)
    for _ in range(48 * 60):
        m_ok = minute is None or candidate.minute == minute
        h_ok = hour is None or candidate.hour == hour
        if m_ok and h_ok:
            return candidate
        candidate += timedelta(minutes=1)

    # Fallback — should never happen with valid cron values
    return after + timedelta(hours=1)  # pragma: no cover


def _next_market_event(
    market: str,
    event: str,
    after: datetime,
) -> datetime:
    """Return the next market open/close time after *after*."""
    session = MARKET_SESSIONS[market]
    tz = session.timezone

    target_time = session.open_time if event == "open" else session.close_time

    local_now = after.astimezone(tz)
    candidate = local_now.replace(
        hour=target_time.hour,
        minute=target_time.minute,
        second=0,
        microsecond=0,
    )

    # If we already passed today's target, start from tomorrow
    if candidate <= local_now:
        candidate += timedelta(days=1)

    # Advance to the next valid weekday
    for _ in range(8):
        if candidate.weekday() in session.weekdays:
            return candidate.astimezone(ZoneInfo("UTC"))
        candidate += timedelta(days=1)

    return candidate.astimezone(ZoneInfo("UTC"))  # pragma: no cover


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    """Lightweight async scheduler.

    Parameters
    ----------
    timezone_str:
        IANA timezone string used as the scheduler's reference timezone.
    """

    def __init__(self, timezone_str: str = "UTC") -> None:
        self._tz = ZoneInfo(timezone_str)
        self._jobs: dict[str, _Job] = {}
        self._running = False

    # -- public API ----------------------------------------------------------

    def add_interval_job(
        self,
        name: str,
        callback: AsyncCallback,
        interval_seconds: float,
    ) -> None:
        """Schedule *callback* to run every *interval_seconds*."""
        now = datetime.now(tz=self._tz)
        job = _IntervalJob(
            name=name,
            callback=callback,
            next_run=now + timedelta(seconds=interval_seconds),
            interval_seconds=interval_seconds,
        )
        self._jobs[name] = job

    def add_cron_job(
        self,
        name: str,
        callback: AsyncCallback,
        cron_expr: str,
    ) -> None:
        """Schedule *callback* using a simple cron expression.

        Only the first two fields are used: ``minute hour``.
        Wildcards (``*``) are supported.  Examples::

            "30 9 * * *"   → every day at 09:30
            "0 * * * *"    → every hour on the hour
            "*/5 * * * *"  → not supported (simple parser)
        """
        parts = cron_expr.split()
        minute = _parse_cron_field(parts[0])
        hour = _parse_cron_field(parts[1]) if len(parts) > 1 else None

        now = datetime.now(tz=self._tz)
        next_run = _next_cron_occurrence(minute, hour, now)

        job = _CronJob(
            name=name,
            callback=callback,
            next_run=next_run,
            minute=minute,
            hour=hour,
        )
        self._jobs[name] = job

    def add_market_session_job(
        self,
        name: str,
        callback: AsyncCallback,
        market: str,
        event: str,
    ) -> None:
        """Schedule *callback* for a market session event.

        Parameters
        ----------
        market:
            One of ``'us'``, ``'india_nse'``, ``'crypto'``.
        event:
            ``'open'`` or ``'close'``.
        """
        if market not in MARKET_SESSIONS:
            raise ValueError(
                f"Unknown market {market!r}. "
                f"Valid: {list(MARKET_SESSIONS.keys())}"
            )
        if event not in ("open", "close"):
            raise ValueError(f"event must be 'open' or 'close', got {event!r}")

        now = datetime.now(tz=ZoneInfo("UTC"))
        next_run = _next_market_event(market, event, now)

        job = _MarketSessionJob(
            name=name,
            callback=callback,
            next_run=next_run,
            market=market,
            event=event,
        )
        self._jobs[name] = job

    async def start(self) -> None:
        """Start the scheduler loop.  Runs until :meth:`stop` is called."""
        self._running = True
        logger.info("Scheduler started (%d jobs)", len(self._jobs))

        while self._running:
            now = datetime.now(tz=self._tz)
            for job in list(self._jobs.values()):
                # Normalise both to UTC for comparison
                now_utc = now.astimezone(ZoneInfo("UTC"))
                next_utc = job.next_run.astimezone(ZoneInfo("UTC"))
                if now_utc >= next_utc:
                    logger.debug("Running job %s", job.name)
                    try:
                        await job.callback()
                    except Exception:
                        logger.exception("Job %s failed", job.name)
                    self._advance_job(job)
            await asyncio.sleep(1)

    def stop(self) -> None:
        """Signal the scheduler loop to stop."""
        self._running = False
        logger.info("Scheduler stopped")

    def get_next_run(self, name: str) -> datetime:
        """Return the next scheduled run time for job *name*."""
        return self._jobs[name].next_run

    # -- internal ------------------------------------------------------------

    def _advance_job(self, job: _Job) -> None:
        """Compute and set the next run time for *job*."""
        if isinstance(job, _IntervalJob):
            job.next_run = datetime.now(tz=self._tz) + timedelta(
                seconds=job.interval_seconds
            )
        elif isinstance(job, _CronJob):
            job.next_run = _next_cron_occurrence(
                job.minute, job.hour, datetime.now(tz=self._tz)
            )
        elif isinstance(job, _MarketSessionJob):
            job.next_run = _next_market_event(
                job.market,
                job.event,
                datetime.now(tz=ZoneInfo("UTC")),
            )
