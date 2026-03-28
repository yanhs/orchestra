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


def _print_stats(result) -> None:
    console.print()
    console.print(
        f"[dim]{len(result.responses)} responses | "
        f"Cost: ${result.total_cost:.4f} | "
        f"Time: {result.total_duration_ms / 1000:.1f}s[/]"
    )


def _print_summary(result) -> None:
    if result.summary:
        console.print()
        console.print(Rule("[bold yellow]Summary[/]"))
        console.print(Panel(Markdown(result.summary), border_style="yellow"))


def _make_coordinator(ctx: click.Context) -> OrchestraCoordinator:
    return OrchestraCoordinator(
        config_path=ctx.obj.get("config_path"),
        project_path=ctx.obj.get("project_path"),
    )


@click.group()
@click.option(
    "--config", "-c",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to agents.yaml config",
)
@click.option(
    "--project", "-p",
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
@click.option("--agents", "-a", default=None, help="Comma-separated agent names")
@click.option("--rounds", "-r", default=None, type=int, help="Number of discussion rounds")
@click.pass_context
def discuss(ctx: click.Context, topic: str, agents: str | None, rounds: int | None) -> None:
    """Round-robin discussion on a topic."""
    agent_names = [a.strip() for a in agents.split(",")] if agents else None
    coordinator = _make_coordinator(ctx)

    console.print(f"\n[bold]Mode:[/] Discussion")
    console.print(f"[bold]Topic:[/] {topic}")
    if agent_names:
        console.print(f"[bold]Agents:[/] {', '.join(agent_names)}")
    console.print()

    result = asyncio.run(
        coordinator.discuss(topic=topic, agent_names=agent_names, rounds=rounds, on_update=_update_handler)
    )
    _print_summary(result)
    _print_stats(result)


@cli.command()
@click.argument("topic")
@click.option(
    "--steps", "-s", default=None,
    help="Comma-separated agent:action pairs (e.g. architect:design,developer:implement,reviewer:review)",
)
@click.pass_context
def pipeline(ctx: click.Context, topic: str, steps: str | None) -> None:
    """Sequential pipeline: design -> implement -> review -> test."""
    parsed_steps = None
    if steps:
        parsed_steps = []
        for pair in steps.split(","):
            parts = pair.strip().split(":")
            if len(parts) != 2:
                raise click.BadParameter(f"Invalid step format: '{pair}'. Use agent:action")
            parsed_steps.append((parts[0].strip(), parts[1].strip()))

    coordinator = _make_coordinator(ctx)

    console.print(f"\n[bold]Mode:[/] Pipeline")
    console.print(f"[bold]Task:[/] {topic}")
    if parsed_steps:
        console.print(f"[bold]Steps:[/] {' -> '.join(f'{a}({act})' for a, act in parsed_steps)}")
    console.print()

    result = asyncio.run(
        coordinator.pipeline(topic=topic, steps=parsed_steps, on_update=_update_handler)
    )
    _print_summary(result)
    _print_stats(result)


@cli.command()
@click.argument("topic")
@click.option(
    "--tasks", "-t", multiple=True, required=True,
    help="Subtasks as 'agent:description' (repeat -t for each)",
)
@click.pass_context
def parallel(ctx: click.Context, topic: str, tasks: tuple[str, ...]) -> None:
    """Parallel work on subtasks, then merge results."""
    parsed_tasks = []
    for task_str in tasks:
        parts = task_str.split(":", 1)
        if len(parts) != 2:
            raise click.BadParameter(f"Invalid task format: '{task_str}'. Use agent:description")
        parsed_tasks.append((parts[0].strip(), parts[1].strip()))

    coordinator = _make_coordinator(ctx)

    console.print(f"\n[bold]Mode:[/] Parallel")
    console.print(f"[bold]Goal:[/] {topic}")
    for agent, desc in parsed_tasks:
        console.print(f"  [cyan]{agent}[/]: {desc}")
    console.print()

    result = asyncio.run(
        coordinator.parallel(topic=topic, tasks=parsed_tasks, on_update=_update_handler)
    )
    _print_summary(result)
    _print_stats(result)


@cli.command()
@click.argument("question")
@click.option("--agents", "-a", default=None, help="Comma-separated agent names")
@click.pass_context
def consensus(ctx: click.Context, question: str, agents: str | None) -> None:
    """Agents vote on a decision question. Supermajority wins."""
    agent_names = [a.strip() for a in agents.split(",")] if agents else None
    coordinator = _make_coordinator(ctx)

    console.print(f"\n[bold]Mode:[/] Consensus")
    console.print(f"[bold]Question:[/] {question}")
    if agent_names:
        console.print(f"[bold]Voters:[/] {', '.join(agent_names)}")
    console.print()

    result = asyncio.run(
        coordinator.consensus(topic=question, agent_names=agent_names, on_update=_update_handler)
    )
    _print_summary(result)
    _print_stats(result)


@cli.command()
@click.pass_context
def agents(ctx: click.Context) -> None:
    """List available agent roles."""
    coordinator = _make_coordinator(ctx)
    console.print("\n[bold]Available Agents:[/]\n")
    for name, role in coordinator.config.agents.items():
        console.print(f"  [cyan]{name:12s}[/] {role.display_name:10s} [dim]model={role.model}, tools={len(role.allowed_tools)}[/]")
    console.print()


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=3015, type=int, help="Port")
def serve(host: str, port: int) -> None:
    """Start the web UI server."""
    from ..web.server import run_server
    console.print(f"[bold]Starting web UI on {host}:{port}[/]")
    run_server(host=host, port=port)
