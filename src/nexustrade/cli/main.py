"""NexusTrade CLI — unified LLM trading platform."""

import typer

app = typer.Typer(
    name="nexus",
    help="NexusTrade — unified open-source LLM trading platform.",
    no_args_is_help=True,
)

agents_app = typer.Typer(help="Manage AI trading agents.")
plugins_app = typer.Typer(help="Manage plugins and adapters.")

app.add_typer(agents_app, name="agents")
app.add_typer(plugins_app, name="plugins")


@app.command()
def trade(
    config: str = typer.Option("config/default.yaml", help="Path to config YAML file"),
) -> None:
    """Start live trading with the given configuration."""
    typer.echo(f"Not yet implemented. Config: {config}")


@app.command()
def backtest(
    strategy: str = typer.Option(..., help="Path to strategy YAML file"),
    start: str = typer.Option(..., "--from", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--to", help="End date (YYYY-MM-DD)"),
) -> None:
    """Run a backtest on historical data."""
    typer.echo(f"Not yet implemented. Strategy: {strategy}, from {start} to {end}")


@app.command()
def paper(
    config: str = typer.Option("config/default.yaml", help="Path to config YAML file"),
) -> None:
    """Start paper trading with the given configuration."""
    typer.echo(f"Not yet implemented. Config: {config}")


@app.command()
def webhook(
    port: int = typer.Option(8888, help="Webhook listener port"),
) -> None:
    """Start TradingView webhook receiver."""
    typer.echo(f"Not yet implemented. Port: {port}")


@app.command()
def health() -> None:
    """Check health of all NexusTrade services."""
    typer.echo("Not yet implemented.")


@agents_app.command("list")
def agents_list() -> None:
    """List all available and enabled agents."""
    typer.echo("No agents configured yet.")


@plugins_app.command("list")
def plugins_list() -> None:
    """List all discovered plugins."""
    typer.echo("No plugins discovered yet.")


if __name__ == "__main__":
    app()
