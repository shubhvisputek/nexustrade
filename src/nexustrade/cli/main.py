"""NexusTrade CLI — unified LLM trading platform."""

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

app.add_typer(agents_app, name="agents")
app.add_typer(plugins_app, name="plugins")

console = Console()


@app.command()
def trade(
    config: str = typer.Option("config/default.yaml", help="Path to config YAML file"),
) -> None:
    """Start live trading with the given configuration."""
    from nexustrade.core.config import load_config

    cfg = load_config(config)
    console.print(f"[bold green]NexusTrade[/] starting with config: {config}")
    console.print(f"  LLM mode: {cfg.llm.mode}")
    console.print(f"  Markets: {list(cfg.markets.keys())}")
    console.print(f"  Execution mode: {cfg.execution.mode}")
    console.print("[yellow]Live trading loop not yet implemented.[/]")


@app.command()
def backtest(
    strategy: str = typer.Option(..., help="Path to strategy YAML file"),
    start: str = typer.Option(..., "--from", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--to", help="End date (YYYY-MM-DD)"),
) -> None:
    """Run a backtest on historical data."""
    from nexustrade.backtest.engine import BacktestEngine
    from nexustrade.backtest.report import format_report
    from nexustrade.strategy.parser import parse_strategy

    console.print(f"[bold]Backtest:[/] {strategy}")
    console.print(f"  Period: {start} to {end}")

    try:
        strat = parse_strategy(strategy)
        console.print(f"  Strategy: {strat.name} ({len(strat.rules)} rules)")
    except Exception as e:
        console.print(f"[red]Error loading strategy: {e}[/]")
        raise typer.Exit(1)

    console.print("[yellow]Full backtest with data pipeline not yet wired. Use API for programmatic backtests.[/]")


@app.command()
def paper(
    config: str = typer.Option("config/default.yaml", help="Path to config YAML file"),
) -> None:
    """Start paper trading with the given configuration."""
    from nexustrade.core.config import load_config

    cfg = load_config(config)
    console.print(f"[bold green]Paper Trading[/] starting with config: {config}")
    console.print(f"  LLM mode: {cfg.llm.mode}")
    console.print(f"  Markets: {list(cfg.markets.keys())}")
    console.print(f"  Agents: {[a.name for a in cfg.agents.enabled]}")
    console.print("[yellow]Paper trading loop not yet implemented.[/]")


@app.command()
def webhook(
    port: int = typer.Option(8888, help="Webhook listener port"),
) -> None:
    """Start TradingView webhook receiver."""
    console.print(f"[bold]Webhook server[/] on port {port}")
    console.print("[yellow]Use: uvicorn nexustrade.web.app:app --port {port}[/]")


@app.command()
def health() -> None:
    """Check health of all NexusTrade services."""
    table = Table(title="NexusTrade Health Check")
    table.add_column("Service", style="cyan")
    table.add_column("Status", style="green")

    # Check Redis
    try:
        import redis
        r = redis.Redis()
        r.ping()
        table.add_row("Redis", "[green]OK[/]")
    except Exception:
        table.add_row("Redis", "[red]DOWN[/]")

    # Check Ollama
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2)
        table.add_row("Ollama", "[green]OK[/]" if resp.status_code == 200 else "[red]DOWN[/]")
    except Exception:
        table.add_row("Ollama", "[red]DOWN[/]")

    # Check OpenAlgo
    try:
        import httpx
        resp = httpx.get("http://localhost:5000/", timeout=2)
        table.add_row("OpenAlgo", "[green]OK[/]" if resp.status_code == 200 else "[red]DOWN[/]")
    except Exception:
        table.add_row("OpenAlgo", "[yellow]NOT RUNNING[/]")

    console.print(table)


@agents_app.command("list")
def agents_list() -> None:
    """List all available and enabled agents."""
    from nexustrade.agents.adapters.ai_hedge_fund import AIHedgeFundAgentGroup

    table = Table(title="Available Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Type")

    for name in AIHedgeFundAgentGroup.AGENTS:
        table.add_row(name, "ai_hedge_fund", "persona")

    table.add_row("bull_bear_debate", "trading_agents", "debate")
    table.add_row("finbert", "finbert", "sentiment")
    table.add_row("finrl", "finrl", "rl")
    table.add_row("fingpt", "fingpt", "sentiment")
    table.add_row("quantagent", "quantagent", "vision")
    table.add_row("qlib_alpha", "qlib", "factor")

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

    if not any([registry.data_providers, registry.brokers, registry.agents]):
        console.print("[yellow]No plugins discovered. Install extras: uv sync --extra agents --extra data --extra execution[/]")
    else:
        console.print(table)


if __name__ == "__main__":
    app()
