"""NexusTrade Streamlit dashboard.

A complete rewrite focused on what a trader actually needs:

- **Live Monitor** — running status, kill-switch, last tick, latest composites
- **Portfolio** — equity curve, positions, P&L breakdown, mark-to-market
- **Agents & Reasoning** — per-agent reasoning timeline (the killer LLM feature)
- **Orders & Trades** — manual ticket, fill ledger, CSV export
- **Backtest** — run a backtest on demand, see equity / drawdown / metrics
- **Risk** — circuit breaker status, recent assessments, kill switch
- **Configuration** — full deep-merge editor with YAML preview, agent toggles
- **Audit Log** — every event with category/level filters
- **Health** — Redis, LLM, broker, data provider, API
- **About / Demo Guide** — first-load guide for HF Spaces visitors

All pages read live data from the FastAPI backend; nothing is hardcoded.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from datetime import datetime
from typing import Any

import httpx
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_URL = os.environ.get("NEXUSTRADE_API_URL", "http://localhost:8085")
DEMO_MODE = os.environ.get("NEXUSTRADE_DEMO_MODE", "").lower() in {"1", "true", "yes"}
DEFAULT_CONFIG_PATH = os.environ.get("NEXUSTRADE_CONFIG", "config/demo.yaml")
REFRESH_OPTIONS = {"Off": 0, "5s": 5, "15s": 15, "30s": 30, "60s": 60}

st.set_page_config(
    page_title="NexusTrade",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _api_get(path: str, **params: Any) -> Any:
    """GET helper that surfaces errors instead of silently returning None."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{API_URL}{path}", params=params)
            if resp.status_code >= 400:
                return {"_error": f"{resp.status_code} {resp.text[:160]}"}
            return resp.json()
    except httpx.HTTPError as exc:
        return {"_error": f"backend unreachable at {API_URL}: {exc}"}


def _api_post(path: str, payload: Any | None = None, params: Any | None = None) -> Any:
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{API_URL}{path}", json=payload, params=params)
            if resp.status_code >= 400:
                return {"_error": f"{resp.status_code} {resp.text[:240]}"}
            return resp.json()
    except httpx.HTTPError as exc:
        return {"_error": f"backend unreachable at {API_URL}: {exc}"}


def _api_put(path: str, payload: Any) -> Any:
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.put(f"{API_URL}{path}", json=payload)
            if resp.status_code >= 400:
                return {"_error": f"{resp.status_code} {resp.text[:240]}"}
            return resp.json()
    except httpx.HTTPError as exc:
        return {"_error": f"backend unreachable at {API_URL}: {exc}"}


def _show_error(payload: Any) -> bool:
    """Return True when an error was rendered (so callers can short-circuit)."""
    if isinstance(payload, dict) and "_error" in payload:
        st.error(payload["_error"])
        return True
    return False


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


_DIRECTION_EMOJI = {
    "strong_buy": "🟢🟢",
    "buy": "🟢",
    "hold": "⚪",
    "sell": "🔴",
    "strong_sell": "🔴🔴",
}

_LEVEL_BADGE = {
    "info": "🟦",
    "warn": "🟧",
    "warning": "🟧",
    "error": "🟥",
    "critical": "💥",
}


def _fmt_money(x: float, currency: str = "$") -> str:
    if x is None:
        return "—"
    sign = "-" if x < 0 else ""
    return f"{sign}{currency}{abs(x):,.2f}"


