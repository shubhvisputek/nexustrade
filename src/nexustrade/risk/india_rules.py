"""India-specific risk rules for SEBI compliance."""

from __future__ import annotations

import logging
import time
from typing import Any

from nexustrade.core.models import Order

logger = logging.getLogger(__name__)


# Common F&O lot sizes (can be updated from exchange data)
DEFAULT_LOT_SIZES: dict[str, int] = {
    "NIFTY": 25,
    "BANKNIFTY": 15,
    "FINNIFTY": 25,
    "MIDCPNIFTY": 50,
    "RELIANCE": 250,
    "TCS": 150,
    "INFY": 300,
    "HDFCBANK": 550,
    "ICICIBANK": 700,
    "SBIN": 750,
}


class IndiaRiskRules:
    """India market risk rules: circuit limits, F&O lot sizes, rate limiting, SEBI audit."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.lot_sizes: dict[str, int] = config.get("lot_sizes", DEFAULT_LOT_SIZES)
        self.circuit_limits: dict[str, tuple[float, float]] = config.get("circuit_limits", {})
        # Rate limiting per broker
        self.rate_limit_per_second: float = config.get("rate_limit_per_second", 10.0)
        self._last_request_times: list[float] = []
        self._audit_log: list[dict[str, Any]] = []

    def validate_order(
        self, order: Order, market_data: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Validate an order against India-specific rules.

        Returns (approved, warnings).
        """
        warnings: list[str] = []
        approved = True

        # Circuit limit checking
        circuit_ok, circuit_msg = self.check_circuit_limits(
            order.symbol, market_data.get("current_price", 0.0), market_data
        )
        if not circuit_ok:
            warnings.append(circuit_msg or "Circuit limit breached")
            approved = False

        # F&O lot size validation
        if market_data.get("is_fno", False):
            lot_ok, lot_msg = self.validate_lot_size(order.symbol, order.quantity)
            if not lot_ok:
                warnings.append(lot_msg or "Invalid lot size")
                approved = False

        return approved, warnings

    def check_circuit_limits(
        self, symbol: str, current_price: float, market_data: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Check if the current price is within circuit limits.

        Returns (within_limits, reason if breached).
        """
        if symbol in self.circuit_limits:
            lower, upper = self.circuit_limits[symbol]
            if current_price <= lower:
                return False, f"{symbol} at lower circuit limit ({current_price} <= {lower})"
            if current_price >= upper:
                return False, f"{symbol} at upper circuit limit ({current_price} >= {upper})"

        # Check from market_data if circuit info is provided
        lower = market_data.get("circuit_lower")
        upper = market_data.get("circuit_upper")
        if lower is not None and current_price <= lower:
            return False, f"{symbol} at lower circuit ({current_price} <= {lower})"
        if upper is not None and current_price >= upper:
            return False, f"{symbol} at upper circuit ({current_price} >= {upper})"

        return True, None

    def validate_lot_size(self, symbol: str, quantity: float) -> tuple[bool, str | None]:
        """Validate F&O quantity is a multiple of the lot size.

        Returns (valid, reason if invalid).
        """
        lot_size = self.lot_sizes.get(symbol)
        if lot_size is None:
            # Unknown lot size -- allow but warn
            return True, None

        if quantity <= 0:
            return False, f"Quantity must be positive, got {quantity}"

        if quantity % lot_size != 0:
            return False, (
                f"{symbol} F&O quantity {quantity} is not a multiple of lot size {lot_size}"
            )

        return True, None

    def check_rate_limit(self) -> tuple[bool, str | None]:
        """Check if we're within the API rate limit.

        Returns (allowed, reason if blocked).
        """
        now = time.monotonic()
        # Remove timestamps older than 1 second
        window = 1.0
        self._last_request_times = [
            t for t in self._last_request_times if now - t < window
        ]

        if len(self._last_request_times) >= self.rate_limit_per_second:
            return False, f"Rate limit exceeded ({self.rate_limit_per_second}/s)"

        self._last_request_times.append(now)
        return True, None

    def log_audit_trail(self, trade_details: dict[str, Any]) -> None:
        """Log trade details for SEBI audit trail compliance."""
        entry = {
            "timestamp": time.time(),
            **trade_details,
        }
        self._audit_log.append(entry)
        logger.info("SEBI audit trail: %s", entry)

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return the audit trail."""
        return list(self._audit_log)
