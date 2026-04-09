"""Fixed fractional position sizing model."""

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


class FixedFractionModel(RiskModelInterface):
    """Risk a fixed percentage of portfolio per trade.

    Position size = (portfolio_value * risk_pct) / (entry_price - stop_loss_price).
    """

    @property
    def name(self) -> str:
        return "fixed_fraction"

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
        risk_pct = config.get("risk_pct", 0.01)  # 1% of portfolio per trade
        atr_stop_multiple = config.get("atr_stop_multiple", 2.0)
        atr_tp_multiple = config.get("atr_tp_multiple", 3.0)
        max_position_pct = config.get("max_position_pct", 0.20)

        if current_price <= 0:
            return self._rejected(signal.symbol, current_price, "Invalid price")

        is_buy = signal.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)

        # Stop-loss / take-profit
        if is_buy:
            stop_loss = current_price - atr * atr_stop_multiple
            take_profit = current_price + atr * atr_tp_multiple
        else:
            stop_loss = current_price + atr * atr_stop_multiple
            take_profit = current_price - atr * atr_tp_multiple

        risk_per_share = abs(current_price - stop_loss)
        if risk_per_share <= 0:
            return self._rejected(signal.symbol, current_price, "Risk per share is zero")

        # Position size = risk_dollars / risk_per_share
        risk_dollars = portfolio.total_value * risk_pct
        position_size = math.floor(risk_dollars / risk_per_share)

        # Cap by max position %
        max_value = portfolio.total_value * max_position_pct
        if position_size * current_price > max_value:
            position_size = math.floor(max_value / current_price)

        if position_size <= 0:
            return self._rejected(signal.symbol, current_price, "Position size rounds to 0")

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
            metadata={"risk_pct": risk_pct, "risk_dollars": risk_dollars},
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
