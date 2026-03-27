"""CLI interface for Agent Orchestra."""

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule

from ..orchestrator.coordinator import OrchestraCoordinator

console = Console()


def _update_handler(agent_name: str, event: str, text: str) -> None:
    """Handle progress updates from orchestrator."""
    if event == "start":
        console.print(Rule(f"[bold cyan]{agent_name}[/] - {text}"))
    elif event == "done":
        console.print(Panel(Markdown(text), title=f"[bold]{agent_name}[/]", border_style="green"))
    elif event == "error":
        console.print(Panel(text, title=f"[bold red]{agent_name} ERROR[/]", border_style="red"))


@click.group()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to agents.yaml config",
)
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Project directory for agents to work in",
)
@click.pass_context
def cli(ctx: click.Context, config: Path | None, project: Path | None) -> None:
    """Agent Orchestra — multi-agent collaboration system."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["project_path"] = project


@cli.command()
@click.argument("topic")
@click.option(
    "--agents",
    "-a",
    default=None,
    help="Comma-separated agent names (e.g. architect,developer,reviewer)",
)
@click.option("--rounds", "-r", default=None, type=int, help="Number of discussion rounds")
@click.pass_context
def discuss(ctx: click.Context, topic: str, agents: str | None, rounds: int | None) -> None:
    """Start a round-robin discussion on a topic."""
    agent_names = [a.strip() for a in agents.split(",")] if agents else None

    coordinator = OrchestraCoordinator(
        config_path=ctx.obj.get("config_path"),
        project_path=ctx.obj.get("project_path"),
    )

    console.print(f"\n[bold]Topic:[/] {topic}")
    if agent_names:
        console.print(f"[bold]Agents:[/] {', '.join(agent_names)}")
    console.print()

    result = asyncio.run(
        coordinator.discuss(
            topic=topic,
            agent_names=agent_names,
            rounds=rounds,
            on_update=_update_handler,
        )
    )

    # Print summary
    if result.summary:
        console.print()
        console.print(Rule("[bold yellow]Summary[/]"))
        console.print(Panel(Markdown(result.summary), border_style="yellow"))

    # Stats
    console.print()
    console.print(
        f"[dim]Agents: {len(result.responses)} responses | "
        f"Cost: ${result.total_cost:.4f} | "
        f"Time: {result.total_duration_ms / 1000:.1f}s[/]"
    )
