"""Risk engine: orchestrates pre-trade, debate, sizing, and circuit breaker."""

from __future__ import annotations

from typing import Any

from nexustrade.core.interfaces import RiskModelInterface
from nexustrade.core.models import (
    CompositeSignal,
    PortfolioState,
    RiskAssessment,
)
from nexustrade.risk.circuit_breaker import CircuitBreaker
from nexustrade.risk.debate import RiskDebate
from nexustrade.risk.pre_trade import PreTradeValidator
from nexustrade.risk.sizing.fixed_fraction import FixedFractionModel


class RiskEngine:
    """Orchestrates the full risk pipeline.

    Flow: circuit breaker check -> risk debate -> position sizing -> pre-trade validation.
    """

    def __init__(
        self,
        sizing_model: RiskModelInterface | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        debate: RiskDebate | None = None,
        pre_trade: PreTradeValidator | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.config = config or {}
        self.sizing_model = sizing_model or FixedFractionModel()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(self.config)
        self.debate = debate or RiskDebate()
        self.pre_trade = pre_trade or PreTradeValidator(self.config)

    async def assess(
        self,
        composite_signal: CompositeSignal,
        portfolio: PortfolioState,
        market_data: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> RiskAssessment:
        """Run the full risk assessment pipeline.

        Parameters
        ----------
        composite_signal:
            Aggregated signal from agents.
        portfolio:
            Current portfolio state.
        market_data:
            Market data including current_price, atr, etc.
        config:
            Optional override config for this assessment.

        Returns
        -------
        RiskAssessment
            Final assessment with position size, stops, and approval status.
        """
        cfg = {**self.config, **(config or {})}
        current_price = market_data.get("current_price", 0.0)

        # 1. Circuit breaker check
        can_trade, cb_reason = self.circuit_breaker.check(portfolio)
        if not can_trade:
            return RiskAssessment(
                symbol=composite_signal.symbol,
                approved=False,
                position_size=0.0,
                stop_loss_price=current_price,
                take_profit_price=current_price,
                risk_reward_ratio=0.0,
                max_loss_amount=0.0,
                sizing_model=self.sizing_model.name,
                warnings=[f"Circuit breaker: {cb_reason}"],
            )

        # 2. Risk debate (advisory)
        debate_assessment = await self.debate.debate(
            composite_signal, portfolio, market_data, cfg
        )

        # 3. Position sizing
        sizing_assessment = await self.sizing_model.calculate_position_size(
            portfolio, composite_signal, market_data, cfg
        )

        if not sizing_assessment.approved:
            sizing_assessment.risk_debate_summary = debate_assessment.risk_debate_summary
            return sizing_assessment

        # Merge debate summary into sizing result
        sizing_assessment.risk_debate_summary = debate_assessment.risk_debate_summary

        # If debate rejected, add warning but don't override sizing approval
        # unless config says to respect debate
        if not debate_assessment.approved and cfg.get("respect_debate", False):
            sizing_assessment.approved = False
            sizing_assessment.warnings.append("Risk debate rejected the trade")

        # Add any debate warnings
        if debate_assessment.warnings:
            sizing_assessment.warnings.extend(debate_assessment.warnings)

        return sizing_assessment