def _ts_short(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
    except Exception:
        return ts


# ---------------------------------------------------------------------------
# Sidebar — global controls
# ---------------------------------------------------------------------------


def _sidebar() -> tuple[str, int]:
    """Sidebar with navigation, runtime controls, refresh, and BYO key."""
    st.sidebar.title("NexusTrade")
    st.sidebar.caption("Open-source LLM trading platform")

    snap = _api_get("/runtime")
    if isinstance(snap, dict) and "_error" not in snap:
        running = snap.get("loop_running")
        paused = snap.get("is_paused")
        kill = snap.get("kill_switch_engaged")
        if kill:
            st.sidebar.error("🛑 KILL SWITCH ENGAGED")
        elif paused:
            st.sidebar.warning("⏸ Paused")
        elif running:
            st.sidebar.success("● Live")
        else:
            st.sidebar.info("○ Stopped")
        last = snap.get("last_tick_at")
        if last:
            st.sidebar.caption(f"Last tick: {_ts_short(last)}")
    else:
        st.sidebar.warning("Backend unreachable")

    page = st.sidebar.radio(
        "Navigate",
        [
            "🏠 Live Monitor",
            "💼 Portfolio",
            "🤖 Agents & Reasoning",
            "📜 Orders & Trades",
            "📊 Backtest",
            "🛡 Risk & Kill Switch",
            "⚙ Configuration",
            "🪵 Audit Log",
            "❤ Health",
            "❓ About / Demo Guide",
        ],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    st.sidebar.subheader("Runtime")
    cols = st.sidebar.columns(2)
    if cols[0].button("Start", use_container_width=True, type="primary"):
        with st.spinner("Starting…"):
            r = _api_post("/runtime/start", {"config_path": DEFAULT_CONFIG_PATH})
            if not _show_error(r):
                st.toast(f"Loop started ({DEFAULT_CONFIG_PATH})")
    if cols[1].button("Stop", use_container_width=True):
        r = _api_post("/runtime/stop")
        if not _show_error(r):
            st.toast("Loop stopped")
    if st.sidebar.button("⚡ Run one tick", use_container_width=True):
        with st.spinner("Ticking…"):
            r = _api_post("/runtime/tick")
            if not _show_error(r):
                st.toast(
                    f"Tick complete — {r.get('signals_emitted', 0)} signals, "
                    f"{r.get('orders_placed', 0)} placed, "
                    f"{r.get('orders_blocked', 0)} blocked"
                )

    st.sidebar.divider()
    refresh_label = st.sidebar.selectbox(
        "Auto-refresh", list(REFRESH_OPTIONS), index=2
    )
    refresh_secs = REFRESH_OPTIONS[refresh_label]

    if DEMO_MODE:
        st.sidebar.divider()
        _byo_key_panel()

    st.sidebar.divider()
    st.sidebar.caption(f"API: {API_URL}")
    return page, refresh_secs


def _byo_key_panel() -> None:
    """Bring-your-own-LLM-key panel for the public HF demo."""
    with st.sidebar.expander("🔑 Bring Your Own LLM Key", expanded=False):
        provider = st.selectbox(
            "Provider", ["anthropic", "openai", "groq", "openrouter"], index=2
        )
        key = st.text_input("API key", type="password")
        cols = st.columns(2)
        if cols[0].button("Save", use_container_width=True, type="primary"):
            env_key = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "groq": "GROQ_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
            }[provider]
            if not key:
                st.warning("Enter a key first")
            else:
                os.environ[env_key] = key
                st.success(f"{env_key} stored for this session")
        if cols[1].button("Clear", use_container_width=True):
            for k in (
                "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                "GROQ_API_KEY", "OPENROUTER_API_KEY",
            ):
                os.environ.pop(k, None)
            st.success("Cleared all keys for this session")
        st.caption(
            "🔒 Keys live only in this Streamlit process. "
            "Free tiers: Groq <https://console.groq.com>, "
            "OpenRouter <https://openrouter.ai>."
        )


# ---------------------------------------------------------------------------
# Page: Live Monitor
# ---------------------------------------------------------------------------


def page_live() -> None:
    st.title("Live Monitor")
    st.caption("What the orchestrator is doing right now.")

    snap = _api_get("/runtime")
    if _show_error(snap):
        return

    cols = st.columns(5)
    cols[0].metric("Loop", "Running" if snap.get("loop_running") else "Stopped")
    cols[1].metric("Last tick", _ts_short(snap.get("last_tick_at")))
    cols[2].metric("Equity", _fmt_money(snap.get("account", {}).get("total_value", 0.0)))
    cols[3].metric("Daily P&L", _fmt_money(snap.get("account", {}).get("daily_pnl", 0.0)))
    cols[4].metric("Positions", snap.get("num_positions", 0))

    if snap.get("kill_switch_engaged"):
        st.error("🛑 Kill switch engaged — no orders will be placed.")
    elif snap.get("is_paused"):
        st.warning("⏸ Loop is paused.")

    st.divider()

    st.subheader("Recent ticks")
    ticks = _api_get("/runtime/ticks", limit=30)
    if isinstance(ticks, list) and ticks:
        df = pd.DataFrame(ticks)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        st.dataframe(
            df[
                [
                    c for c in [
                        "timestamp", "correlation_id", "symbols",
                        "signals_emitted", "composite_signals",
                        "orders_placed", "orders_blocked",
                        "duration_ms", "error",
                    ]
                    if c in df.columns
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No ticks yet — start the loop or click ⚡ Run one tick.")

    st.divider()
    st.subheader("Latest composite signals")
    composites = _api_get("/agents/composites", limit=50)
    if isinstance(composites, list) and composites:
        df = pd.DataFrame(composites)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp", ascending=False)
        latest = df.drop_duplicates("symbol")
        for _, row in latest.head(8).iterrows():
            cols = st.columns([0.15, 0.15, 0.10, 0.60])
            cols[0].markdown(f"**{row['symbol']}**")
            cols[1].markdown(
                f"{_DIRECTION_EMOJI.get(row['direction'], '·')} {row['direction']}"
            )
            cols[2].markdown(f"`{row['confidence']:.2f}`")
            cols[3].caption(row["reasoning"][:200])
    else:
        st.info("No composite signals yet.")


# ---------------------------------------------------------------------------
# Page: Portfolio
# ---------------------------------------------------------------------------


def page_portfolio() -> None:
    st.title("Portfolio")

    portfolio = _api_get("/portfolio")
    if _show_error(portfolio):
        return

    cols = st.columns(5)
    cols[0].metric("Cash", _fmt_money(portfolio.get("cash", 0.0)))
    cols[1].metric(
        "Positions value",
        _fmt_money(portfolio.get("positions_value", 0.0)),
    )
    cols[2].metric("Total equity", _fmt_money(portfolio.get("total_value", 0.0)))
    cols[3].metric(
        "Total P&L",
        _fmt_money(portfolio.get("total_pnl", 0.0)),
        delta=_fmt_money(portfolio.get("daily_pnl", 0.0)),
    )
    cols[4].metric("# Trades", portfolio.get("num_trades", 0))

    st.divider()
    st.subheader("Equity curve")
    equity = _api_get("/portfolio/equity", limit=4096)
    if isinstance(equity, list) and equity:
        df = pd.DataFrame(equity)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")
        st.line_chart(
            df.set_index("timestamp")[["total_value", "cash", "positions_value"]],
            use_container_width=True,
            height=280,
        )
        peak = df["total_value"].cummax()
        df["drawdown_pct"] = (df["total_value"] - peak) / peak * 100
        st.subheader("Drawdown (%)")
        st.area_chart(
            df.set_index("timestamp")["drawdown_pct"],
            use_container_width=True,
            height=160,
        )
    else:
        st.info("No equity history yet — run at least one tick.")

    st.divider()
    st.subheader("Open positions")
    positions = portfolio.get("positions", [])
    if positions:
        df = pd.DataFrame(positions)
        cols_keep = [
            c for c in [
                "symbol", "quantity", "avg_entry_price", "current_price",
                "unrealized_pnl", "realized_pnl", "broker", "market",
            ] if c in df.columns
        ]
        st.dataframe(df[cols_keep], use_container_width=True, hide_index=True)
    else:
        st.info("No open positions.")


# ---------------------------------------------------------------------------
# Page: Agents & Reasoning
# ---------------------------------------------------------------------------


def page_agents() -> None:
    st.title("Agents & Reasoning")
    st.caption("The why behind every signal — the killer LLM feature.")

    agents = _api_get("/agents")
    if _show_error(agents):
        return
    if not isinstance(agents, list):
        agents = []

    st.subheader("Registered agents")
    if agents:
        rows = [
            {
                "Agent": a.get("name"),
                "Type": a.get("type"),
                "LLM channel": (a.get("capabilities") or {}).get("llm_channel", "—"),
                "Markets": ", ".join((a.get("capabilities") or {}).get("supported_markets", [])),
                "Enabled": "✔" if a.get("enabled") else "✘",
            }
            for a in agents
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No agents registered yet — start the loop.")

    st.divider()
    st.subheader("Reasoning timeline")
    fcols = st.columns(3)
    symbol_filter = fcols[0].text_input("Filter symbol (e.g. AAPL)", "")
    agent_filter = fcols[1].selectbox(
        "Filter agent",
        ["(all)"] + sorted({a.get("name") for a in agents if a.get("name")}),
    )
    limit = fcols[2].slider("Max entries", 10, 500, 100, step=10)

    params: dict[str, Any] = {"limit": limit}
    if symbol_filter:
        params["symbol"] = symbol_filter.upper()
    if agent_filter != "(all)":
        params["agent"] = agent_filter

    traces = _api_get("/agents/reasoning", **params)
    if isinstance(traces, list) and traces:
        for entry in reversed(traces[-limit:]):
            with st.container(border=True):
                cols = st.columns([0.15, 0.15, 0.15, 0.10, 0.45])
                cols[0].caption(_ts_short(entry.get("timestamp")))
                cols[1].markdown(f"**{entry.get('symbol')}**")
                cols[2].markdown(
                    f"{_DIRECTION_EMOJI.get(entry.get('direction'), '·')} "
                    f"{entry.get('direction')}"
                )
                cols[3].caption(f"conf {entry.get('confidence', 0):.2f}")
                cols[4].markdown(f"_{entry.get('agent_name')}_")
                st.caption(entry.get("reasoning", "(no reasoning)"))
    else:
        st.info("No reasoning yet.")

    st.divider()
    st.subheader("Signal distribution")
    if isinstance(traces, list) and traces:
        counts = Counter(t.get("direction") for t in traces)
        chart_df = pd.DataFrame(
            {"direction": list(counts.keys()), "count": list(counts.values())}
        ).sort_values("direction")
        st.bar_chart(chart_df.set_index("direction"), use_container_width=True, height=200)


# ---------------------------------------------------------------------------
# Page: Orders & Trades
# ---------------------------------------------------------------------------


def page_orders() -> None:
    st.title("Orders & Trades")

    tabs = st.tabs(["📋 Manual ticket", "📜 Order book", "✅ Fills (CSV export)"])

    with tabs[0]:
        st.subheader("Manual order")
        with st.form("manual_order"):
            cols = st.columns(4)
            symbol = cols[0].text_input("Symbol", "AAPL")
            side = cols[1].selectbox("Side", ["buy", "sell"])
            qty = cols[2].number_input("Quantity", min_value=0.001, value=1.0, step=1.0)
            price = cols[3].number_input(
                "Price (0 = use latest quote)",
                min_value=0.0, value=0.0, step=0.01,
            )
            market = st.selectbox("Market", ["us_equity", "crypto", "india_equity", "forex"])
            confirmed = st.checkbox(
                "I confirm this is a paper-trading order. Real money requires explicit live mode."
            )
            submitted = st.form_submit_button("Submit order", type="primary")
            if submitted:
                if not confirmed:
                    st.error("Please confirm before submitting.")
                else:
                    payload = {
                        "symbol": symbol.upper(),
                        "side": side,
                        "quantity": float(qty),
                        "market": market,
                    }
                    if price > 0:
                        payload["price"] = float(price)
                    r = _api_post("/orders/manual", payload)
                    if not _show_error(r):
                        st.success(f"Filled: {r}")

    with tabs[1]:
        orders = _api_get("/orders", limit=200)
        if isinstance(orders, list) and orders:
            df = pd.DataFrame(orders)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            st.dataframe(df.sort_values("timestamp", ascending=False),
                         use_container_width=True, hide_index=True)
        else:
            st.info("No orders yet.")

    with tabs[2]:
        fills = _api_get("/orders/fills", limit=500)
        if isinstance(fills, list) and fills:
            df = pd.DataFrame(fills)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download CSV", csv,
                file_name="nexustrade_fills.csv", mime="text/csv",
            )
        else:
            st.info("No fills yet.")


# ---------------------------------------------------------------------------
# Page: Backtest
# ---------------------------------------------------------------------------


def page_backtest() -> None:
    st.title("Backtest")
    st.caption(
        "Run a backtest on historical Yahoo Finance data. Default is "
        "SMA(20/50) crossover; supply a strategy YAML for richer rules."
    )

    with st.form("bt_form"):
        cols = st.columns(4)
        symbol = cols[0].text_input("Symbol", "AAPL")
        timeframe = cols[1].selectbox("Timeframe", ["1d", "1h", "1wk"])
        days = cols[2].slider("Days back", 30, 3650, 365, step=30)
        capital = cols[3].number_input(
            "Initial capital ($)", min_value=1_000.0, value=100_000.0, step=1_000.0
        )
        cols2 = st.columns(2)
        commission_bps = cols2[0].slider("Commission (bps)", 0, 200, 10)
        slippage_bps = cols2[1].slider("Slippage (bps)", 0, 200, 10)
        strategy_yaml = st.text_input(
            "Strategy YAML (optional path)", "",
        )
        submit = st.form_submit_button("Run backtest", type="primary")

    if submit:
        with st.spinner("Running backtest…"):
            r = _api_post("/backtest/run", {
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "days": int(days),
                "initial_capital": float(capital),
                "commission_pct": commission_bps / 10_000.0,
                "slippage_pct": slippage_bps / 10_000.0,
                "strategy_yaml": strategy_yaml or None,
            })
            if not _show_error(r):
                _render_backtest_result(r)

    st.divider()
    st.subheader("Saved results")
    saved = _api_get("/backtest")
    if isinstance(saved, dict) and saved:
        for name in saved:
            with st.expander(name):
                _render_backtest_result(saved[name])
    else:
        st.info("No backtests stored yet.")


def _render_backtest_result(result: dict[str, Any]) -> None:
    metrics = result.get("metrics", {})
    cols = st.columns(5)
    cols[0].metric("Return", f"{metrics.get('total_return_pct', 0):.2f}%")
    cols[1].metric("Sharpe", f"{metrics.get('sharpe_ratio', 0):.2f}")
    cols[2].metric("Max DD", f"{metrics.get('max_drawdown_pct', 0):.2f}%")
    cols[3].metric("Win rate", f"{metrics.get('win_rate_pct', 0):.1f}%")
    cols[4].metric("Trades", metrics.get("num_trades", 0))

    eq = result.get("equity_curve") or []
    if eq:
        st.line_chart(pd.Series(eq, name="equity"), height=240, use_container_width=True)

    trades = result.get("trades") or []
    if trades:
        with st.expander(f"Trade ledger ({len(trades)} trades)"):
            st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Page: Risk
# ---------------------------------------------------------------------------


def page_risk() -> None:
    st.title("Risk & Kill Switch")
    risk = _api_get("/risk")
    if _show_error(risk):
        return

    cols = st.columns(4)
    cb_active = bool(risk.get("circuit_breaker_active"))
    cols[0].metric("Circuit breaker", "ACTIVE" if cb_active else "Normal")
    cols[1].metric(
        "Daily loss",
        f"{risk.get('daily_loss_pct', 0) * 100:.2f}%",
        delta=f"max {risk.get('max_daily_loss_pct', 0) * 100:.1f}%",
        delta_color="inverse",
    )
    cols[2].metric("Consecutive losses", risk.get("consecutive_losses", 0))
    cols[3].metric(
        "Kill switch",
        "ENGAGED" if risk.get("kill_switch_engaged") else "Released",
    )

    if cb_active and risk.get("circuit_breaker_reason"):
        st.error(f"Circuit breaker reason: {risk['circuit_breaker_reason']}")

    st.divider()
    st.subheader("Kill switch (manual override)")
    cols = st.columns(2)
    if cols[0].button("🛑 ENGAGE", type="primary", use_container_width=True):
        r = _api_post("/runtime/kill-switch", params={"reason": "manual"})
        if not _show_error(r):
            st.toast("Kill switch engaged")
    if cols[1].button("Release", use_container_width=True):
        r = _api_post("/runtime/kill-switch/release")
        if not _show_error(r):
            st.toast("Kill switch released")

    st.divider()
    st.subheader("Recent risk assessments")
    assessments = _api_get("/risk/assessments", limit=200)
    if isinstance(assessments, list) and assessments:
        df = pd.DataFrame(assessments)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        st.dataframe(df.sort_values("timestamp", ascending=False),
                     use_container_width=True, hide_index=True)
    else:
        st.info("No risk assessments recorded yet.")


# ---------------------------------------------------------------------------
# Page: Configuration
# ---------------------------------------------------------------------------


def page_config() -> None:
    st.title("Configuration")
    st.caption(
        "Live, deep-merge editor. Sensitive keys are masked and cannot be set "
        "via the UI — use environment variables for those."
    )

    config = _api_get("/config")
    if _show_error(config):
        return

    st.subheader("Quick controls")
    llm = config.get("llm", {}) or {}
    cols = st.columns(3)
    new_mode = cols[0].selectbox(
        "LLM mode",
        ["local", "cloud", "hybrid"],
        index=["local", "cloud", "hybrid"].index(llm.get("mode", "local"))
        if llm.get("mode") in ("local", "cloud", "hybrid") else 0,
    )
    exec_cfg = config.get("execution", {}) or {}
    new_exec = cols[1].selectbox(
        "Execution mode",
        ["python", "tradingview", "both"],
        index=["python", "tradingview", "both"].index(exec_cfg.get("mode", "python"))
        if exec_cfg.get("mode") in ("python", "tradingview", "both") else 0,
    )
    risk = config.get("risk", {}) or {}
    new_max_pos = cols[2].slider(
        "Max position %",
        0.0, 0.5, float(risk.get("max_position_pct", 0.05)), step=0.005,
    )

    st.subheader("Agent toggles")
    agents_cfg = (config.get("agents") or {}).get("enabled") or []
    edited_df: pd.DataFrame = pd.DataFrame()
    if agents_cfg:
        rows = []
        for entry in agents_cfg:
            if isinstance(entry, dict):
                rows.append({
                    "Agent": entry.get("name"),
                    "Source": entry.get("source", ""),
                    "Enabled": bool(entry.get("enabled", True)),
                })
        edited_df = st.data_editor(
            pd.DataFrame(rows),
            num_rows="fixed",
            disabled=["Agent", "Source"],
            use_container_width=True,
            hide_index=True,
            key="agent_editor",
        )
    else:
        st.info("No agents configured in active config.")

    if st.button("Apply quick controls", type="primary"):
        patch: dict[str, Any] = {
            "llm": {"mode": new_mode},
            "execution": {"mode": new_exec},
            "risk": {"max_position_pct": float(new_max_pos)},
        }
        if not edited_df.empty:
            patch["agents"] = {
                "enabled": [
                    {
                        "name": row["Agent"],
                        "source": row["Source"],
                        "enabled": bool(row["Enabled"]),
                    }
                    for _, row in edited_df.iterrows()
                ]
            }
        r = _api_put("/config", {"config": patch})
        if not _show_error(r):
            st.toast("Config applied")

    st.divider()
    st.subheader("Advanced — raw JSON patch")
    patch_text = st.text_area(
        "JSON to deep-merge into the active config",
        '{\n  "scheduler": {"analysis_interval": "1h"}\n}',
        height=160,
    )
    if st.button("Apply JSON patch"):
        try:
            patch = json.loads(patch_text)
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
        else:
            r = _api_put("/config", {"config": patch})
            if not _show_error(r):
                st.success("Applied")
                st.json(r)

    st.divider()
    st.subheader("Active configuration (sensitive keys redacted)")
    st.json(config, expanded=False)


# ---------------------------------------------------------------------------
# Page: Audit Log
# ---------------------------------------------------------------------------


def page_audit() -> None:
    st.title("Audit Log")
    st.caption("Every event the orchestrator emits — searchable.")

    cols = st.columns(4)
    category = cols[0].selectbox(
        "Category",
        ["(all)", "config", "tick", "signal", "risk", "order", "fill", "alert", "system", "error"],
    )
    level = cols[1].selectbox(
        "Level", ["(all)", "info", "warn", "warning", "error", "critical"]
    )
    limit = cols[2].slider("Max", 50, 2000, 300, step=50)
    search = cols[3].text_input("Search text", "")

    params: dict[str, Any] = {"limit": limit}
    if category != "(all)":
        params["category"] = category
    if level != "(all)":
        params["level"] = level

    log = _api_get("/audit/log", **params)
    if not isinstance(log, list):
        _show_error(log)
        return

    if search:
        s = search.lower()
        log = [e for e in log if s in (e.get("message") or "").lower()]

    for e in reversed(log[-limit:]):
        badge = _LEVEL_BADGE.get(e.get("level", "info"), "·")
        msg = e.get("message", "")
        ts = _ts_short(e.get("timestamp"))
        st.markdown(f"`{ts}` {badge} **{e.get('category')}** — {msg}")

    st.divider()
    st.subheader("Recent alerts (notification dispatches)")
    alerts = _api_get("/audit/alerts", limit=100)
    if isinstance(alerts, list) and alerts:
        df = pd.DataFrame(alerts)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No alerts dispatched yet.")


# ---------------------------------------------------------------------------
# Page: Health
# ---------------------------------------------------------------------------


def page_health() -> None:
    st.title("Health")
    cols = st.columns(3)
    overall = _api_get("/health")
    cols[0].metric(
        "Overall",
        overall.get("status", "?") if isinstance(overall, dict) else "?",
    )

    redis = _api_get("/health/redis")
    cols[1].metric(
        "Redis",
        redis.get("redis", "?") if isinstance(redis, dict) else "?",
    )

    llm = _api_get("/health/llm")
    cols[2].metric(
        "LLM",
        llm.get("llm", "?") if isinstance(llm, dict) else "?",
    )

    st.divider()
    st.subheader("Service detail")
    st.json({"overall": overall, "redis": redis, "llm": llm})


# ---------------------------------------------------------------------------
# Page: About / Demo Guide
# ---------------------------------------------------------------------------


def page_about() -> None:
    st.title("Welcome to NexusTrade")
    st.markdown("""
**Open-source LLM trading platform** — 18 investor-persona LLM agents,
risk-aware execution, multi-market support, and a fully configurable
YAML pipeline.

#### Try the demo in 3 steps

1. **Bring an LLM key** _(optional)_ — open the sidebar's
   "🔑 Bring Your Own LLM Key" panel. The free Groq tier works fine.
   Without a key the platform falls back to the **deterministic
   momentum baseline** so the demo still runs.
2. **Start the loop** — click **Start** in the sidebar. The orchestrator
   instantiates a Yahoo Finance data adapter, a paper broker, and the
   configured agents. Then click **⚡ Run one tick** to fire an
   immediate iteration.
3. **Watch it work** — visit:
   - **🏠 Live Monitor** — what the loop just did
   - **🤖 Agents & Reasoning** — the *why* behind every signal
   - **💼 Portfolio** — equity curve, P&L, positions
   - **📊 Backtest** — run an SMA(20/50) crossover on any symbol

#### What's safe?
Every order goes through the **paper broker**. No real broker is
connected unless you explicitly configure one and set
`NEXUSTRADE_LIVE_OK=1`. The kill switch on the **Risk** page blocks all
new orders instantly.

#### Want to see source / fork?
GitHub: <https://github.com/shubhvisputek/nexustrade>
""")


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------


PAGES = {
    "🏠 Live Monitor": page_live,
    "💼 Portfolio": page_portfolio,
    "🤖 Agents & Reasoning": page_agents,
    "📜 Orders & Trades": page_orders,
    "📊 Backtest": page_backtest,
    "🛡 Risk & Kill Switch": page_risk,
    "⚙ Configuration": page_config,
    "🪵 Audit Log": page_audit,
    "❤ Health": page_health,
    "❓ About / Demo Guide": page_about,
}


def main() -> None:
    page, refresh = _sidebar()
    PAGES[page]()
    if refresh > 0:
        time.sleep(refresh)
        st.rerun()


# Streamlit runs scripts with __name__ == "__main__" via its bootstrap.
# Avoid invoking main() on import so the module is testable and importable
# from FastAPI lifespan or notebooks without spinning up the UI.
if __name__ == "__main__":
    main()
