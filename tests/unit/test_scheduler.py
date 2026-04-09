"""Unit tests for the scheduler engine."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from nexustrade.scheduler.engine import (
    MARKET_SESSIONS,
    Scheduler,
    _next_cron_occurrence,
    _next_market_event,
)


class TestIntervalJob:
    """Tests for interval-based scheduling."""

    def test_next_run_is_correct(self) -> None:
        scheduler = Scheduler(timezone_str="UTC")
        before = datetime.now(tz=ZoneInfo("UTC"))

        async def noop() -> None:
            pass

        scheduler.add_interval_job("test_interval", noop, interval_seconds=60)
        next_run = scheduler.get_next_run("test_interval")
        after = datetime.now(tz=ZoneInfo("UTC"))

        # next_run should be ~60s from now
        assert next_run >= before + timedelta(seconds=59)
        assert next_run <= after + timedelta(seconds=61)

    def test_interval_10_seconds(self) -> None:
        scheduler = Scheduler(timezone_str="UTC")
        before = datetime.now(tz=ZoneInfo("UTC"))

        async def noop() -> None:
            pass

        scheduler.add_interval_job("fast", noop, interval_seconds=10)
        next_run = scheduler.get_next_run("fast")

        assert next_run >= before + timedelta(seconds=9)
        assert next_run <= before + timedelta(seconds=12)


class TestCronJob:
    """Tests for cron-based scheduling."""

    def test_cron_parsing_930(self) -> None:
        """'30 9 * * *' should produce a next occurrence at 9:30."""
        now = datetime(2025, 1, 15, 8, 0, 0, tzinfo=ZoneInfo("UTC"))
        next_run = _next_cron_occurrence(minute=30, hour=9, after=now)

        assert next_run.hour == 9
        assert next_run.minute == 30

    def test_cron_parsing_already_passed_today(self) -> None:
        """If 9:30 already passed, next occurrence is tomorrow."""
        now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        next_run = _next_cron_occurrence(minute=30, hour=9, after=now)

        assert next_run.hour == 9
        assert next_run.minute == 30
        assert next_run.date() == now.date() + timedelta(days=1)

    def test_cron_wildcard_hour(self) -> None:
        """'30 * * * *' should fire at the next :30."""
        now = datetime(2025, 1, 15, 14, 25, 0, tzinfo=ZoneInfo("UTC"))
        next_run = _next_cron_occurrence(minute=30, hour=None, after=now)

        assert next_run.minute == 30
        assert next_run.hour == 14  # Same hour, just 5 minutes later

    def test_scheduler_add_cron_job(self) -> None:
        scheduler = Scheduler(timezone_str="UTC")

        async def noop() -> None:
            pass

        scheduler.add_cron_job("daily_930", noop, "30 9 * * *")
        next_run = scheduler.get_next_run("daily_930")

        assert next_run.hour == 9
        assert next_run.minute == 30


class TestMarketSessionJob:
    """Tests for market session scheduling."""

    def test_us_market_open_time(self) -> None:
        """US market opens at 9:30 ET."""
        session = MARKET_SESSIONS["us"]
        assert session.open_time == time(9, 30)
        assert session.timezone == ZoneInfo("America/New_York")

    def test_us_market_close_time(self) -> None:
        """US market closes at 16:00 ET."""
        session = MARKET_SESSIONS["us"]
        assert session.close_time == time(16, 0)

    def test_india_nse_session(self) -> None:
        """India NSE: 9:15 - 15:30 IST."""
        session = MARKET_SESSIONS["india_nse"]
        assert session.open_time == time(9, 15)
        assert session.close_time == time(15, 30)
        assert session.timezone == ZoneInfo("Asia/Kolkata")

    def test_crypto_session_24_7(self) -> None:
        """Crypto runs 24/7."""
        session = MARKET_SESSIONS["crypto"]
        assert session.weekdays == (0, 1, 2, 3, 4, 5, 6)

    def test_next_market_event_us_open(self) -> None:
        """Compute next US market open from a known time."""
        # Monday 8:00 ET → should get 9:30 ET same day
        et = ZoneInfo("America/New_York")
        now = datetime(2025, 1, 13, 8, 0, 0, tzinfo=et)  # Monday
        next_open = _next_market_event("us", "open", now.astimezone(ZoneInfo("UTC")))

        local = next_open.astimezone(et)
        assert local.hour == 9
        assert local.minute == 30
        assert local.weekday() == 0  # Monday

    def test_next_market_event_skips_weekend(self) -> None:
        """If today is Saturday, US open should be Monday."""
        et = ZoneInfo("America/New_York")
        saturday = datetime(2025, 1, 18, 12, 0, 0, tzinfo=et)  # Saturday
        next_open = _next_market_event("us", "open", saturday.astimezone(ZoneInfo("UTC")))

        local = next_open.astimezone(et)
        assert local.weekday() == 0  # Monday
        assert local.hour == 9
        assert local.minute == 30

    def test_scheduler_add_market_session_job(self) -> None:
        scheduler = Scheduler(timezone_str="UTC")

        async def noop() -> None:
            pass

        scheduler.add_market_session_job("us_open", noop, market="us", event="open")
        next_run = scheduler.get_next_run("us_open")

        et = ZoneInfo("America/New_York")
        local = next_run.astimezone(et)
        assert local.hour == 9
        assert local.minute == 30
        assert local.weekday() in (0, 1, 2, 3, 4)

    def test_invalid_market_raises(self) -> None:
        scheduler = Scheduler()

        async def noop() -> None:
            pass

        with pytest.raises(ValueError, match="Unknown market"):
            scheduler.add_market_session_job("mars", noop, market="mars", event="open")

    def test_invalid_event_raises(self) -> None:
        scheduler = Scheduler()

        async def noop() -> None:
            pass

        with pytest.raises(ValueError, match="event must be"):
            scheduler.add_market_session_job("x", noop, market="us", event="lunch")


class TestSchedulerStartStop:
    """Tests for scheduler lifecycle."""

    def test_stop_sets_flag(self) -> None:
        scheduler = Scheduler()
        scheduler._running = True
        scheduler.stop()
        assert scheduler._running is False
