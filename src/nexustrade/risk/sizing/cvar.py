"""Conditional Value-at-Risk (CVaR) position sizing model."""

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


class CVaRModel(RiskModelInterface):
    """Size positions so max loss at a given confidence level
    doesn't exceed max_loss_pct * portfolio_value.
    """

    @property
    def name(self) -> str:
        return "cvar"

    async def calculate_position_size(
        self,
        portfolio: PortfolioState,
        signal: CompositeSignal,
        market_data: dict[str, Any],
        config: dict[str, Any],
    ) -> RiskAssessment:
        current_price = market_data.get("current_price", 0.0)
        atr = market_data.get("atr", current_price * 0.02)
        daily_volatility = market_data.get(
            "daily_volatility",
            atr / current_price if current_price > 0 else 0.02,
        )

        # Config
        confidence_level = config.get("confidence_level", 0.95)
        max_loss_pct = config.get("max_loss_pct", 0.02)
        atr_stop_multiple = config.get("atr_stop_multiple", 2.0)
        atr_tp_multiple = config.get("atr_tp_multiple", 3.0)
        max_position_pct = config.get("max_position_pct", 0.20)

        if current_price <= 0 or daily_volatility <= 0:
            return self._rejected(signal.symbol, current_price, "Invalid price or volatility data")

        # CVaR multiplier (approximate for normal distribution)
        # At 95% confidence, z ~ 1.645; CVaR multiplier ~ 2.06
        # At 99% confidence, z ~ 2.326; CVaR multiplier ~ 2.67
        z_scores = {0.90: 1.28, 0.95: 1.645, 0.99: 2.326}
        z = z_scores.get(confidence_level, 1.645)
        # CVaR for normal: E[X | X > VaR] ~ z * 1.25 (approximation)
        cvar_multiplier = z * 1.25

        # Max dollar loss allowed
        max_loss_dollars = portfolio.total_value * max_loss_pct

        # Expected loss per share at CVaR level
        cvar_loss_per_share = current_price * daily_volatility * cvar_multiplier

        if cvar_loss_per_share <= 0:
            return self._rejected(signal.symbol, current_price, "CVaR loss per share is zero")

        # Position size
        position_size = math.floor(max_loss_dollars / cvar_loss_per_share)
        position_value = position_size * current_price
        max_value = portfolio.total_value * max_position_pct

        if position_value > max_value and current_price > 0:
            position_size = math.floor(max_value / current_price)

        if position_size <= 0:
            return self._rejected(signal.symbol, current_price, "Position size rounds to 0")

        # Stop-loss / take-profit
        is_buy = signal.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
        if is_buy:
            stop_loss = current_price - atr * atr_stop_multiple
            take_profit = current_price + atr * atr_tp_multiple
        else:
            stop_loss = current_price + atr * atr_stop_multiple
            take_profit = current_price - atr * atr_tp_multiple

        risk_per_share = abs(current_price - stop_loss)
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
                "cvar_multiplier": cvar_multiplier,
                "daily_volatility": daily_volatility,
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
