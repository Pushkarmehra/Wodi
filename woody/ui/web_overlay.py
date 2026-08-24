"""
Woody WebEngine Overlay — PySide6 QWebEngineView window serving the OLED HTML UI.

Ported from the Nex prototype's NexMainWindow (gui/app.py) and integrated into
the Woody application layer. Uses the FastAPI SSE backend via localhost.

Features:
  - Frameless, always-on-top window
  - Smooth slide + fade show/hide animations (QPropertyAnimation group)
  - Geometry expand/collapse animation (for response panel growth)
  - Title-channel IPC: document.title → action:hide / expand / collapse
  - Ctrl+Alt+Space  — toggle window (primary hotkey, from prototype)
  - Ctrl+Space      — toggle window (legacy Woody hotkey)
  - Ctrl+/          — jump to input box focus
"""
from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import (
    Qt, QUrl, Signal, QObject, Slot,
    QPropertyAnimation, QEasingCurve,
    QPoint, QRect, QParallelAnimationGroup,
)
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QBrush
from PySide6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
from PySide6.QtWebEngineWidgets import QWebEngineView

log = logging.getLogger("WoodyWebOverlay")

# Animation constants
ANIM_SHOW_MS  = 300
ANIM_HIDE_MS  = 200
SLIDE_PX      = 22       # pixels the window travels during show/hide
WIN_WIDTH     = 680
WIN_HEIGHT    = 62       # compact (input bar only)
WIN_HEIGHT_EX = 260      # expanded (response panel visible)
BOTTOM_MARGIN = 40       # pixels above taskbar


class HotkeySignaler(QObject):
    """Thread-safe Qt signal bridge for global hotkey callbacks."""
    activate_requested = Signal()   # toggle: Ctrl+Alt+Space or Ctrl+Space
    focus_requested    = Signal()   # jump to input: Ctrl+/


class WoodyWebOverlay(QMainWindow):
    """
    Frameless WebEngine window hosting the Woody OLED HTML interface.

    Communicates with the renderer via:
      - URL: serves content from the Woody FastAPI backend
      - Title IPC: JS sets document.title to "action:hide", "action:expand", etc.
    """

    def __init__(self, server_url: str = "http://127.0.0.1:8765/") -> None:
        super().__init__()
        self.server_url  = server_url
        self._animating  = False
        self._showing    = False

        # ── Window flags ──────────────────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # ── Geometry ──────────────────────────────────────────────────────────
        self._compact_h  = WIN_HEIGHT
        self._expanded_h = WIN_HEIGHT_EX
        self._cur_height = WIN_HEIGHT
        self.resize(WIN_WIDTH, WIN_HEIGHT)
        self.setWindowOpacity(0.0)

        # ── WebEngine ─────────────────────────────────────────────────────────
        self.web_view = QWebEngineView(self)
        self.web_view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.web_view.setUrl(QUrl(self.server_url))
        self.web_view.titleChanged.connect(self._on_title_changed)
        self.setCentralWidget(self.web_view)

        # ── Opacity animation ─────────────────────────────────────────────────
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # ── Slide (position) animation ────────────────────────────────────────
        self._slide_anim = QPropertyAnimation(self, b"pos", self)

        # ── Geometry expand/collapse animation ────────────────────────────────
        self._expand_anim = QPropertyAnimation(self, b"geometry", self)
        self._expand_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._expand_anim.setDuration(260)

        # ── Parallel group (fade + slide together) ────────────────────────────
        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(self._fade_anim)
        self._anim_group.addAnimation(self._slide_anim)
        self._anim_group.finished.connect(self._on_anim_finished)

    # ── Title-channel IPC ─────────────────────────────────────────────────────

    def _on_title_changed(self, title: str) -> None:
        """Handle document.title actions emitted by the JS renderer."""
        if "action:hide" in title:
            self.hide_window()
            self.web_view.page().runJavaScript("document.title = 'Woody';")
        elif "action:expand" in title:
            self._expand_window()
            self.web_view.page().runJavaScript("document.title = 'Woody';")
        elif "action:collapse" in title:
            self._collapse_window()
            self.web_view.page().runJavaScript("document.title = 'Woody';")

    # ── Focus input ───────────────────────────────────────────────────────────

    @Slot()
    def focus_input(self) -> None:
        """Show window and jump focus directly to the input box."""
        if not self.isVisible() or not self._showing:
            self.show_window()
        else:
            self.activateWindow()
            self.raise_()
        self.web_view.setFocus()
        self.web_view.page().runJavaScript(
            "if (window.nexFocusInput) window.nexFocusInput();"
        )

    # ── Expand / Collapse ─────────────────────────────────────────────────────

    def _expand_window(self) -> None:
        """Animate height from 62px → expanded height, bottom edge fixed."""
        if self._cur_height != self._expanded_h:
            self._cur_height = self._expanded_h
            self._animate_geometry(self._expanded_h)

    def _collapse_window(self) -> None:
        """Animate height from expanded → 62px compact, bottom edge fixed."""
        if self._cur_height != self._compact_h:
            self._cur_height = self._compact_h
            self._animate_geometry(self._compact_h)

    def _animate_geometry(self, target_h: int) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x   = (geo.width() - WIN_WIDTH) // 2
        start_rect = self.geometry()
        end_rect   = QRect(x, geo.height() - target_h - BOTTOM_MARGIN, WIN_WIDTH, target_h)
        self._expand_anim.stop()
        self._expand_anim.setStartValue(start_rect)
        self._expand_anim.setEndValue(end_rect)
        self._expand_anim.start()

    # ── Rest / Hidden positions ───────────────────────────────────────────────

    def _rest_pos(self) -> QPoint:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - WIN_WIDTH) // 2
            y = geo.height() - self._cur_height - BOTTOM_MARGIN
            return QPoint(x, y)
        return QPoint(0, 0)

    def _hidden_pos(self) -> QPoint:
        p = self._rest_pos()
        return QPoint(p.x(), p.y() + SLIDE_PX)

    # ── Toggle / Show / Hide ──────────────────────────────────────────────────

    @Slot()
    def toggle_window(self) -> None:
        if self._animating:
            return
        if self.isVisible() and self._showing:
            self.hide_window()
        else:
            self.show_window()

    def show_window(self) -> None:
        if self._animating:
            return
        self._showing   = True
        self._animating = True

        start = self._hidden_pos()
        end   = self._rest_pos()
        self.move(start)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        self._fade_anim.setDuration(ANIM_SHOW_MS)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)

        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide_anim.setDuration(ANIM_SHOW_MS)
        self._slide_anim.setStartValue(start)
        self._slide_anim.setEndValue(end)

        self._anim_group.start()

    def hide_window(self) -> None:
        if self._animating:
            return
        self._showing   = False
        self._animating = True

        start = self._rest_pos()
        end   = self._hidden_pos()

        self._fade_anim.setDuration(ANIM_HIDE_MS)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)

        self._slide_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._slide_anim.setDuration(ANIM_HIDE_MS)
        self._slide_anim.setStartValue(start)
        self._slide_anim.setEndValue(end)

        self._anim_group.start()

    def _on_anim_finished(self) -> None:
        self._animating = False
        if not self._showing:
            self.hide()
            self._collapse_window()
        else:
            self.activateWindow()
            self.web_view.page().runJavaScript(
                "if (window.nexFocusInput) window.nexFocusInput();"
            )


