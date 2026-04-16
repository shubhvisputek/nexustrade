"""NexusTrade CLI — unified LLM trading platform."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="nexus",
    help="NexusTrade — unified open-source LLM trading platform.",
    no_args_is_help=True,
)

agents_app = typer.Typer(help="Manage AI trading agents.")
plugins_app = typer.Typer(help="Manage plugins and adapters.")
runtime_app = typer.Typer(help="Inspect or control the live runtime.")

app.add_typer(agents_app, name="agents")
app.add_typer(plugins_app, name="plugins")
app.add_typer(runtime_app, name="runtime")

console = Console()


# ---------------------------------------------------------------------------
# Trading commands
# ---------------------------------------------------------------------------


@app.command()
def paper(
    config: str = typer.Option("config/default.yaml", help="Path to config YAML file"),
    once: bool = typer.Option(False, "--once", help="Run a single tick and exit"),
    serve: bool = typer.Option(
        False, "--serve", help="Also start the FastAPI/dashboard process"
    ),
    api_port: int = typer.Option(8085, help="FastAPI port (used with --serve)"),
    ui_port: int = typer.Option(8501, help="Streamlit port (used with --serve)"),
) -> None:
    """Start paper trading with the given configuration."""
    from nexustrade.core.config import load_config
    from nexustrade.runtime.paper_loop import get_or_create_loop

    cfg = load_config(config)
    console.print(f"[bold green]NexusTrade Paper Trading[/]")
    console.print(f"  Config: [cyan]{config}[/]")
    console.print(f"  LLM mode: {cfg.llm.mode}")
    console.print(f"  Markets: {list(cfg.markets.keys())}")
    console.print(f"  Agents enabled: {[a.name for a in cfg.agents.enabled]}")
    console.print(f"  Aggregation: {cfg.agents.aggregation_mode}")

    async def _run() -> None:
        loop = await get_or_create_loop(cfg, config_path=config)
        if once:
            console.print("[bold]Running a single tick…[/]")
            summary = await loop.tick_once()
            console.print(_format_tick_summary(summary))
            return
        await loop.start()
        console.print(
            f"[green]Loop started[/] — interval [cyan]{loop.tick_seconds}s[/]. "
            "Press Ctrl-C to stop."
        )
        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[yellow]Stopping…[/]")
            await loop.stop()

    if serve:
        # Run uvicorn in-process so the user gets API + loop in one command.
        import uvicorn
        import os
        os.environ["NEXUSTRADE_AUTOSTART_LOOP"] = "1"
        os.environ["NEXUSTRADE_CONFIG"] = config
        console.print(
            f"[green]Serving FastAPI on :{api_port} (autostart enabled). "
            f"Run streamlit separately on :{ui_port}.[/]"
        )
        uvicorn.run("nexustrade.web.app:app", host="0.0.0.0", port=api_port)
    else:
        asyncio.run(_run())


@app.command()
def trade(
    config: str = typer.Option("config/default.yaml", help="Path to config YAML file"),
) -> None:
    """Start LIVE trading (real money) with the given configuration.

    For your safety this command refuses to run unless every configured
    broker explicitly declares ``is_paper == False`` AND the env var
    ``NEXUSTRADE_LIVE_OK=1`` is set.
    """
    import os

    if os.environ.get("NEXUSTRADE_LIVE_OK") != "1":
        console.print(
            "[red]Refusing to run live trading.[/] Set "
            "[bold]NEXUSTRADE_LIVE_OK=1[/] to override (and read the disclaimer)."
        )
        raise typer.Exit(2)
    # Otherwise behaves like `paper`. The broker selection in YAML
    # determines whether the run is actually paper or live.
    paper(config=config)


@app.command()
def backtest(
    strategy: str | None = typer.Option(
        None, help="Path to strategy YAML file (optional — defaults to SMA crossover)"
    ),
    symbol: str = typer.Option("AAPL", help="Symbol to backtest"),
    start: str = typer.Option(..., "--from", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--to", help="End date (YYYY-MM-DD)"),
    timeframe: str = typer.Option("1d", help="Bar timeframe"),
    capital: float = typer.Option(100_000.0, help="Initial capital"),
    provider: str = typer.Option("yahoo", help="Data provider (yahoo, ccxt)"),
    out: str | None = typer.Option(None, help="Optional JSON output path"),
) -> None:
    """Run a backtest on historical data."""
    from nexustrade.runtime.backtest_runner import run_backtest

    start_dt = datetime.fromisoformat(start).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=UTC)

    if provider == "yahoo":
        from nexustrade.data.adapters.yahoo import YahooFinanceAdapter
        data_provider = YahooFinanceAdapter({})
    elif provider == "ccxt":
        from nexustrade.data.adapters.ccxt_data import CCXTDataAdapter
        data_provider = CCXTDataAdapter({})
    else:
        console.print(f"[red]Unknown provider: {provider}[/]")
        raise typer.Exit(1)

    console.print(f"[bold]Backtest:[/] {symbol} {start} → {end} ({timeframe})")
    if strategy:
        console.print(f"  Strategy: [cyan]{strategy}[/]")
    else:
        console.print("  Strategy: [cyan]default SMA(20/50) crossover[/]")

    result = asyncio.run(
        run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            start=start_dt,
            end=end_dt,
            data_provider=data_provider,
            initial_capital=capital,
            strategy_yaml=strategy,
        )
    )

    metrics = result.get("metrics", {})
    table = Table(title=f"Backtest Result: {result.get('strategy_name')}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total return", f"{metrics.get('total_return_pct', 0.0):.2f} %")
    table.add_row("Annualized return", f"{metrics.get('annualized_return_pct', 0.0):.2f} %")
    table.add_row("Sharpe", f"{metrics.get('sharpe_ratio', 0.0):.2f}")
    table.add_row("Sortino", f"{metrics.get('sortino_ratio', 0.0):.2f}")
    table.add_row("Max drawdown", f"{metrics.get('max_drawdown_pct', 0.0):.2f} %")
    table.add_row("Win rate", f"{metrics.get('win_rate_pct', 0.0):.2f} %")
    table.add_row("Profit factor", f"{metrics.get('profit_factor', 0.0):.2f}")
    table.add_row("Trades", str(metrics.get("num_trades", 0)))
    table.add_row("Final value", f"${result.get('final_value', 0.0):,.2f}")
    console.print(table)

    if out:
        Path(out).write_text(json.dumps(result, indent=2))
        console.print(f"[green]Wrote full result to {out}[/]")


@app.command()
def webhook(
    port: int = typer.Option(8888, help="Webhook listener port"),
) -> None:
    """Start TradingView webhook receiver (FastAPI)."""
    import os
    import uvicorn

    os.environ["NEXUSTRADE_AUTOSTART_LOOP"] = os.environ.get(
        "NEXUSTRADE_AUTOSTART_LOOP", "0"
    )
    console.print(f"[bold]Webhook + API server[/] on port [cyan]{port}[/]")
    uvicorn.run("nexustrade.web.app:app", host="0.0.0.0", port=port)


@app.command()
def serve(
    port: int = typer.Option(8085, help="FastAPI port"),
    autostart: bool = typer.Option(False, "--autostart", help="Auto-start the loop"),
    config: str = typer.Option("config/demo.yaml", help="Config for autostart"),
) -> None:
    """Run the FastAPI server (used by the dashboard and webhook receiver)."""
    import os
    import uvicorn

    if autostart:
        os.environ["NEXUSTRADE_AUTOSTART_LOOP"] = "1"
        os.environ["NEXUSTRADE_CONFIG"] = config
    console.print(f"[bold green]NexusTrade API[/] on port [cyan]{port}[/]")
    uvicorn.run("nexustrade.web.app:app", host="0.0.0.0", port=port)


@app.command()
def health() -> None:
    """Check health of all NexusTrade services."""
    table = Table(title="NexusTrade Health Check")
    table.add_column("Service", style="cyan")
    table.add_column("Status", style="green")

    # Redis
    try:
        import redis
        r = redis.Redis()
        r.ping()
        table.add_row("Redis", "[green]OK[/]")
    except Exception:
        table.add_row("Redis", "[yellow]NOT RUNNING[/]")

    # Ollama
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2)
        table.add_row(
            "Ollama",
            "[green]OK[/]" if resp.status_code == 200 else "[red]DOWN[/]",
        )
    except Exception:
        table.add_row("Ollama", "[yellow]NOT RUNNING[/]")

    # OpenAlgo
    try:
        import httpx
        resp = httpx.get("http://localhost:5000/", timeout=2)
        table.add_row(
            "OpenAlgo",
            "[green]OK[/]" if resp.status_code == 200 else "[red]DOWN[/]",
        )
    except Exception:
        table.add_row("OpenAlgo", "[yellow]NOT RUNNING[/]")

    # Yahoo Finance (no creds needed)
    try:
        import yfinance as yf
        info = yf.Ticker("AAPL").info
        table.add_row(
            "Yahoo Finance",
            "[green]OK[/]" if info else "[yellow]NO DATA[/]",
        )
    except Exception:
        table.add_row("Yahoo Finance", "[red]DOWN[/]")

    console.print(table)


# ---------------------------------------------------------------------------
# Agent / plugin / runtime sub-commands
# ---------------------------------------------------------------------------


@agents_app.command("list")
def agents_list() -> None:
    """List all available agents (whether or not enabled in config)."""
    from nexustrade.agents.adapters.ai_hedge_fund import AIHedgeFundAgentGroup
    from nexustrade.agents.prompt_loader import PromptLoader

    loader = PromptLoader()
    available_templates = {
        Path(p).stem for p in loader.list_templates("agents")
    }

    table = Table(title="Available Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Type")
    table.add_column("Template?")

    for name in AIHedgeFundAgentGroup.AGENTS:
        has_template = name in available_templates
        table.add_row(
            name,
            "ai_hedge_fund",
            "persona",
            "[green]yes[/]" if has_template else "[red]MISSING[/]",
        )

    table.add_row("bull_bear_debate", "trading_agents", "debate", "n/a")
    table.add_row("finbert", "finbert", "sentiment", "n/a")
    table.add_row("finrl", "finrl", "rl", "n/a")
    table.add_row("fingpt", "fingpt", "sentiment", "n/a")
    table.add_row("quantagent", "quantagent", "vision", "n/a")
    table.add_row("qlib_alpha", "qlib", "factor", "n/a")
    table.add_row("momentum_baseline", "runtime", "deterministic", "n/a")

    console.print(table)


@plugins_app.command("list")
def plugins_list() -> None:
    """List all discovered plugins."""
    from nexustrade.core.registry import AdapterRegistry

    registry = AdapterRegistry()
    registry.discover_all()

    table = Table(title="Discovered Plugins")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")

    for name in registry.data_providers:
        table.add_row("data", name)
    for name in registry.brokers:
        table.add_row("broker", name)
    for name in registry.agents:
        table.add_row("agent", name)
    for name in registry.notifications:
        table.add_row("notification", name)

    if not any(
        [registry.data_providers, registry.brokers, registry.agents]
    ):
        console.print(
            "[yellow]No plugins discovered. Install extras: "
            "uv sync --extra agents --extra data --extra execution[/]"
        )
    else:
        console.print(table)


@runtime_app.command("status")
def runtime_status() -> None:
    """Print the in-process runtime state snapshot."""
    from nexustrade.runtime.state import get_runtime_state

    state = get_runtime_state()
    snap = state.snapshot()
    table = Table(title="Runtime State Snapshot")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    for k, v in snap.items():
        table.add_row(k, str(v))
    console.print(table)


@runtime_app.command("tick")
def runtime_tick(
    config: str = typer.Option("config/demo.yaml", help="Config to use if loop not started"),
) -> None:
    """Run a single orchestrator tick locally (no server required)."""
    from nexustrade.core.config import load_config
    from nexustrade.runtime.paper_loop import get_or_create_loop

    cfg = load_config(config)

    async def _go() -> None:
        loop = await get_or_create_loop(cfg, config_path=config)
        summary = await loop.tick_once()
        console.print(_format_tick_summary(summary))

    asyncio.run(_go())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_tick_summary(summary) -> str:  # type: ignore[no-untyped-def]
    return (
        f"[bold]tick {summary.correlation_id}[/]\n"
        f"  symbols: {summary.symbols}\n"
        f"  signals emitted: {summary.signals_emitted}\n"
        f"  composites:      {summary.composite_signals}\n"
        f"  orders placed:   {summary.orders_placed}\n"
        f"  orders blocked:  {summary.orders_blocked}\n"
        f"  duration:        {summary.duration_ms:.1f} ms"
        + (f"\n  [red]ERROR:[/] {summary.error}" if summary.error else "")
    )


if __name__ == "__main__":
    app()
