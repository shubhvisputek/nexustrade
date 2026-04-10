"""Max drawdown position sizing model."""

from __future__ import annotations

import math
from typing import Any

from nexustrade.core.interfaces import RiskModelInterface
from nexustrade.core.models import (
    CompositeSignal,
    PortfolioState,
    RiskAssessment,
    SignalDirection,
)


class MaxDrawdownModel(RiskModelInterface):
    """Limit position size to prevent exceeding a max drawdown threshold.

    The model scales position size so that a worst-case loss (stop-loss hit)
    does not push the portfolio drawdown beyond the configured threshold.
    """

    @property
    def name(self) -> str:
        return "max_drawdown"

    async def calculate_position_size(
        self,
        portfolio: PortfolioState,
        signal: CompositeSignal,
        market_data: dict[str, Any],
        config: dict[str, Any],
    ) -> RiskAssessment:
        current_price = market_data.get("current_price", 0.0)
        atr = market_data.get("atr", current_price * 0.02)

        # Config
        max_drawdown_pct = config.get("max_drawdown_pct", 0.10)  # 10% max drawdown
        atr_stop_multiple = config.get("atr_stop_multiple", 2.0)
        atr_tp_multiple = config.get("atr_tp_multiple", 3.0)
        max_position_pct = config.get("max_position_pct", 0.20)

        if current_price <= 0:
            return self._rejected(signal.symbol, current_price, "Invalid price")

        # Current drawdown: how much have we already lost?
        # daily_pnl negative = we're in drawdown territory
        current_drawdown_pct = (
            abs(min(0.0, portfolio.daily_pnl)) / portfolio.total_value
            if portfolio.total_value > 0
            else 0.0
        )
        remaining_drawdown_budget = max(0.0, max_drawdown_pct - current_drawdown_pct)

        if remaining_drawdown_budget <= 0:
            return self._rejected(
                signal.symbol, current_price,
                f"Drawdown budget exhausted ({current_drawdown_pct:.1%} >= {max_drawdown_pct:.1%})"
            )

        is_buy = signal.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
        risk_per_share = atr * atr_stop_multiple

        if risk_per_share <= 0:
            return self._rejected(signal.symbol, current_price, "Risk per share is zero")

        # Max loss allowed from remaining budget
        max_loss_dollars = portfolio.total_value * remaining_drawdown_budget
        position_size = math.floor(max_loss_dollars / risk_per_share)

        # Cap
        max_value = portfolio.total_value * max_position_pct
        if position_size * current_price > max_value:
            position_size = math.floor(max_value / current_price)

        if position_size <= 0:
            return self._rejected(signal.symbol, current_price, "Position size rounds to 0")

        if is_buy:
            stop_loss = current_price - risk_per_share
            take_profit = current_price + atr * atr_tp_multiple
        else:
            stop_loss = current_price + risk_per_share
            take_profit = current_price - atr * atr_tp_multiple

        reward_per_share = abs(take_profit - current_price)
        rr_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0
        max_loss = risk_per_share * position_size

        return RiskAssessment(
            symbol=signal.symbol,
            approved=True,
            position_size=float(position_size),
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            risk_reward_ratio=rr_ratio,
            max_loss_amount=max_loss,
            sizing_model=self.name,
            warnings=[],
            metadata={
                "current_drawdown_pct": current_drawdown_pct,
                "remaining_drawdown_budget": remaining_drawdown_budget,
            },
        )

    def _rejected(self, symbol: str, price: float, reason: str) -> RiskAssessment:
        return RiskAssessment(
            symbol=symbol,
            approved=False,
            position_size=0.0,
            stop_loss_price=price,
            take_profit_price=price,
            risk_reward_ratio=0.0,
            max_loss_amount=0.0,
            sizing_model=self.name,
            warnings=[reason],
        )
