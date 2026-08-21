"""
Wodi CLI entry point.

Usage:
    wodi                  # Start full Wodi (kernel + native UI)
    wodi --web-ui         # Start with WebEngine HTML overlay + FastAPI
    wodi --serve          # Start FastAPI backend only (headless REST/SSE)
    wodi --kernel-only    # Start kernel without any UI (headless/REPL mode)
    wodi --eval           # Run the Phase 1 eval suite
    wodi --version        # Print version
    wodi --port 8765      # Override backend port (for --web-ui and --serve)
"""
from __future__ import annotations

import asyncio
import os
import sys

# ── Auto-switch to project virtual environment (.venv) ──
# Ported from the Nex prototype launcher — ensures the correct venv
# is active even when launched from a shortcut or system tray.
_VENV_WIN  = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".venv", "Scripts", "python.exe"))
_VENV_UNIX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".venv", "bin", "python"))
_VENV_PYTHON = _VENV_WIN if os.name == "nt" else _VENV_UNIX

if os.path.exists(_VENV_PYTHON) and os.path.normcase(sys.executable) != os.path.normcase(_VENV_PYTHON):
    os.execv(_VENV_PYTHON, [_VENV_PYTHON] + sys.argv)

import click
from rich.console import Console

from wodi import __version__

console = Console()


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Print version and exit.")
@click.option("--kernel-only", is_flag=True, help="Start kernel without GUI.")
@click.option("--web-ui", is_flag=True, help="Start with WebEngine overlay + FastAPI backend.")
@click.option("--serve", is_flag=True, help="Start FastAPI backend only (headless REST/SSE mode).")
@click.option("--eval", "run_eval", is_flag=True, help="Run the eval harness.")
@click.option("--port", default=None, type=int, help="Override backend port (default: 8765).")
@click.option(
    "--config",
    default=None,
    help="Path to wodi_config.yaml (default: config/wodi_config.yaml).",
)
@click.pass_context
def main(
    ctx: click.Context,
    version: bool,
    kernel_only: bool,
    web_ui: bool,
    serve: bool,
    run_eval: bool,
    port: int | None,
    config: str | None,
) -> None:
    """Wodi — Local-First Windows AI Operating System Layer."""
    if version:
        console.print(f"[bold cyan]Wodi[/bold cyan] v{__version__}")
        sys.exit(0)

    if run_eval:
        from wodi.observability.eval.harness import cli_run
        cli_run()
        return

    # ── Serve-only mode (FastAPI backend, no GUI) ──
    if serve:
        _start_serve(port=port)
        return

    # ── Web-UI mode (FastAPI + WebEngine overlay) ──
    if web_ui:
        _start_web_ui(port=port, config_path=config)
        return

    # ── Kernel-only mode (headless REPL) ──
    if kernel_only:
        from wodi.kernel.kernel import start_kernel_only
        asyncio.run(start_kernel_only(config_path=config))
        return

    # ── Default: full native application (kernel + PySide6 overlay) ──
    if ctx.invoked_subcommand is None:
        _start_full(config_path=config)


def _start_full(config_path: str | None) -> None:
    """Start the complete Wodi application with native Qt overlay."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        console.print(
            "[bold red]PySide6 not found.[/bold red] Install it with:\n"
            "  pip install PySide6\n"
            "Or start in kernel-only mode: wodi --kernel-only\n"
            "Or try the web UI mode: wodi --web-ui"
        )
        sys.exit(1)

    from wodi.ui.app import WodiApp

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Wodi")
    qt_app.setApplicationVersion(__version__)
    qt_app.setQuitOnLastWindowClosed(False)

    wodi_app = WodiApp(qt_app, config_path=config_path)
    wodi_app.start()

    sys.exit(qt_app.exec())


def _start_web_ui(port: int | None = None, config_path: str | None = None) -> None:
    """Start Wodi with WebEngine overlay + FastAPI backend."""
    console.print(
        "[bold cyan]Wodi[/bold cyan] starting in [bold]Web-UI[/bold] mode "
        "(FastAPI + WebEngine overlay)..."
    )
    try:
        from wodi.ui.app import start_web_ui_mode
        start_web_ui_mode(port=port, config_path=config_path)
    except ImportError as e:
        console.print(f"[bold red]Missing dependency:[/bold red] {e}")
        console.print(
            "Install required packages:\n"
            "  pip install fastapi uvicorn sse-starlette PySide6 pynput\n"
            "  pip install langchain langgraph langchain-core"
        )
        sys.exit(1)


def _start_serve(port: int | None = None) -> None:
    """Start FastAPI backend only (no GUI)."""
    console.print(
        "[bold cyan]Wodi[/bold cyan] starting in [bold]serve[/bold] mode "
        "(FastAPI backend only)..."
    )
    try:
        from wodi.ipc.fastapi_server import serve
        serve(port=port)
    except ImportError as e:
        console.print(f"[bold red]Missing dependency:[/bold red] {e}")
        console.print(
            "Install required packages:\n"
            "  pip install fastapi uvicorn sse-starlette"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
