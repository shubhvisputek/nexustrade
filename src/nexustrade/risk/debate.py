"""Risk debate module: 3-perspective risk assessment."""

from __future__ import annotations

from typing import Any

from nexustrade.core.models import (
    CompositeSignal,
    PortfolioState,
    RiskAssessment,
    SignalDirection,
)


class RiskDebate:
    """Generates a 3-perspective risk assessment (aggressive, conservative, neutral).

    Uses prompt_loader and llm_router when available; falls back to heuristic
    analysis when no LLM is configured.
    """

    def __init__(
        self,
        prompt_loader: Any | None = None,
        llm_router: Any | None = None,
    ) -> None:
        self.prompt_loader = prompt_loader
        self.llm_router = llm_router

    async def debate(
        self,
        signal: CompositeSignal,
        portfolio: PortfolioState,
        market_data: dict[str, Any],
        config: dict[str, Any],
    ) -> RiskAssessment:
        """Run the risk debate and synthesize into a RiskAssessment.

        If no LLM is available, returns a heuristic-based default assessment.
        """
        current_price = market_data.get("current_price", 0.0)
        atr = market_data.get("atr", current_price * 0.02)

        if self.llm_router is not None:
            return await self._llm_debate(signal, portfolio, market_data, config)

        # Heuristic fallback: synthesize from signal properties
        return self._heuristic_debate(signal, portfolio, current_price, atr, config)

    async def _llm_debate(
        self,
        signal: CompositeSignal,
        portfolio: PortfolioState,
        market_data: dict[str, Any],
        config: dict[str, Any],
    ) -> RiskAssessment:
        """Run debate using LLM for each perspective."""
        current_price = market_data.get("current_price", 0.0)
        atr = market_data.get("atr", current_price * 0.02)

        perspectives = ["aggressive", "conservative", "neutral"]
        responses: list[str] = []

        for perspective in perspectives:
            prompt = (
                f"As a {perspective} risk analyst, evaluate this trade signal:\n"
                f"Symbol: {signal.symbol}, Direction: {signal.direction.value}, "
                f"Confidence: {signal.confidence:.2f}\n"
                f"Portfolio value: ${portfolio.total_value:,.0f}, "
                f"Current price: ${current_price:.2f}, ATR: ${atr:.2f}\n"
                f"Daily P&L: ${portfolio.daily_pnl:,.0f}\n"
                f"Give your assessment: should we take this trade? "
                f"What position size and risk level?"
            )
            try:
                resp = await self.llm_router.complete(prompt, channel="fast")
                responses.append(f"[{perspective}] {resp}")
            except Exception:
                responses.append(f"[{perspective}] Unable to get assessment")

        summary = " | ".join(responses)

        # Use heuristic sizing even with LLM debate summary
        assessment = self._heuristic_debate(
            signal, portfolio, current_price, atr, config
        )
        assessment.risk_debate_summary = summary
        return assessment

    def _heuristic_debate(
        self,
        signal: CompositeSignal,
        portfolio: PortfolioState,
        current_price: float,
        atr: float,
        config: dict[str, Any],
    ) -> RiskAssessment:
        """Heuristic debate without LLM: uses signal confidence and portfolio state."""
        if current_price <= 0 or portfolio.total_value <= 0:
            return RiskAssessment(
                symbol=signal.symbol,
                approved=False,
                position_size=0.0,
                stop_loss_price=current_price,
                take_profit_price=current_price,
                risk_reward_ratio=0.0,
                max_loss_amount=0.0,
                sizing_model="debate",
                risk_debate_summary="Insufficient data for debate",
                warnings=["No valid price or portfolio data"],
            )

        # Perspective scores
        aggressive_score = signal.confidence  # High confidence = aggressive says go
        conservative_score = 1.0 - signal.confidence  # Low confidence = conservative says no

        # Neutral blends
        neutral_score = 0.5

        # Weighted synthesis (conservative has more weight for safety)
        weights = config.get("debate_weights", {
            "aggressive": 0.25, "conservative": 0.40, "neutral": 0.35,
        })
        final_score = (
            aggressive_score * weights.get("aggressive", 0.25)
            + (1.0 - conservative_score) * weights.get("conservative", 0.40)
            + neutral_score * weights.get("neutral", 0.35)
        )

        approved = final_score >= config.get("min_debate_score", 0.45)
        is_buy = signal.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)

        atr_stop_multiple = config.get("atr_stop_multiple", 2.0)
        atr_tp_multiple = config.get("atr_tp_multiple", 3.0)

        if is_buy:
            stop_loss = current_price - atr * atr_stop_multiple
            take_profit = current_price + atr * atr_tp_multiple
        else:
            stop_loss = current_price + atr * atr_stop_multiple
            take_profit = current_price - atr * atr_tp_multiple

        risk_per_share = abs(current_price - stop_loss)
        reward_per_share = abs(take_profit - current_price)
        rr_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0

        # Scale position by final_score
        base_risk_pct = config.get("risk_pct", 0.01)
        risk_dollars = portfolio.total_value * base_risk_pct * final_score
        position_size = int(risk_dollars / risk_per_share) if risk_per_share > 0 else 0

        max_loss = risk_per_share * position_size

        summary = (
            f"Aggressive: {aggressive_score:.2f}, "
            f"Conservative: {1.0 - conservative_score:.2f}, "
            f"Neutral: {neutral_score:.2f} => Final: {final_score:.2f}"
        )

        return RiskAssessment(
            symbol=signal.symbol,
            approved=approved and position_size > 0,
            position_size=float(position_size),
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            risk_reward_ratio=rr_ratio,
            max_loss_amount=max_loss,
            sizing_model="debate",
            risk_debate_summary=summary,
            warnings=[] if approved else [f"Debate score {final_score:.2f} below threshold"],
        )
