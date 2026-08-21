import sys
import os
import signal

# ── Auto-switch to project virtual environment (.venv) ──
_VENV_WIN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv", "Scripts", "python.exe"))
_VENV_UNIX = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv", "bin", "python"))
_VENV_PYTHON = _VENV_WIN if os.name == "nt" else _VENV_UNIX

if os.path.exists(_VENV_PYTHON) and os.path.normcase(sys.executable) != os.path.normcase(_VENV_PYTHON):
    os.execv(_VENV_PYTHON, [_VENV_PYTHON] + sys.argv)

import time
import threading
import uvicorn

from src.backend.server import app as fastapi_app
from src.backend.config import get_backend_port
from src.gui.app import start_pyside_gui


def run_server(port: int):
    config = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    server.run()


def main():
    # Handle Ctrl+C (SIGINT) to terminate instantly without hanging
    def signal_handler(sig, frame):
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    port = get_backend_port()

    # Start FastAPI backend in a background daemon thread
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    # Allow FastAPI backend a brief moment to initialize
    time.sleep(0.8)

    # Launch PySide6 GUI
    try:
        start_pyside_gui(server_url=f"http://127.0.0.1:{port}/")
    except KeyboardInterrupt:
        os._exit(0)


if __name__ == "__main__":
    main()