# ── Tray icon factory ─────────────────────────────────────────────────────────

def _make_tray_icon() -> QIcon:
    """Generate a Woody indigo circle tray icon."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Outer glow ring
    painter.setBrush(QBrush(QColor(99, 102, 241, 55)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    # Main circle
    painter.setBrush(QBrush(QColor(99, 102, 241)))
    painter.drawEllipse(6, 6, 20, 20)
    # Center spark
    painter.setBrush(QBrush(QColor(255, 255, 255)))
    painter.drawEllipse(13, 13, 6, 6)
    painter.end()
    return QIcon(pixmap)


# ── Public entry point ────────────────────────────────────────────────────────

def start_web_overlay(server_url: str = "http://127.0.0.1:8765/") -> None:
    """
    Launch the Woody WebEngine overlay as a standalone PySide6 application.

    Registers hotkeys:
      Ctrl+Alt+Space — toggle window
      Ctrl+/         — focus input box
    """
    from pynput import keyboard  # type: ignore

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = WoodyWebOverlay(server_url=server_url)

    signaler = HotkeySignaler()
    signaler.activate_requested.connect(window.toggle_window)
    signaler.focus_requested.connect(window.focus_input)

    # Dual hotkey: Ctrl+Alt+Space (prototype) + Ctrl+/ (focus)
    hotkeys = {
        "<ctrl>+<alt>+<space>": lambda: signaler.activate_requested.emit(),
        "<ctrl>+/":             lambda: signaler.focus_requested.emit(),
    }

    try:
        listener = keyboard.GlobalHotKeys(hotkeys)
        listener.start()
        log.info("Hotkeys registered: Ctrl+Alt+Space | Ctrl+/")
    except Exception as exc:
        log.warning(f"Could not register hotkeys: {exc}")

    tray = QSystemTrayIcon(_make_tray_icon(), app)
    menu = QMenu()
    menu.addAction("Toggle Woody (Ctrl+Alt+Space)").triggered.connect(window.toggle_window)
    menu.addAction("Focus Input (Ctrl+/)").triggered.connect(window.focus_input)
    menu.addSeparator()
    menu.addAction("Quit Woody").triggered.connect(lambda: os._exit(0))
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda r: window.toggle_window()
        if r == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray.setToolTip("Woody AI — Ctrl+Alt+Space")
    tray.show()

    sys.exit(app.exec())
