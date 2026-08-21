"""
Wodi PySide6 Application — System tray, global hotkey, kernel lifecycle.

Manages:
  - System tray icon with context menu
  - Global hotkey (Ctrl+Space) to show/hide the orb overlay
  - Kernel startup in asyncio background thread
  - Signal bridge between Qt UI thread and asyncio kernel
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal, QObject, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from wodi.utils.logging import get_logger

log = get_logger(__name__)

# Resources directory
RESOURCES_DIR = Path(__file__).parent / "resources"


class KernelSignalBridge(QObject):
    """Qt signal bridge to safely communicate between asyncio kernel and Qt UI thread."""
    wake_detected = Signal()
    speech_started = Signal()
    response_chunk = Signal(str)
    response_complete = Signal(str)
    confirm_needed = Signal(str, dict)      # tool_name, params
    kernel_ready = Signal()
    kernel_error = Signal(str)


class WodiApp:
    """
    Top-level Wodi application object.

    Manages the Qt event loop, system tray, and kernel lifecycle.
    The kernel runs in a separate asyncio event loop on a background thread.
    """

    def __init__(self, qt_app: QApplication, config_path: str | None = None) -> None:
        self._qt_app = qt_app
        self._config_path = config_path
        self._bridge = KernelSignalBridge()
        self._tray: QSystemTrayIcon | None = None
        self._overlay: Any | None = None
        self._kernel: Any | None = None
        self._kernel_loop: asyncio.AbstractEventLoop | None = None
        self._kernel_thread: threading.Thread | None = None
        self._confirm_future: asyncio.Future | None = None

        # Wire signals (overlay manages response_chunk and response_complete directly)
        self._bridge.wake_detected.connect(self._on_wake)
        self._bridge.speech_started.connect(self._on_speech_start)
        self._bridge.kernel_ready.connect(self._on_kernel_ready)
        self._bridge.kernel_error.connect(self._on_kernel_error)

    def start(self) -> None:
        """Start the application: tray → overlay → kernel."""
        self._setup_tray()
        self._setup_overlay()
        self._setup_global_hotkey()
        self._start_kernel_thread()

    # ── System Tray ───────────────────────────────────────────────────────────

    def _setup_tray(self) -> None:
        icon = self._load_icon()
        self._tray = QSystemTrayIcon(icon, self._qt_app)
        self._tray.setToolTip("Wodi — AI Assistant")

        menu = QMenu()
        show_action = QAction("Show Wodi (Ctrl+Space)", menu)
        show_action.triggered.connect(self._toggle_overlay)
        menu.addAction(show_action)

        activity_action = QAction("Activity Log", menu)
        activity_action.triggered.connect(self._show_activity)
        menu.addAction(activity_action)

        menu.addSeparator()

        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self._show_settings)
        menu.addAction(settings_action)

        quit_action = QAction("Quit Wodi", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()
        log.info("ui.tray_ready")

    def _load_icon(self) -> QIcon:
        """Load tray icon — use a colored circle if no icon file found."""
        icon_path = RESOURCES_DIR / "wodi_tray.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        # Generate a simple colored icon programmatically
        from PySide6.QtGui import QPixmap, QPainter, QColor, QBrush
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(99, 102, 241)))  # Indigo to match new design
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.end()
        return QIcon(pixmap)

    # ── Global Hotkey ─────────────────────────────────────────────────────────

    def _setup_global_hotkey(self) -> None:
        """
        Register global hotkeys for toggling the overlay.

        Registered hotkeys:
          Ctrl+Space      — primary Wodi hotkey (legacy)
          Ctrl+Alt+Space  — secondary hotkey (from Nex prototype)

        Uses pynput for system-wide listening.
        Falls back to keyboard module if pynput is unavailable.
        """
        # Method 1: pynput (preferred)
        try:
            from pynput import keyboard

            ctrl_pressed = False

            alt_pressed  = False

            def _on_press(key: Any) -> None:
                nonlocal ctrl_pressed, alt_pressed
                try:
                    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                        ctrl_pressed = True
                    elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                        alt_pressed = True
                    elif key == keyboard.Key.space and ctrl_pressed:
                        # Ctrl+Space  OR  Ctrl+Alt+Space — both toggle the overlay
                        self._bridge.wake_detected.emit()
                except Exception:
                    pass

            def _on_release(key: Any) -> None:
                nonlocal ctrl_pressed, alt_pressed
                try:
                    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                        ctrl_pressed = False
                    elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                        alt_pressed = False
                except Exception:
                    pass

            listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
            listener.daemon = True
            listener.start()
            log.info("ui.hotkey_registered", hotkey="Ctrl+Space", method="pynput")
            return
        except ImportError:
            log.info("ui.pynput_not_found", fallback="keyboard_module")
        except Exception as e:
            log.warning("ui.pynput_failed", error=str(e))

        # Method 2: keyboard module
        try:
            import keyboard as kb

            def _on_hotkey() -> None:
                self._bridge.wake_detected.emit()

            kb.add_hotkey('ctrl+space', _on_hotkey, suppress=False)
            log.info("ui.hotkey_registered", hotkey="Ctrl+Space", method="keyboard")
            return
        except ImportError:
            log.warning("ui.keyboard_not_found")
        except Exception as e:
            log.warning("ui.keyboard_failed", error=str(e))

        log.warning(
            "ui.no_global_hotkey",
            hint="Install pynput or keyboard: pip install pynput",
        )

    # ── Overlay ───────────────────────────────────────────────────────────────

    def _setup_overlay(self) -> None:
        # Ensure resources directory exists
        RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
        from wodi.ui.overlay import WodiOverlay
        self._overlay = WodiOverlay(bridge=self._bridge, submit_callback=self.submit_text)

    def _toggle_overlay(self) -> None:
        if self._overlay:
            self._overlay.toggle()

    # ── Kernel Thread ─────────────────────────────────────────────────────────

    def _start_kernel_thread(self) -> None:
        """Start the Wodi kernel on a background asyncio thread."""
        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._kernel_loop = loop
            try:
                loop.run_until_complete(self._kernel_main())
            finally:
                loop.close()

        self._kernel_thread = threading.Thread(
            target=_run, daemon=True, name="wodi-kernel"
        )
        self._kernel_thread.start()

    async def _kernel_main(self) -> None:
        """Async kernel lifecycle running on the background thread."""
        from wodi.kernel.config import load_config
        from wodi.kernel.kernel import WodiKernel

        cfg = load_config(self._config_path)

        self._kernel = WodiKernel(cfg)
        self._kernel.set_wake_word_callback(lambda: self._bridge.wake_detected.emit())
        self._kernel.set_speech_start_callback(lambda: self._bridge.speech_started.emit())
        self._kernel.set_confirm_callback(self._async_confirm)

        try:
            await self._kernel.start()
            self._bridge.kernel_ready.emit()

            # Keep alive until Qt closes
            while True:
                await asyncio.sleep(1)
        except Exception as e:
            log.error("kernel.fatal", error=str(e))
            self._bridge.kernel_error.emit(str(e))
        finally:
            if self._kernel:
                await self._kernel.stop()

    async def _async_confirm(self, tool_name: str, params: dict) -> bool:
        """Bridge: emit confirmation request to Qt UI, await user response."""
        loop = asyncio.get_event_loop()
        self._confirm_future = loop.create_future()
        self._bridge.confirm_needed.emit(tool_name, params)
        try:
            return await asyncio.wait_for(self._confirm_future, timeout=30.0)
        except asyncio.TimeoutError:
            return False

    def resolve_confirm(self, approved: bool) -> None:
        """Called by UI when user approves/denies a confirmation card."""
        if self._confirm_future and not self._confirm_future.done():
            if self._kernel_loop:
                self._kernel_loop.call_soon_threadsafe(
                    self._confirm_future.set_result, approved
                )

    def submit_text(self, text: str) -> None:
        """Submit a text command to the kernel from the UI."""
        if self._kernel and self._kernel_loop:
            async def _process() -> None:
                response = await self._kernel.process_request(
                    text,
                    on_response_chunk=lambda chunk: self._bridge.response_chunk.emit(chunk),
                )
                self._bridge.response_complete.emit(response)

            asyncio.run_coroutine_threadsafe(_process(), self._kernel_loop)

    # ── Qt Slots ──────────────────────────────────────────────────────────────

    @Slot()
    def _on_wake(self) -> None:
        """Wake word / hotkey detected — TOGGLE overlay (open if closed, close if open)."""
        log.info("ui.wake_toggle")
        if self._overlay:
            self._overlay.toggle()

    @Slot()
    def _on_speech_start(self) -> None:
        if self._overlay:
            self._overlay.set_state("listening")

    @Slot(str)
    def _on_response_chunk(self, chunk: str) -> None:
        if self._overlay:
            self._overlay.append_caption(chunk)

    @Slot(str)
    def _on_response_complete(self, response: str) -> None:
        if self._overlay:
            self._overlay.set_state("idle")

    @Slot()
    def _on_kernel_ready(self) -> None:
        log.info("ui.kernel_ready")
        if self._tray:
            self._tray.showMessage(
                "Wodi Ready",
                "Say 'Hey Jarvis' or press Ctrl+Space",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    @Slot(str)
    def _on_kernel_error(self, error: str) -> None:
        log.error("ui.kernel_error", error=error)
        if self._tray:
            self._tray.showMessage(
                "Wodi Error",
                f"Kernel error: {error[:100]}",
                QSystemTrayIcon.MessageIcon.Critical,
                5000,
            )

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_overlay()

    def _show_activity(self) -> None:
        log.info("ui.show_activity")  # TODO: open ActivityPanel

    def _show_settings(self) -> None:
        log.info("ui.show_settings")  # TODO: open SettingsDialog

    def _quit(self) -> None:
        log.info("ui.quit")
        if self._kernel and self._kernel_loop:
            asyncio.run_coroutine_threadsafe(self._kernel.stop(), self._kernel_loop)
        self._qt_app.quit()


# ── Web-UI mode (FastAPI + WebEngine overlay) ─────────────────────────────────

def start_web_ui_mode(port: int | None = None, config_path: str | None = None) -> None:
    """
    Start Wodi in Web-UI mode.

    1. Launches the WodiKernel on a background asyncio thread (if Ollama is
       available) so local tool execution still works.
    2. Starts the FastAPI SSE backend server on a daemon thread.
    3. Launches the WebEngine overlay (slide/fade animations, OLED HTML UI).

    This mode supports both cloud (Gemini/Groq) and local (Ollama) providers
    and renders the UI using the HTML/CSS/JS renderer in wodi/ui/renderer/.
    """
    import threading
    import time

    from wodi.utils.llm_factory import get_backend_port
    from wodi.ipc.fastapi_server import serve as _serve_fastapi
    from wodi.ui.web_overlay import start_web_overlay

    _port = port or get_backend_port()

    # Start FastAPI backend daemon thread
    server_thread = threading.Thread(
        target=_serve_fastapi,
        args=(_port,),
        daemon=True,
        name="wodi-fastapi",
    )
    server_thread.start()
    log.info("ui.web_mode.server_started", port=_port)

    # Brief wait for uvicorn to bind
    time.sleep(0.8)

    # Launch WebEngine overlay (blocking — runs Qt event loop)
    start_web_overlay(server_url=f"http://127.0.0.1:{_port}/")

