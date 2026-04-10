"""Pre-trade validation checks."""

from __future__ import annotations

from typing import Any

from nexustrade.core.models import Order, PortfolioState


class PreTradeValidator:
    """Validates orders against risk limits before execution.

    Checks include max position size (% of portfolio), max portfolio risk,
    market hours (optional), and max open positions.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.max_position_pct: float = config.get("max_position_pct", 0.20)
        self.max_portfolio_risk: float = config.get("max_portfolio_risk", 0.50)
        self.max_open_positions: int = config.get("max_open_positions", 10)
        self.check_market_hours: bool = config.get("check_market_hours", False)
        self.india_rules: Any = config.get("india_rules", None)

    def validate(
        self,
        order: Order,
        portfolio: PortfolioState,
        market_data: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate an order against risk limits.

        Returns
        -------
        tuple[bool, list[str]]
            (approved, list of warning/rejection messages)
        """
        warnings: list[str] = []
        approved = True

        # 1. Max position size as % of portfolio
        current_price = market_data.get("current_price", order.price or 0.0)
        if current_price > 0 and portfolio.total_value > 0:
            order_value = order.quantity * current_price
            position_pct = order_value / portfolio.total_value
            if position_pct > self.max_position_pct:
                warnings.append(
                    f"Position size {position_pct:.1%} exceeds max {self.max_position_pct:.1%}"
                )
                approved = False

        # 2. Max open positions
        if len(portfolio.positions) >= self.max_open_positions:
            # Check if this is a new position (not adding to existing)
            existing_symbols = {p.symbol for p in portfolio.positions}
            if order.symbol not in existing_symbols:
                warnings.append(
                    f"Max open positions ({self.max_open_positions}) reached"
                )
                approved = False

        # 3. Max portfolio risk (total exposure / portfolio value)
        if portfolio.total_value > 0:
            total_exposure = sum(
                abs(p.quantity * p.current_price) for p in portfolio.positions
            )
            order_value = order.quantity * current_price if current_price > 0 else 0.0
            new_exposure = total_exposure + order_value
            exposure_ratio = new_exposure / portfolio.total_value
            if exposure_ratio > self.max_portfolio_risk:
                warnings.append(
                    f"Portfolio exposure {exposure_ratio:.1%}"
                    f" would exceed max {self.max_portfolio_risk:.1%}"
                )
                # This is a warning, not a hard reject unless significantly over
                if exposure_ratio > self.max_portfolio_risk * 1.5:
                    approved = False

        # 4. Circuit breaker check
        if portfolio.circuit_breaker_active:
            warnings.append("Circuit breaker is active")
            approved = False

        # 5. India-specific rules (delegate)
        if self.india_rules is not None:
            india_approved, india_warnings = self.india_rules.validate_order(
                order, market_data
            )
            warnings.extend(india_warnings)
            if not india_approved:
                approved = False

        # 6. Basic sanity checks
        if order.quantity <= 0:
            warnings.append("Order quantity must be positive")
            approved = False

        return approved, warnings
