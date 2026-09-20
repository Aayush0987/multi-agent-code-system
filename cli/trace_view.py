"""Phase 7 trace viewer: renders a saved run log's full decision path --
macro supervisor steps, nested critique-loop rounds, and a timing breakdown
of where time was spent.

Usage:
    uv run python -m cli.trace_view                # most recent run
    uv run python -m cli.trace_view logs/<id>.json  # a specific run
"""
from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from graph.observability import compute_timing, latest_run_log, load_run_log, walk_trace

console = Console()


def _round_label(entry: dict) -> str:
    agent = entry.get("agent", "?")
    event = entry.get("event", "?")
    round_no = entry.get("round")
    prefix = f"round {round_no} — " if round_no is not None else ""
    if agent == "coder":
        return f"{prefix}[cyan]Coder[/cyan] {event}: {entry.get('reason', '')[:80]}"
    if agent == "tester":
        status = "[green]passed[/green]" if entry.get("passed") else "[red]failed[/red]"
        return f"{prefix}[magenta]Tester[/magenta] ran tests — {status} (exit {entry.get('exit_code')})"
    if agent == "reviewer":
        return f"{prefix}[yellow]Reviewer[/yellow] verdict={entry.get('verdict')}: {entry.get('reason', '')[:80]}"
    return f"{agent}: {entry.get('event') or entry.get('decision')}"


def _macro_label(entry: dict) -> str:
    decision = entry.get("decision")
    if decision == "planner":
        return "[bold]Planner[/bold] — generated initial plan"
    if decision == "critique_loop":
        return (
            f"[bold]Critique Loop[/bold] (supervisor step {entry.get('supervisor_step')}) — "
            f"{entry.get('critique_rounds_used')} round(s), outcome={entry.get('critique_outcome')}"
        )
    if decision == "test_gate":
        status = "[green]passed[/green]" if entry.get("passed") else "[red]failed[/red]"
        return f"[bold]Test Gate[/bold] — {status}"
    if decision == "human_checkpoint":
        return f"[bold]Human Checkpoint[/bold] — decision={entry.get('human_decision')}"
    return f"[bold]{decision}[/bold]"


def render(log: dict) -> None:
    console.rule(f"[bold cyan]Run {log['run_id']}[/bold cyan]")
    console.print(f"Task: {log['task']}")
    console.print(
        f"Final: human_decision=[bold]{log.get('human_decision')}[/bold], "
        f"review_verdict={log.get('review_verdict')}, "
        f"test_passed={log.get('test_passed')}, "
        f"supervisor_steps_used={log.get('supervisor_step')}"
    )

    tree = Tree("[bold]Decision Path[/bold]")
    for section in walk_trace(log["trace"]):
        macro_node = tree.add(_macro_label(section["macro"]))
        for round_entry in section["rounds"]:
            macro_node.add(_round_label(round_entry))
    console.print(tree)

    timing = compute_timing(log["trace"])
    table = Table(title="Time Spent by Agent")
    table.add_column("Agent")
    table.add_column("Total seconds", justify="right")
    for agent, total in sorted(timing["totals_by_agent"].items(), key=lambda kv: -kv[1]):
        table.add_row(agent, f"{total:.2f}")
    console.print(table)


def main() -> None:
    if len(sys.argv) > 1:
        log_path = Path(sys.argv[1])
    else:
        log_path = latest_run_log()
        if log_path is None:
            console.print("[red]No run logs found in logs/. Run cli/main.py first.[/red]")
            return

    render(load_run_log(log_path))


if __name__ == "__main__":
    main()
