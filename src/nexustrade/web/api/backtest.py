"""Backtest endpoints — start a backtest and read results."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nexustrade.runtime.backtest_runner import run_backtest
from nexustrade.runtime.state import get_runtime_state

router = APIRouter()


class BacktestPayload(BaseModel):
    symbol: str = "AAPL"
    timeframe: str = "1d"
    days: int = Field(default=365, gt=0, le=3650)
    initial_capital: float = 100_000.0
    commission_pct: float = 0.001
    slippage_pct: float = 0.001
    strategy_yaml: str | None = None
    data_provider: str = "yahoo"
    name: str | None = None


@router.get("")
async def list_backtests() -> dict[str, Any]:
    state = get_runtime_state()
    return state.backtests


@router.get("/{name}")
async def get_backtest(name: str) -> dict[str, Any]:
    state = get_runtime_state()
    if name not in state.backtests:
        raise HTTPException(404, f"Backtest '{name}' not found")
    return state.backtests[name]


@router.post("/run")
async def run_one(payload: BacktestPayload) -> dict[str, Any]:
    end = datetime.now(UTC)
    start = end - timedelta(days=payload.days)

    # Build a data provider on demand
    if payload.data_provider == "yahoo":
        from nexustrade.data.adapters.yahoo import YahooFinanceAdapter
        provider = YahooFinanceAdapter({})
    elif payload.data_provider == "ccxt":
        from nexustrade.data.adapters.ccxt_data import CCXTDataAdapter
        provider = CCXTDataAdapter({})
    else:
        raise HTTPException(400, f"Unknown data provider: {payload.data_provider}")

    try:
        result = await run_backtest(
            symbol=payload.symbol.upper(),
            timeframe=payload.timeframe,
            start=start,
            end=end,
            data_provider=provider,
            initial_capital=payload.initial_capital,
            commission_pct=payload.commission_pct,
            slippage_pct=payload.slippage_pct,
            strategy_yaml=payload.strategy_yaml,
            name=payload.name,
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
