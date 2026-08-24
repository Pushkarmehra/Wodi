"""
Nex PySide6 Desktop Overlay — Input bar GUI.
Controls:
- Ctrl + Alt + Space: Toggle / Activate Nex window
- Ctrl + /: Directly jump to and focus the prompt input box
"""

import sys
import os
import logging
from PySide6.QtCore import (
    Qt, QUrl, Signal, QObject, Slot,
    QPropertyAnimation, QEasingCurve, QPoint, QRect, QParallelAnimationGroup,
)
from PySide6.QtGui import QIcon, QColor, QPixmap, QPainter, QBrush
from PySide6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
from PySide6.QtWebEngineWidgets import QWebEngineView
from pynput import keyboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NexGUI")

# ── Animation constants ──
ANIM_SHOW_MS = 300
ANIM_HIDE_MS = 200
SLIDE_PX     = 24   # px the bar travels during show/hide


class HotkeySignaler(QObject):
    activate_requested = Signal()  # Ctrl + Alt + Space
    focus_requested    = Signal()  # Ctrl + /


class NexMainWindow(QMainWindow):
    def __init__(self, server_url: str = "http://127.0.0.1:8000/"):
        super().__init__()
        self.server_url = server_url
        self._animating = False
        self._showing   = False

        # ── Window flags ──
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # ── Dimensions ──
        self.win_width  = 660
        self.win_height = 62
        self.resize(self.win_width, self.win_height)
        self.setWindowOpacity(0.0)

        # ── WebEngine ──
        self.web_view = QWebEngineView(self)
        self.web_view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.web_view.setUrl(QUrl(self.server_url))
        self.web_view.titleChanged.connect(self._on_title_changed)
        self.setCentralWidget(self.web_view)

        # ── Opacity animation ──
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # ── Position animation ──
        self._slide_anim = QPropertyAnimation(self, b"pos", self)

        # ── Geometry expansion animation ──
        self._expand_anim = QPropertyAnimation(self, b"geometry", self)
        self._expand_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._expand_anim.setDuration(260)

        # ── Parallel group ──
        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(self._fade_anim)
        self._anim_group.addAnimation(self._slide_anim)
        self._anim_group.finished.connect(self._on_finished)

    # ── IPC Title listener ──────────────────────────────────────────────────

    def _on_title_changed(self, title: str):
        if "action:hide" in title:
            self.hide_window()
            self.web_view.page().runJavaScript("document.title = 'Nex';")
        elif "action:expand" in title:
            self.expand_window()
            self.web_view.page().runJavaScript("document.title = 'Nex';")
        elif "action:collapse" in title:
            self.collapse_window()
            self.web_view.page().runJavaScript("document.title = 'Nex';")

    # ── Jump & Focus Input ──────────────────────────────────────────────────

    @Slot()
    def focus_input(self):
        """Shows/raises window and jumps directly to input box."""
        if not self.isVisible() or not self._showing:
            self.show_window()
        else:
            self.activateWindow()
            self.raise_()
        self.web_view.setFocus()
        self.web_view.page().runJavaScript("if (window.nexFocusInput) window.nexFocusInput();")

    # ── Window Size Expansion / Collapse ────────────────────────────────────

    def expand_window(self):
        """Expands window height to 220px to show output smoothly, keeping bottom edge fixed."""
        if self.win_height != 220:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                x = (geo.width() - self.win_width) // 2
                start_rect = self.geometry()
                end_rect = QRect(x, geo.height() - 220 - 40, self.win_width, 220)

                self.win_height = 220
                self._expand_anim.stop()
                self._expand_anim.setStartValue(start_rect)
                self._expand_anim.setEndValue(end_rect)
                self._expand_anim.start()

    def collapse_window(self):
        """Collapses window height back to 62px single-bar mode smoothly."""
        if self.win_height != 62:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                x = (geo.width() - self.win_width) // 2
                start_rect = self.geometry()
                end_rect = QRect(x, geo.height() - 62 - 40, self.win_width, 62)

                self.win_height = 62
                self._expand_anim.stop()
                self._expand_anim.setStartValue(start_rect)
                self._expand_anim.setEndValue(end_rect)
                self._expand_anim.start()

    def _rest_pos(self) -> QPoint:
        """Bottom-center resting position."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.win_width) // 2
            y = geo.height() - self.win_height - 40
            return QPoint(x, y)
        return QPoint(0, 0)

    def _hidden_pos(self) -> QPoint:
        """Slightly below resting — just enough for a natural slide."""
        p = self._rest_pos()
        return QPoint(p.x(), p.y() + SLIDE_PX)

    # ── Toggle ──────────────────────────────────────────────────────────────

    @Slot()
    def toggle_window(self):
        if self._animating:
            return
        if self.isVisible() and self._showing:
            self.hide_window()
        else:
            self.show_window()

    # ── Show ─────────────────────────────────────────────────────────────────

    def show_window(self):
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

    # ── Hide ─────────────────────────────────────────────────────────────────

    def hide_window(self):
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

    def _on_finished(self):
        self._animating = False
        if not self._showing:
            self.hide()
            self.collapse_window()
        else:
            self.activateWindow()


# ── Sleek Cyber Cyan Tray Icon ──────────────────────────────────────────────

def create_tray_icon() -> QIcon:
    logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../renderer/assets/logo.png"))
    if os.path.exists(logo_path):
        return QIcon(logo_path)

    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Outer cyan glow ring
    painter.setBrush(QBrush(QColor(6, 182, 212, 60)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 28, 28)

    # Main Cyan Circle
    painter.setBrush(QBrush(QColor(6, 182, 212)))
    painter.drawEllipse(6, 6, 20, 20)

    # Center white spark dot
    painter.setBrush(QBrush(QColor(255, 255, 255)))
    painter.drawEllipse(13, 13, 6, 6)

    painter.end()
    return QIcon(pixmap)


# ── Entry point ──────────────────────────────────────────────────────────────

def start_pyside_gui(server_url: str = "http://127.0.0.1:8000/"):
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = NexMainWindow(server_url=server_url)

    signaler = HotkeySignaler()
    signaler.activate_requested.connect(window.toggle_window)
    signaler.focus_requested.connect(window.focus_input)

    # Only 2 hotkeys: Ctrl + Alt + Space (activate) & Ctrl + / (jump to input)
    hotkey_mapping = {
        '<ctrl>+<alt>+<space>': lambda: signaler.activate_requested.emit(),
        '<ctrl>+/':             lambda: signaler.focus_requested.emit(),
    }

    try:
        listener = keyboard.GlobalHotKeys(hotkey_mapping)
        listener.start()
        logger.info("Registered Hotkeys: Ctrl+Alt+Space (Activate) | Ctrl+/ (Jump to Input)")
    except Exception as e:
        logger.warning(f"Could not register hotkeys: {e}")

    tray = QSystemTrayIcon(create_tray_icon(), app)
    menu  = QMenu()
    menu.addAction("Activate Nex (Ctrl+Alt+Space)").triggered.connect(window.toggle_window)
    menu.addAction("Focus Input Box (Ctrl+/)").triggered.connect(window.focus_input)
    menu.addSeparator()
    menu.addAction("Quit Nex").triggered.connect(lambda: os._exit(0))
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda r: window.toggle_window()
        if r == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray.setToolTip("Nex AI Agent — Ctrl+Alt+Space")
    tray.show()

    logger.info("Nex running silently. Press Ctrl+Alt+Space to open or Ctrl+/ to jump to input.")
    sys.exit(app.exec())
