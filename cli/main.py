"""CLI entry point: runs the supervisor graph on a task and drives the
human-in-the-loop checkpoint interactively."""
from __future__ import annotations

import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from graph.observability import save_run_log
from graph.supervisor import SupervisorSession, run_supervisor

load_dotenv()
console = Console()


def _present_checkpoint(payload: dict) -> None:
    console.rule("[bold cyan]Human-in-the-Loop Checkpoint[/bold cyan]")
    console.print(
        f"Supervisor step [bold]{payload['supervisor_step']}[/bold]"
        f" / {payload['supervisor_max_steps']}"
    )

    console.print(Panel(Syntax(payload["code"], "python", theme="ansi_dark"), title="Final Code"))

    test_result = payload["test_result"]
    status = "[green]PASSED[/green]" if test_result["passed"] else "[red]FAILED[/red]"
    console.print(Panel(
        f"Status: {status}\nExit code: {test_result['exit_code']}\n\n"
        f"stdout:\n{test_result['stdout']}\n\nstderr:\n{test_result['stderr']}",
        title="Test Result",
    ))

    console.print(Panel(
        f"Verdict: [bold]{payload['review_verdict']}[/bold]\n\n{payload['review_feedback']}",
        title="Reviewer's Final Verdict",
    ))

    console.print(Panel(
        "\n\n".join(
            f"Round {h['round_number']} — {h['verdict']}: {h['reviewer_feedback']}"
            for h in payload["critique_history"]
        ) or "(no critique rounds — approved immediately)",
        title="Critique-Loop History",
    ))


def _prompt_decision() -> tuple[str, str | None]:
    while True:
        raw = console.input("\n[bold]Approve or reject?[/bold] (a/r): ").strip().lower()
        if raw in ("a", "approve"):
            return "approve", None
        if raw in ("r", "reject"):
            feedback = console.input("Feedback for the Coder: ").strip()
            return "reject", feedback
        console.print("[yellow]Please type 'a' (approve) or 'r' (reject).[/yellow]")


def main() -> None:
    task = " ".join(sys.argv[1:]).strip()
    if not task:
        task = console.input("[bold]Describe the coding task:[/bold] ").strip()
    if not task:
        console.print("[red]No task given, exiting.[/red]")
        return

    session, state = run_supervisor(task)

    while SupervisorSession.is_paused(state):
        payload = SupervisorSession.interrupt_payload(state)
        _present_checkpoint(payload)
        decision, feedback = _prompt_decision()
        state = session.resume(decision=decision, feedback=feedback)

    console.rule("[bold green]Done[/bold green]")
    console.print(f"Final human decision: [bold]{state['human_decision']}[/bold]")
    console.print(f"Total supervisor steps used: {state['supervisor_step']}")
    console.print(Panel(Syntax(state["code"], "python", theme="ansi_dark"), title="Delivered Code"))

    log_path = save_run_log(session.thread_id, state, task)
    console.print(f"\nTrace saved to [bold]{log_path}[/bold] — view with:")
    console.print(f"  uv run python -m cli.trace_view {log_path}")


if __name__ == "__main__":
    main()
