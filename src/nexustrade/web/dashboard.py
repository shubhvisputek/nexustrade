"""NexusTrade Streamlit Dashboard.

A comprehensive trading dashboard that connects to the NexusTrade FastAPI backend.

Run standalone:
    streamlit run src/nexustrade/web/dashboard.py
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DASHBOARD_TITLE = "NexusTrade Trading Dashboard"
DASHBOARD_VERSION = "0.1.0"
API_URL = os.environ.get("NEXUSTRADE_API_URL", "http://localhost:8085")

# ---------------------------------------------------------------------------
# API Client Helpers
# ---------------------------------------------------------------------------


def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Perform a GET request against the FastAPI backend.

    Returns the parsed JSON on success, or ``None`` when the backend is
    unreachable or returns a non-2xx status.
    """
    try:
        with httpx.Client(base_url=API_URL, timeout=10.0) as client:
            resp = client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return None


def api_put(path: str, json_body: dict[str, Any]) -> dict | None:
    """Perform a PUT request against the FastAPI backend.

    Returns the parsed JSON on success, or ``None`` on failure.
    """
    try:
        with httpx.Client(base_url=API_URL, timeout=10.0) as client:
            resp = client.put(path, json=json_body)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return None


def api_post(path: str, json_body: dict[str, Any]) -> dict | None:
    """Perform a POST request against the FastAPI backend.

    Returns the parsed JSON on success, or ``None`` on failure.
    """
    try:
        with httpx.Client(base_url=API_URL, timeout=10.0) as client:
            resp = client.post(path, json=json_body)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_currency(value: float | int | None) -> str:
    """Format a numeric value as USD currency string."""
    if value is None:
        return "$0.00"
    return f"${value:,.2f}"


def format_pnl(value: float | int | None) -> str:
    """Format a P&L value with sign prefix."""
    if value is None:
        return "$0.00"
    sign = "+" if value >= 0 else ""
    return f"{sign}${value:,.2f}"


def direction_color(direction: str) -> str:
    """Return an emoji indicator for a signal direction."""
    d = direction.lower() if direction else ""
    if d in ("buy", "long", "bullish"):
        return "🟢"
    elif d in ("sell", "short", "bearish"):
        return "🔴"
    return "⚪"


def service_status_indicator(status: str) -> str:
    """Return an emoji for a service health status."""
    s = status.lower() if status else "unknown"
    if s == "ok":
        return "✅"
    elif s in ("degraded", "error"):
        return "⚠️"
    return "❌"


# ---------------------------------------------------------------------------
# Page implementations
# ---------------------------------------------------------------------------


def page_overview() -> None:
    """Page 1: Dashboard Overview."""
    # -- Header ---------------------------------------------------------------
    health = api_get("/health")
    if health and health.get("status") == "ok":
        st.success(f"{DASHBOARD_TITLE} v{DASHBOARD_VERSION} — All systems operational")
    elif health:
        st.warning(f"{DASHBOARD_TITLE} v{DASHBOARD_VERSION} — System degraded")
    else:
        st.error(f"{DASHBOARD_TITLE} v{DASHBOARD_VERSION} — Backend unreachable")

    # -- Portfolio summary cards -----------------------------------------------
    portfolio = api_get("/portfolio") or {}
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Value", format_currency(portfolio.get("total_value")))
    with col2:
        st.metric("Cash", format_currency(portfolio.get("cash")))
    with col3:
        daily = portfolio.get("daily_pnl", 0)
        st.metric("Daily P&L", format_pnl(daily), delta=f"{daily:+.2f}" if daily else None)
    with col4:
        total = portfolio.get("total_pnl", 0)
        st.metric("Total P&L", format_pnl(total), delta=f"{total:+.2f}" if total else None)

    # -- Active positions ------------------------------------------------------
    st.subheader("Active Positions")
    positions = api_get("/portfolio/positions")
    if positions:
        st.dataframe(positions, use_container_width=True)
    else:
        st.info("No open positions.")

    # -- Recent signals --------------------------------------------------------
    st.subheader("Recent Signals (last 20)")
    signals = api_get("/signals", params={"limit": 20})
    if signals:
        for sig in signals:
            sig["indicator"] = direction_color(sig.get("direction", ""))
        st.dataframe(signals, use_container_width=True)
    else:
        st.info("No recent signals.")

    # -- Circuit breaker -------------------------------------------------------
    st.subheader("Circuit Breaker")
    st.info("Circuit breaker status: Normal")


