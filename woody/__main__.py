"""
Woody CLI entry point.

Usage:
    woody                  # Start full Woody (kernel + native UI)
    woody --web-ui         # Start with WebEngine HTML overlay + FastAPI
    woody --serve          # Start FastAPI backend only (headless REST/SSE)
    woody --kernel-only    # Start kernel without any UI (headless/REPL mode)
    woody --eval           # Run the Phase 1 eval suite
    woody --version        # Print version
    woody --port 8765      # Override backend port (for --web-ui and --serve)
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

from woody import __version__

console = Console()


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Print version and exit.")
@click.option("--kernel-only", is_flag=True, help="Start kernel without GUI.")
@click.option("--web-ui", is_flag=True, help="Start with WebEngine overlay + FastAPI backend.")
@click.option("--pet", is_flag=True, help="Start animated AI Desktop Pet companion.")
@click.option("--serve", is_flag=True, help="Start FastAPI backend only (headless REST/SSE mode).")
@click.option("--eval", "run_eval", is_flag=True, help="Run the eval harness.")
@click.option("--port", default=None, type=int, help="Override backend port (default: 8765).")
@click.option(
    "--config",
    default=None,
    help="Path to woody_config.yaml (default: config/woody_config.yaml).",
)
@click.pass_context
def main(
    ctx: click.Context,
    version: bool,
    kernel_only: bool,
    web_ui: bool,
    pet: bool,
    serve: bool,
    run_eval: bool,
    port: int | None,
    config: str | None,
) -> None:
    """Woody — Local-First Windows AI Operating System Layer."""
    if version:
        console.print(f"[bold cyan]Woody[/bold cyan] v{__version__}")
        sys.exit(0)

    if run_eval:
        from woody.observability.eval.harness import cli_run
        cli_run()
        return

    # ── Desktop AI Pet Mode ──
    if pet:
        from woody.ui.desktop_pet import run_pet
        _port = port or 8765
        run_pet(server_url=f"http://127.0.0.1:{_port}")
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
        from woody.kernel.kernel import start_kernel_only
        asyncio.run(start_kernel_only(config_path=config))
        return

    # ── Default: full native application (kernel + PySide6 overlay) ──
    if ctx.invoked_subcommand is None:
        _start_full(config_path=config)


def _start_full(config_path: str | None) -> None:
    """Start the complete Woody application with native Qt overlay."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        console.print(
            "[bold red]PySide6 not found.[/bold red] Install it with:\n"
            "  pip install PySide6\n"
            "Or start in kernel-only mode: woody --kernel-only\n"
            "Or try the web UI mode: woody --web-ui"
        )
        sys.exit(1)

    from woody.ui.app import WoodyApp

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Woody")
    qt_app.setApplicationVersion(__version__)
    qt_app.setQuitOnLastWindowClosed(False)

    woody_app = WoodyApp(qt_app, config_path=config_path)
    woody_app.start()

    sys.exit(qt_app.exec())


def _start_web_ui(port: int | None = None, config_path: str | None = None) -> None:
    """Start Woody with WebEngine overlay + FastAPI backend."""
    console.print(
        "[bold cyan]Woody[/bold cyan] starting in [bold]Web-UI[/bold] mode "
        "(FastAPI + WebEngine overlay)..."
    )
    try:
        from woody.ui.app import start_web_ui_mode
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
        "[bold cyan]Woody[/bold cyan] starting in [bold]serve[/bold] mode "
        "(FastAPI backend only)..."
    )
    try:
        from woody.ipc.fastapi_server import serve
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
