"""
Wodi CLI entry point.

Usage:
    wodi                  # Start full Wodi (kernel + UI)
    wodi --kernel-only    # Start kernel without UI (headless/server mode)
    wodi --eval           # Run the Phase 1 eval suite
    wodi --version        # Print version
"""
from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console

from wodi import __version__

console = Console()


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Print version and exit.")
@click.option("--kernel-only", is_flag=True, help="Start kernel without GUI.")
@click.option("--eval", "run_eval", is_flag=True, help="Run the eval harness.")
@click.option(
    "--config",
    default=None,
    help="Path to wodi_config.yaml (default: config/wodi_config.yaml).",
)
@click.pass_context
def main(ctx: click.Context, version: bool, kernel_only: bool, run_eval: bool, config: str | None) -> None:
    """Wodi — Local-First Windows AI Operating System Layer."""
    if version:
        console.print(f"[bold cyan]Wodi[/bold cyan] v{__version__}")
        sys.exit(0)

    if run_eval:
        from wodi.observability.eval.harness import cli_run
        cli_run()
        return

    if kernel_only:
        from wodi.kernel.kernel import start_kernel_only
        asyncio.run(start_kernel_only(config_path=config))
        return

    # Default: start full application (kernel + PySide6 UI)
    if ctx.invoked_subcommand is None:
        _start_full(config_path=config)


def _start_full(config_path: str | None) -> None:
    """Start the complete Wodi application with GUI."""
    import os

    # PySide6 must be imported on the main thread before asyncio starts.
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        console.print(
            "[bold red]PySide6 not found.[/bold red] Install it with:\n"
            "  pip install PySide6\n"
            "Or start in kernel-only mode: wodi --kernel-only"
        )
        sys.exit(1)

    from wodi.ui.app import WodiApp

    # Qt requires sys.argv to be passed
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Wodi")
    qt_app.setApplicationVersion(__version__)
    qt_app.setQuitOnLastWindowClosed(False)

    wodi_app = WodiApp(qt_app, config_path=config_path)
    wodi_app.start()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
