"""Unit tests for forex utilities."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nexustrade.data.forex import (
    ForexSession,
    calculate_pip_size,
    calculate_pips,
    get_current_session,
    get_pip_info,
    get_spread_threshold,
    is_high_liquidity,
)


@pytest.mark.unit
class TestPipCalculation:
    """Tests for pip size and pip calculation."""

    def test_pip_size_eurusd(self) -> None:
        assert calculate_pip_size("EUR/USD") == 0.0001

    def test_pip_size_gbpusd(self) -> None:
        assert calculate_pip_size("GBP/USD") == 0.0001

    def test_pip_size_usdjpy(self) -> None:
        assert calculate_pip_size("USD/JPY") == 0.01

    def test_pip_size_eurjpy(self) -> None:
        assert calculate_pip_size("EUR/JPY") == 0.01

    def test_pip_size_case_insensitive(self) -> None:
        assert calculate_pip_size("eur/usd") == 0.0001
        assert calculate_pip_size("usd/jpy") == 0.01

    def test_pip_size_underscore_separator(self) -> None:
        assert calculate_pip_size("EUR_USD") == 0.0001
        assert calculate_pip_size("USD_JPY") == 0.01

    def test_calculate_pips_eurusd_positive(self) -> None:
        pips = calculate_pips("EUR/USD", 1.1000, 1.1050)
        assert pips == pytest.approx(50.0)

    def test_calculate_pips_eurusd_negative(self) -> None:
        pips = calculate_pips("EUR/USD", 1.1050, 1.1000)
        assert pips == pytest.approx(-50.0)

    def test_calculate_pips_usdjpy_positive(self) -> None:
        pips = calculate_pips("USD/JPY", 150.00, 150.50)
        assert pips == pytest.approx(50.0)

    def test_calculate_pips_usdjpy_negative(self) -> None:
        pips = calculate_pips("USD/JPY", 150.50, 150.00)
        assert pips == pytest.approx(-50.0)

    def test_calculate_pips_zero(self) -> None:
        pips = calculate_pips("EUR/USD", 1.1000, 1.1000)
        assert pips == pytest.approx(0.0)


@pytest.mark.unit
class TestPipInfo:
    """Tests for pip info helper."""

    def test_pip_info_usd_quoted(self) -> None:
        info = get_pip_info("EUR/USD")
        assert info.pip_size == 0.0001
        assert info.pip_value_usd == pytest.approx(10.0)

    def test_pip_info_usd_base(self) -> None:
        info = get_pip_info("USD/JPY", price=150.0)
        assert info.pip_size == 0.01
        # pip_value = 100000 * 0.01 / 150 ~ 6.67
        assert info.pip_value_usd == pytest.approx(6.6667, rel=0.01)

    def test_pip_info_cross(self) -> None:
        info = get_pip_info("EUR/GBP")
        assert info.pip_size == 0.0001
        # Cross pairs get default ~10.0
        assert info.pip_value_usd == pytest.approx(10.0)


@pytest.mark.unit
class TestSessionDetection:
    """Tests for forex session detection."""

    def test_asian_session(self) -> None:
        # 03:00 UTC -> Asian + Sydney
        t = datetime(2025, 1, 15, 3, 0, tzinfo=timezone.utc)
        sessions = get_current_session(t)
        assert ForexSession.ASIAN in sessions
        assert ForexSession.SYDNEY in sessions
        assert ForexSession.LONDON not in sessions
        assert ForexSession.NEW_YORK not in sessions

    def test_london_session(self) -> None:
        # 10:00 UTC -> London only
        t = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        sessions = get_current_session(t)
        assert ForexSession.LONDON in sessions
        assert ForexSession.ASIAN not in sessions
        assert ForexSession.NEW_YORK not in sessions

    def test_new_york_session(self) -> None:
        # 18:00 UTC -> New York only
        t = datetime(2025, 1, 15, 18, 0, tzinfo=timezone.utc)
        sessions = get_current_session(t)
        assert ForexSession.NEW_YORK in sessions
        assert ForexSession.LONDON not in sessions

    def test_london_ny_overlap(self) -> None:
        # 14:00 UTC -> London + New York + Overlap
        t = datetime(2025, 1, 15, 14, 0, tzinfo=timezone.utc)
        sessions = get_current_session(t)
        assert ForexSession.LONDON in sessions
        assert ForexSession.NEW_YORK in sessions
        assert ForexSession.OVERLAP_LONDON_NY in sessions

    def test_sydney_session_late_night(self) -> None:
        # 22:00 UTC -> Sydney + New York
        t = datetime(2025, 1, 15, 22, 0, tzinfo=timezone.utc)
        sessions = get_current_session(t)
        assert ForexSession.SYDNEY in sessions

    def test_sydney_session_early_morning(self) -> None:
        # 04:00 UTC -> Sydney + Asian
        t = datetime(2025, 1, 15, 4, 0, tzinfo=timezone.utc)
        sessions = get_current_session(t)
        assert ForexSession.SYDNEY in sessions
        assert ForexSession.ASIAN in sessions

    def test_no_session_boundary(self) -> None:
        # 09:00 UTC -> end of Asian, not quite London overlap start
        # Asian: 0-9 (exclusive), London: 8-17
        # At hour 9: Asian ended, London active
        t = datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc)
        sessions = get_current_session(t)
        assert ForexSession.ASIAN not in sessions
        assert ForexSession.LONDON in sessions

    def test_default_uses_current_time(self) -> None:
        # Should not raise
        sessions = get_current_session()
        assert isinstance(sessions, list)


@pytest.mark.unit
class TestHighLiquidity:
    """Tests for is_high_liquidity."""

    def test_high_liquidity_during_overlap(self) -> None:
        t = datetime(2025, 1, 15, 15, 0, tzinfo=timezone.utc)
        assert is_high_liquidity(t) is True

    def test_no_high_liquidity_outside_overlap(self) -> None:
        t = datetime(2025, 1, 15, 3, 0, tzinfo=timezone.utc)
        assert is_high_liquidity(t) is False

    def test_no_high_liquidity_after_london_close(self) -> None:
        t = datetime(2025, 1, 15, 18, 0, tzinfo=timezone.utc)
        assert is_high_liquidity(t) is False


@pytest.mark.unit
class TestSpreadThreshold:
    """Tests for spread thresholds."""

    def test_major_pair_eurusd(self) -> None:
        assert get_spread_threshold("EUR/USD") == 2.0

    def test_major_pair_usdjpy(self) -> None:
        assert get_spread_threshold("USD/JPY") == 2.0

    def test_major_pair_gbpusd(self) -> None:
        assert get_spread_threshold("GBP/USD") == 2.0

    def test_minor_pair_eurgbp(self) -> None:
        assert get_spread_threshold("EUR/GBP") == 5.0

    def test_minor_pair_gbpjpy(self) -> None:
        assert get_spread_threshold("GBP/JPY") == 5.0

    def test_exotic_pair(self) -> None:
        assert get_spread_threshold("USD/TRY") == 15.0

    def test_unknown_pair(self) -> None:
        assert get_spread_threshold("XYZ/ABC") == 15.0

    def test_case_insensitive(self) -> None:
        assert get_spread_threshold("eur/usd") == 2.0