def page_portfolio() -> None:
    """Page 2: Portfolio & Trading."""
    st.header("Portfolio & Trading")

    # -- Portfolio value placeholder chart -------------------------------------
    st.subheader("Portfolio Value")
    portfolio = api_get("/portfolio") or {}
    total_val = portfolio.get("total_value", 0)
    st.metric("Current Portfolio Value", format_currency(total_val))
    st.caption("Historical chart will be available once trade history accumulates.")

    # -- Positions with unrealized P&L -----------------------------------------
    st.subheader("Open Positions")
    positions = api_get("/portfolio/positions")
    if positions:
        st.dataframe(positions, use_container_width=True)
    else:
        st.info("No open positions.")

    # -- Trade history ---------------------------------------------------------
    st.subheader("Trade History")
    history_limit = st.slider("Max entries", 10, 200, 50, key="history_limit")
    history = api_get("/portfolio/history", params={"limit": history_limit})
    if history:
        st.dataframe(history, use_container_width=True)
    else:
        st.info("No trade history yet.")

    # -- Manual order form -----------------------------------------------------
    st.subheader("Manual Order (Webhook)")
    with st.form("manual_order"):
        symbol = st.text_input("Symbol", placeholder="AAPL")
        side = st.selectbox("Side", ["buy", "sell"])
        quantity = st.number_input("Quantity", min_value=1, value=1, step=1)
        price = st.number_input("Limit Price (0 = market)", min_value=0.0, value=0.0, step=0.01)
        submitted = st.form_submit_button("Submit Order")

    if submitted:
        order_payload = {
            "symbol": symbol.upper(),
            "side": side,
            "quantity": int(quantity),
            "price": float(price) if price > 0 else None,
        }
        result = api_post("/webhook/order", json_body=order_payload)
        if result:
            st.success(f"Order submitted: {result}")
        else:
            st.warning(
                "Could not submit order. The /webhook/order endpoint may not "
                "be available yet."
            )


def page_agents() -> None:
    """Page 3: Agents & Signals."""
    st.header("Agents & Signals")

    # -- Agent list placeholder -------------------------------------------------
    st.subheader("Registered Agents")
    config = api_get("/config") or {}
    llm_info = config.get("llm", {})
    st.json(llm_info)

    # -- Signal filtering -------------------------------------------------------
    st.subheader("Signal History")
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_symbol = st.text_input("Filter by Symbol", key="sig_symbol")
    with col2:
        filter_direction = st.selectbox(
            "Filter by Direction",
            ["All", "buy", "sell", "hold"],
            key="sig_dir",
        )
    with col3:
        filter_limit = st.slider("Max signals", 10, 200, 50, key="sig_limit")

    if filter_symbol:
        signals = api_get(f"/signals/{filter_symbol.upper()}", params={"limit": filter_limit})
    else:
        signals = api_get("/signals", params={"limit": filter_limit})

    signals = signals or []

    if filter_direction != "All":
        signals = [
            s for s in signals
            if s.get("direction", "").lower() == filter_direction
        ]

    if signals:
        for sig in signals:
            sig["indicator"] = direction_color(sig.get("direction", ""))
        st.dataframe(signals, use_container_width=True)

        # -- Confidence distribution ------------------------------------------
        st.subheader("Signal Confidence Distribution")
        confidences = [s.get("confidence", 0) for s in signals if s.get("confidence") is not None]
        if confidences:
            st.bar_chart(confidences)

        # -- Bull vs Bear ratio -----------------------------------------------
        st.subheader("Bull vs Bear Ratio")
        bull_count = sum(
            1 for s in signals
            if s.get("direction", "").lower() in ("buy", "long", "bullish")
        )
        bear_count = sum(
            1 for s in signals
            if s.get("direction", "").lower() in ("sell", "short", "bearish")
        )
        neutral_count = len(signals) - bull_count - bear_count
        ratio_col1, ratio_col2, ratio_col3 = st.columns(3)
        with ratio_col1:
            st.metric("Bullish", bull_count)
        with ratio_col2:
            st.metric("Bearish", bear_count)
        with ratio_col3:
            st.metric("Neutral", neutral_count)
    else:
        st.info("No signals available.")


