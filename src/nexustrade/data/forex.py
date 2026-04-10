"""Forex-specific utilities -- pip calculation and session detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class ForexSession(str, Enum):
    ASIAN = "asian"  # Tokyo: 00:00-09:00 UTC
    LONDON = "london"  # 08:00-17:00 UTC
    NEW_YORK = "new_york"  # 13:00-22:00 UTC
    SYDNEY = "sydney"  # 21:00-06:00 UTC (next day)
    OVERLAP_LONDON_NY = "overlap_london_ny"  # 13:00-17:00 UTC


@dataclass
class ForexPipInfo:
    pair: str
    pip_size: float  # 0.0001 for most, 0.01 for JPY
    pip_value_usd: float  # approx USD value per pip per standard lot


# Major pairs (tight spreads, 1-2 pips)
_MAJOR_PAIRS = frozenset({
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "NZD/USD", "USD/CAD",
})

# Minor / cross pairs (moderate spreads, 3-5 pips)
_MINOR_PAIRS = frozenset({
    "EUR/GBP", "EUR/AUD", "EUR/CAD", "EUR/CHF", "EUR/NZD",
    "GBP/AUD", "GBP/CAD", "GBP/CHF", "GBP/NZD",
    "AUD/CAD", "AUD/CHF", "AUD/NZD",
    "CAD/CHF", "NZD/CAD", "NZD/CHF",
    "GBP/JPY", "EUR/JPY", "AUD/JPY", "NZD/JPY", "CAD/JPY", "CHF/JPY",
})

# JPY-quoted currencies use 0.01 pip size
_JPY_CURRENCIES = frozenset({"JPY"})


def _normalize_pair(pair: str) -> str:
    """Normalize pair string: strip whitespace and uppercase."""
    return pair.strip().upper().replace("_", "/")


def _is_jpy_pair(pair: str) -> bool:
    """Return True if the pair is JPY-quoted."""
    normalized = _normalize_pair(pair)
    parts = normalized.split("/")
    return len(parts) == 2 and parts[1] in _JPY_CURRENCIES


def calculate_pip_size(pair: str) -> float:
    """Return pip size: 0.01 for JPY pairs, 0.0001 for others."""
    if _is_jpy_pair(pair):
        return 0.01
    return 0.0001


def calculate_pips(pair: str, entry_price: float, exit_price: float) -> float:
    """Calculate pips between two prices.

    Returns positive pips if exit > entry, negative otherwise.
    """
    pip_size = calculate_pip_size(pair)
    return (exit_price - entry_price) / pip_size


def get_pip_info(pair: str, price: float | None = None) -> ForexPipInfo:
    """Return pip info for a pair. Approximate USD value per standard lot."""
    normalized = _normalize_pair(pair)
    pip_size = calculate_pip_size(normalized)

    # Approximate pip value in USD for a standard lot (100,000 units)
    # For USD-quoted pairs (e.g. EUR/USD): pip_value = 100000 * pip_size
    # For JPY pairs or non-USD quoted: rough approximation
    parts = normalized.split("/")
    if len(parts) == 2 and parts[1] == "USD":
        pip_value_usd = 100_000 * pip_size  # $10 per pip
    elif len(parts) == 2 and parts[0] == "USD":
        # USD is base; pip value depends on current rate
        if price and price > 0:
            pip_value_usd = (100_000 * pip_size) / price
        else:
            pip_value_usd = 10.0  # rough default
    else:
        pip_value_usd = 10.0  # rough approximation for crosses

    return ForexPipInfo(pair=normalized, pip_size=pip_size, pip_value_usd=pip_value_usd)


def get_current_session(utc_time: datetime | None = None) -> list[ForexSession]:
    """Return list of active forex sessions at the given UTC time.

    Session hours (UTC):
      - Sydney:  21:00 - 06:00 (next day, wraps midnight)
      - Asian:   00:00 - 09:00
      - London:  08:00 - 17:00
      - New York: 13:00 - 22:00
      - Overlap London-NY: 13:00 - 17:00 (subset)
    """
    if utc_time is None:
        utc_time = datetime.now(timezone.utc)

    hour = utc_time.hour
    sessions: list[ForexSession] = []

    # Sydney: 21:00 - 06:00 UTC (wraps midnight)
    if hour >= 21 or hour < 6:
        sessions.append(ForexSession.SYDNEY)

    # Asian (Tokyo): 00:00 - 09:00 UTC
    if 0 <= hour < 9:
        sessions.append(ForexSession.ASIAN)

    # London: 08:00 - 17:00 UTC
    if 8 <= hour < 17:
        sessions.append(ForexSession.LONDON)

    # New York: 13:00 - 22:00 UTC
    if 13 <= hour < 22:
        sessions.append(ForexSession.NEW_YORK)

    # Overlap London-NY: 13:00 - 17:00 UTC
    if 13 <= hour < 17:
        sessions.append(ForexSession.OVERLAP_LONDON_NY)

    return sessions


def is_high_liquidity(utc_time: datetime | None = None) -> bool:
    """True during London-NY overlap (best liquidity)."""
    sessions = get_current_session(utc_time)
    return ForexSession.OVERLAP_LONDON_NY in sessions


def get_spread_threshold(pair: str) -> float:
    """Return typical spread threshold in pips for major/minor/exotic pairs.

    Returns
    -------
    float
        Spread threshold in pips:
        - Majors: 2.0 pips
        - Minors: 5.0 pips
        - Exotics: 15.0 pips
    """
    normalized = _normalize_pair(pair)
    if normalized in _MAJOR_PAIRS:
        return 2.0
    if normalized in _MINOR_PAIRS:
        return 5.0
    # Exotic or unknown
    return 15.0
