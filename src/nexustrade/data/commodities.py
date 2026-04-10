"""Commodities support: futures symbol resolution and rollover management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class FuturesContract:
    symbol: str
    underlying: str
    expiry: datetime
    exchange: str
    multiplier: float
    tick_size: float
    metadata: dict = field(default_factory=dict)


class CommoditySymbolResolver:
    """Resolves common commodity names to futures symbols."""

    COMMODITY_MAP: dict[str, str] = {
        "gold": "GC",
        "crude": "CL",
        "silver": "SI",
        "natural_gas": "NG",
        "corn": "ZC",
        "wheat": "ZW",
        "soybeans": "ZS",
        "copper": "HG",
        "platinum": "PL",
        "palladium": "PA",
    }

    MONTH_CODES: dict[int, str] = {
        1: "F",
        2: "G",
        3: "H",
        4: "J",
        5: "K",
        6: "M",
        7: "N",
        8: "Q",
        9: "U",
        10: "V",
        11: "X",
        12: "Z",
    }

    def resolve(self, symbol: str) -> str:
        """Resolve a common commodity name to its futures root symbol.

        Args:
            symbol: Common name (e.g. "gold") or already a root symbol (e.g. "GC").

        Returns:
            Futures root symbol (e.g. "GC").
        """
        key = symbol.lower().strip()
        return self.COMMODITY_MAP.get(key, symbol.upper())

    def get_front_month(self, root: str, reference_date: datetime) -> str:
        """Return the front-month contract symbol.

        Uses the current month if reference_date is before the 15th,
        otherwise rolls to the next month.

        Args:
            root: Futures root symbol (e.g. "GC").
            reference_date: Date to compute the front month from.

        Returns:
            Contract symbol like "GCZ24".
        """
        # If past the 15th of the month, roll to next month
        if reference_date.day > 15:
            # Move to next month
            if reference_date.month == 12:
                month = 1
                year = reference_date.year + 1
            else:
                month = reference_date.month + 1
                year = reference_date.year
        else:
            month = reference_date.month
            year = reference_date.year

        month_code = self.MONTH_CODES[month]
        year_suffix = str(year % 100).zfill(2)
        return f"{root}{month_code}{year_suffix}"

    def get_continuous(self, root: str) -> str:
        """Return the continuous contract symbol in Yahoo Finance format.

        Args:
            root: Futures root symbol (e.g. "GC").

        Returns:
            Continuous symbol like "GC=F".
        """
        return f"{root}=F"


class RolloverManager:
    """Manages futures contract rollovers."""

    def should_roll(self, contract: FuturesContract, days_before_expiry: int = 5) -> bool:
        """Check whether a contract should be rolled to the next expiry.

        Args:
            contract: The current futures contract.
            days_before_expiry: Number of days before expiry to trigger a roll.

        Returns:
            True if the contract should be rolled.
        """
        now = datetime.now(contract.expiry.tzinfo)
        days_remaining = (contract.expiry - now).days
        return days_remaining <= days_before_expiry

    def get_next_contract(self, contract: FuturesContract) -> FuturesContract:
        """Compute the next contract after the given one.

        Moves the expiry forward by roughly one month and updates the symbol
        using the standard month-code convention.

        Args:
            contract: The current futures contract.

        Returns:
            A new FuturesContract with the next expiry.
        """
        resolver = CommoditySymbolResolver()

        # Advance expiry by ~1 month
        exp = contract.expiry
        if exp.month == 12:
            next_month = 1
            next_year = exp.year + 1
        else:
            next_month = exp.month + 1
            next_year = exp.year

        next_expiry = exp.replace(year=next_year, month=next_month)

        month_code = resolver.MONTH_CODES[next_month]
        year_suffix = str(next_year % 100).zfill(2)
        next_symbol = f"{contract.underlying}{month_code}{year_suffix}"

        return FuturesContract(
            symbol=next_symbol,
            underlying=contract.underlying,
            expiry=next_expiry,
            exchange=contract.exchange,
            multiplier=contract.multiplier,
            tick_size=contract.tick_size,
            metadata=dict(contract.metadata),
        )