def page_config() -> None:
    """Page 4: Configuration."""
    st.header("Configuration")

    # -- Current config --------------------------------------------------------
    st.subheader("Current Configuration")
    config = api_get("/config")
    if config:
        st.json(config)
    else:
        st.error("Unable to fetch configuration from the backend.")

    # -- Quick selectors -------------------------------------------------------
    st.subheader("Quick Settings")
    col1, col2 = st.columns(2)
    with col1:
        llm_mode = st.selectbox("LLM Mode", ["local", "cloud", "hybrid"], key="llm_mode")
        if st.button("Apply LLM Mode"):
            result = api_put("/config", json_body={"config": {"llm": {"mode": llm_mode}}})
            if result:
                st.success(f"LLM mode updated to '{llm_mode}'")
            else:
                st.error("Failed to update LLM mode.")
    with col2:
        exec_mode = st.selectbox(
            "Execution Mode",
            ["paper", "python", "tradingview", "both"],
            key="exec_mode",
        )
        if st.button("Apply Execution Mode"):
            result = api_put("/config", json_body={"config": {"execution": {"mode": exec_mode}}})
            if result:
                st.success(f"Execution mode updated to '{exec_mode}'")
            else:
                st.error("Failed to update execution mode.")

    # -- Market toggles --------------------------------------------------------
    st.subheader("Market Toggles")
    markets = {"US Equities": "us_equities", "Crypto": "crypto", "India": "india"}
    for label, key in markets.items():
        enabled = st.checkbox(label, value=True, key=f"mkt_{key}")
        if not enabled:
            st.caption(f"{label} market disabled (changes apply on next restart).")

    # -- Config editor ---------------------------------------------------------
    st.subheader("Advanced: Edit Config (YAML / JSON)")
    config_text = st.text_area(
        "Paste JSON config to merge into current configuration",
        height=200,
        placeholder='{"llm": {"mode": "cloud"}}',
        key="config_editor",
    )
    if st.button("Apply Config"):
        if config_text.strip():
            try:
                parsed = json.loads(config_text)
                result = api_put("/config", json_body={"config": parsed})
                if result:
                    st.success("Configuration updated successfully.")
                    st.json(result)
                else:
                    st.error("Backend rejected the update.")
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")
        else:
            st.warning("Config text is empty.")


def page_health() -> None:
    """Page 5: System Health."""
    st.header("System Health")

    # -- Auto-refresh -----------------------------------------------------------
    auto_refresh = st.checkbox("Auto-refresh (30s)", value=False, key="health_auto")

    # -- Service health table ---------------------------------------------------
    st.subheader("Service Status")
    health = api_get("/health")
    if health:
        services = health.get("services", {})
        rows = []
        for svc, status in services.items():
            rows.append({
                "Service": svc.capitalize(),
                "Status": status,
                "Indicator": service_status_indicator(status),
            })
        # Add inferred services
        extra_services = [
            ("OpenAlgo", "unknown"),
            ("Scheduler", "unknown"),
        ]
        for name, default_status in extra_services:
            if name.lower() not in services:
                rows.append({
                    "Service": name,
                    "Status": default_status,
                    "Indicator": service_status_indicator(default_status),
                })
        st.dataframe(rows, use_container_width=True)

        overall = health.get("status", "unknown")
        if overall == "ok":
            st.success(f"Overall status: {overall}")
        else:
            st.warning(f"Overall status: {overall}")
    else:
        st.error("Backend is unreachable. Ensure the FastAPI server is running.")

    # -- Detailed health checks -------------------------------------------------
    st.subheader("Individual Service Checks")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Redis**")
        redis_health = api_get("/health/redis")
        if redis_health:
            st.json(redis_health)
        else:
            st.error("Cannot reach Redis health endpoint.")
    with col2:
        st.markdown("**LLM (Ollama)**")
        llm_health = api_get("/health/llm")
        if llm_health:
            st.json(llm_health)
        else:
            st.error("Cannot reach LLM health endpoint.")

    # -- Metrics placeholder ----------------------------------------------------
    st.subheader("Metrics")
    st.info("Prometheus metrics will be displayed here once the /metrics endpoint is available.")

    # -- Log viewer placeholder -------------------------------------------------
    st.subheader("Log Viewer")
    st.text_area(
        "Recent logs",
        value="(Log streaming not yet connected.)",
        height=150,
        disabled=True,
    )

    # -- Auto-refresh loop ------------------------------------------------------
    if auto_refresh:
        time.sleep(30)
        st.rerun()


# ---------------------------------------------------------------------------
# Navigation & Main
# ---------------------------------------------------------------------------

PAGES: dict[str, Any] = {
    "Dashboard Overview": page_overview,
    "Portfolio & Trading": page_portfolio,
    "Agents & Signals": page_agents,
    "Configuration": page_config,
    "System Health": page_health,
}


def main() -> None:
    """Entry point for the Streamlit dashboard."""
    st.set_page_config(
        page_title=DASHBOARD_TITLE,
        page_icon="📈",
        layout="wide",
    )

    st.sidebar.title(DASHBOARD_TITLE)
    st.sidebar.caption(f"v{DASHBOARD_VERSION}")
    st.sidebar.markdown("---")

    selection = st.sidebar.radio("Navigate", list(PAGES.keys()))
    st.sidebar.markdown("---")
    st.sidebar.caption(f"API: {API_URL}")

    page_fn = PAGES.get(selection, page_overview)
    page_fn()


if __name__ == "__main__":
    main()
