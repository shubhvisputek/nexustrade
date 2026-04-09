"""Circuit breaker for trading risk management."""

from __future__ import annotations

import time
from typing import Any

from nexustrade.core.models import Fill, OrderSide, OrderStatus, PortfolioState


class CircuitBreaker:
    """Tracks daily P&L, consecutive losses, and open positions.

    When thresholds are breached, trading is halted until cooldown expires
    or a manual reset is performed.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.max_daily_loss_pct: float = config.get("max_daily_loss_pct", 0.03)
        self.max_consecutive_losses: int = config.get("max_consecutive_losses", 5)
        self.max_open_positions: int = config.get("max_open_positions", 10)
        self.cooldown_minutes: float = config.get("cooldown_minutes", 30.0)

        # Internal state
        self._consecutive_losses: int = 0
        self._daily_pnl: float = 0.0
        self._triggered: bool = False
        self._trigger_reason: str | None = None
        self._trigger_time: float | None = None
        self._fills: list[Fill] = []

    @property
    def is_triggered(self) -> bool:
        """Whether the circuit breaker is currently active."""
        if self._triggered and self._trigger_time is not None:
            elapsed = time.monotonic() - self._trigger_time
            if elapsed >= self.cooldown_minutes * 60:
                # Cooldown expired, auto-reset
                self._triggered = False
                self._trigger_reason = None
                self._trigger_time = None
        return self._triggered

    def check(self, portfolio: PortfolioState) -> tuple[bool, str | None]:
        """Check whether trading should be allowed.

        Returns
        -------
        tuple[bool, str | None]
            (can_trade, reason if blocked)
        """
        # Check cooldown
        if self.is_triggered:
            return False, self._trigger_reason

        # Check daily loss
        if portfolio.total_value > 0:
            daily_loss_pct = abs(min(0.0, portfolio.daily_pnl)) / portfolio.total_value
            if daily_loss_pct >= self.max_daily_loss_pct:
                self._trigger(
                    f"Daily loss {daily_loss_pct:.1%} exceeds max {self.max_daily_loss_pct:.1%}"
                )
                return False, self._trigger_reason

        # Check consecutive losses
        if self._consecutive_losses >= self.max_consecutive_losses:
            self._trigger(
                f"Consecutive losses ({self._consecutive_losses}) reached max ({self.max_consecutive_losses})"
            )
            return False, self._trigger_reason

        # Check open positions
        if len(portfolio.positions) > self.max_open_positions:
            return False, f"Too many open positions ({len(portfolio.positions)} > {self.max_open_positions})"

        return True, None

    def update(self, fill: Fill) -> None:
        """Update state with a new fill.

        Tracks consecutive losses and daily P&L from fill results.
        """
        self._fills.append(fill)

        if fill.status != OrderStatus.FILLED:
            return

        # Compute realized P&L from the fill's metadata or slippage
        pnl = fill.metadata.get("realized_pnl", 0.0)

        self._daily_pnl += pnl

        if pnl < 0:
            self._consecutive_losses += 1
        elif pnl > 0:
            self._consecutive_losses = 0
        # pnl == 0: no change to consecutive losses

    def reset(self) -> None:
        """Manual override to reset the circuit breaker."""
        self._triggered = False
        self._trigger_reason = None
        self._trigger_time = None
        self._consecutive_losses = 0
        self._daily_pnl = 0.0

    def _trigger(self, reason: str) -> None:
        """Activate the circuit breaker."""
        self._triggered = True
        self._trigger_reason = reason
        self._trigger_time = time.monotonic()
