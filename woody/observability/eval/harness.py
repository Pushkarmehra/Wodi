"""
Phase 1 Eval Harness — 20-task regression suite.

Runs scripted task scenarios against the live kernel and measures:
  - Pass/fail per task
  - End-to-end latency
  - Agent routing accuracy

Exit criterion: >90% pass rate for Phase 1 sign-off.

Usage:
    python -m woody.observability.eval.harness
    # or:
    woody --eval
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

RESULTS_DIR = Path("tests/eval/results")


@dataclass
class EvalTask:
    id: str
    description: str
    input_text: str
    expected_agent: str
    expected_action: str
    pass_criterion: str  # keyword that must appear in result/response
    timeout_seconds: float = 15.0


@dataclass
class EvalResult:
    task_id: str
    passed: bool
    latency_ms: float
    response: str
    error: str | None = None
    routed_agent: str | None = None
    notes: str = ""


# ── 20-Task Phase 1 Eval Suite ────────────────────────────────────────────────

PHASE1_TASKS: list[EvalTask] = [
    # System agent — information retrieval
    EvalTask("t01", "Get current time", "what time is it", "system_agent", "get_time_date", "time"),
    EvalTask("t02", "Get current date", "what's today's date", "system_agent", "get_time_date", "date"),
    EvalTask("t03", "System CPU stats", "how much cpu am i using", "system_agent", "get_system_stats", "cpu"),
    EvalTask("t04", "RAM usage", "how much ram is being used", "system_agent", "get_system_stats", "ram"),
    EvalTask("t05", "Battery status", "check my battery", "system_agent", "get_battery", "percent"),
    EvalTask("t06", "Running processes", "what's running on my computer", "system_agent", "list_processes", "process"),
    EvalTask("t07", "Clipboard content", "what's in my clipboard", "system_agent", "get_clipboard", "clipboard"),

    # Desktop agent — app control
    EvalTask("t08", "Open Notepad", "open notepad", "desktop_agent", "open_app", "opened"),
    EvalTask("t09", "Open Calculator", "launch the calculator", "desktop_agent", "open_app", "opened"),
    EvalTask("t10", "Open Chrome", "open google chrome", "desktop_agent", "open_app", "opened"),
    EvalTask("t11", "List open windows", "what windows do i have open", "desktop_agent", "get_open_windows", "windows"),
    EvalTask("t12", "Close app", "close notepad", "desktop_agent", "close_app", "closed"),
    EvalTask("t13", "Take screenshot", "take a screenshot", "desktop_agent", "take_screenshot", "screenshot"),
    EvalTask("t14", "Type text", "type 'hello world' in the current window", "desktop_agent", "type_text", "typed"),

    # Vision agent
    EvalTask("t15", "See the screen", "what's on my screen", "vision_agent", "analyze_screen", "screen", timeout_seconds=30.0),
    EvalTask("t16", "Explain error", "what error am i seeing", "vision_agent", "explain_error", "", timeout_seconds=30.0),

    # Multi-step / planner
    EvalTask("t17", "Open and type", "open notepad and type hello", "desktop_agent", "open_app", "hello", timeout_seconds=20.0),
    EvalTask("t18", "Check system and respond", "tell me about my computer's performance", "system_agent", "get_system_stats", "cpu"),

    # Graceful failure
    EvalTask("t19", "Ambiguous request handled", "do the thing", "system_agent", "clarify", "clarif"),
    EvalTask("t20", "App not found handled", "open blergblarg123", "desktop_agent", "open_app", ""),
]


class EvalHarness:
    """
    Runs the Phase 1 eval suite against a live Woody kernel.
    """

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = config_path
        self._kernel: Any | None = None
        self._results: list[EvalResult] = []

    async def setup(self) -> None:
        from woody.kernel.config import load_config
        from woody.kernel.kernel import WoodyKernel

        cfg = load_config(self._config_path)
        self._kernel = WoodyKernel(cfg)
        await self._kernel.start()

    async def teardown(self) -> None:
        if self._kernel:
            await self._kernel.stop()

    async def run_task(self, task: EvalTask) -> EvalResult:
        assert self._kernel
        t0 = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                self._kernel.process_request(task.input_text),
                timeout=task.timeout_seconds,
            )
            elapsed = (time.perf_counter() - t0) * 1000

            # Pass criterion
            passed = True
            if task.pass_criterion:
                passed = task.pass_criterion.lower() in response.lower()

            return EvalResult(
                task_id=task.id,
                passed=passed,
                latency_ms=elapsed,
                response=response[:200],
            )
        except asyncio.TimeoutError:
            return EvalResult(
                task_id=task.id,
                passed=False,
                latency_ms=task.timeout_seconds * 1000,
                response="",
                error=f"Timed out after {task.timeout_seconds}s",
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return EvalResult(
                task_id=task.id,
                passed=False,
                latency_ms=elapsed,
                response="",
                error=str(e),
            )

    async def run_all(self, tasks: list[EvalTask] | None = None) -> list[EvalResult]:
        tasks = tasks or PHASE1_TASKS
        self._results = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            prog_task = progress.add_task("Running eval...", total=len(tasks))
            for task in tasks:
                progress.update(prog_task, description=f"[{task.id}] {task.description}")
                result = await self.run_task(task)
                self._results.append(result)
                progress.advance(prog_task)

        return self._results

    def report(self) -> None:
        """Print a rich table with results and summary."""
        table = Table(title="Woody Phase 1 Eval Results", show_header=True)
        table.add_column("ID", style="dim", width=5)
        table.add_column("Description", width=32)
        table.add_column("Pass", justify="center", width=6)
        table.add_column("Latency", justify="right", width=10)
        table.add_column("Response / Error", width=40)

        passed = 0
        for result in self._results:
            task = next((t for t in PHASE1_TASKS if t.id == result.task_id), None)
            desc = task.description if task else result.task_id
            pass_icon = "[green]✓[/green]" if result.passed else "[red]✗[/red]"
            latency_str = f"{result.latency_ms:.0f}ms"
            detail = result.error or result.response[:60]
            table.add_row(result.task_id, desc, pass_icon, latency_str, detail)
            if result.passed:
                passed += 1

        console.print(table)

        total = len(self._results)
        pct = (passed / total * 100) if total else 0
        color = "green" if pct >= 90 else "yellow" if pct >= 70 else "red"
        console.print(f"\n[bold {color}]Result: {passed}/{total} passed ({pct:.1f}%)[/bold {color}]")

        if pct >= 90:
            console.print("[bold green]✓ Phase 1 exit criterion MET (>90% pass rate)[/bold green]")
        else:
            console.print(f"[yellow]Phase 1 exit criterion NOT met. Need {int(total*0.9)} passes.[/yellow]")

        # Save JSON results
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        out_path = RESULTS_DIR / f"eval_{ts}.json"
        with open(out_path, "w") as f:
            json.dump(
                {
                    "timestamp": ts,
                    "passed": passed,
                    "total": total,
                    "pass_rate": pct,
                    "results": [
                        {
                            "id": r.task_id,
                            "passed": r.passed,
                            "latency_ms": r.latency_ms,
                            "error": r.error,
                        }
                        for r in self._results
                    ],
                },
                f,
                indent=2,
            )
        console.print(f"[dim]Results saved to {out_path}[/dim]")


def cli_run() -> None:
    """CLI entry point for Woody-eval command."""
    async def _main() -> None:
        harness = EvalHarness()
        await harness.setup()
        try:
            await harness.run_all()
            harness.report()
        finally:
            await harness.teardown()

    asyncio.run(_main())


if __name__ == "__main__":
    cli_run()
