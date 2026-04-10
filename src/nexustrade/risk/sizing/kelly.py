"""Kelly criterion position sizing model."""

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


class KellyCriterionModel(RiskModelInterface):
    """Position sizing using the Kelly criterion.

    Optimal fraction = (win_prob * win_size - loss_prob * loss_size) / win_size.
    Uses signal confidence as a proxy for win probability.
    """

    @property
    def name(self) -> str:
        return "kelly"

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
        max_kelly_fraction = config.get("max_kelly_fraction", 0.25)
        half_kelly = config.get("half_kelly", True)
        atr_stop_multiple = config.get("atr_stop_multiple", 2.0)
        atr_tp_multiple = config.get("atr_tp_multiple", 3.0)
        max_position_pct = config.get("max_position_pct", 0.20)

        # Win probability from signal confidence
        win_prob = signal.confidence
        loss_prob = 1.0 - win_prob

        # Expected win/loss sizes from ATR
        win_size = atr * atr_tp_multiple
        loss_size = atr * atr_stop_multiple

        # Kelly fraction: f* = (p*b - q) / b  where b = win_size/loss_size
        if win_size <= 0 or loss_size <= 0:
            return self._rejected(signal.symbol, current_price, "Invalid ATR data")

        b = win_size / loss_size  # odds ratio
        kelly_fraction = (win_prob * b - loss_prob) / b

        # Clamp to max
        kelly_fraction = max(0.0, min(kelly_fraction, max_kelly_fraction))

        # Half-Kelly for safety
        if half_kelly:
            kelly_fraction *= 0.5

        if kelly_fraction <= 0:
            return self._rejected(
                signal.symbol, current_price, "Kelly fraction <= 0; edge is negative"
            )

        # Position size in dollars
        position_value = portfolio.total_value * kelly_fraction
        position_value = min(position_value, portfolio.total_value * max_position_pct)
        position_size = math.floor(position_value / current_price) if current_price > 0 else 0

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
            metadata={"kelly_fraction": kelly_fraction},
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
