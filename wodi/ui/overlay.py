"""
Wodi Desktop Overlay — Premium Apple-Intelligence-Inspired Glassmorphism UI.

Features:
  - Full Conversation History feed with user & assistant bubbles (timestamps, Wodi badges)
  - History toggle drawer (expand/collapse with smooth animated sizing)
  - Real-time token streaming into active conversation bubble
  - Aurora borealis waveform visualizer (multi-layer state-reactive sine waves with glow)
  - Deep dark glassmorphism with frosted blur and spectrum gradient borders
  - Clean professional typography (Inter font)
  - Draggable, always-on-top desktop widget
"""
from __future__ import annotations

import datetime
import math
import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QColor, QPainter, QRadialGradient, QBrush, QPen,
    QFont, QLinearGradient, QPainterPath, QGuiApplication,
    QCursor,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QLineEdit,
    QPushButton, QScrollArea, QFrame, QSizePolicy,
)

if TYPE_CHECKING:
    from wodi.ui.app import KernelSignalBridge


# ── Color Palettes per State (Apple Intelligence Spectrum Scale) ─────────────

STATE_COLORS = {
    "idle":      {"primary": (129, 140, 248), "secondary": (192, 132, 252), "tertiary": (96, 165, 250)},
    "wake":      {"primary": (56, 189, 248),  "secondary": (168, 85, 247),  "tertiary": (236, 72, 153)},
    "listening": {"primary": (56, 189, 248),  "secondary": (244, 63, 94),   "tertiary": (168, 85, 247)},
    "thinking":  {"primary": (251, 191, 36),  "secondary": (245, 158, 11),  "tertiary": (217, 119, 6)},
    "speaking":  {"primary": (168, 85, 247),  "secondary": (99, 102, 241),  "tertiary": (236, 72, 153)},
}

STATE_LABELS = {
    "idle":      "Ready",
    "wake":      "Activating",
    "listening": "Listening",
    "thinking":  "Processing",
    "speaking":  "Speaking",
}


class AuroraVisualizer(QWidget):
    """
    Premium aurora borealis waveform visualizer.
    Draws multi-layer sine waves with glow and depth, state-reactive.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(440, 70)

        self._rms: float = 0.0
        self._state: str = "idle"
        self._phase: float = 0.0
        self._target_rms: float = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60fps

    def set_rms(self, rms: float) -> None:
        self._target_rms = min(1.0, max(0.0, rms))

    def set_state(self, state: str) -> None:
        self._state = state

    def _tick(self) -> None:
        self._phase += 0.035
        # Smooth RMS interpolation
        self._rms += (self._target_rms - self._rms) * 0.12
        self._target_rms *= 0.92
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter()
        if not painter.begin(self):
            return

        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            w = self.width()
            h = self.height()
            cx = w / 2.0
            cy = h / 2.0

            colors = STATE_COLORS.get(self._state, STATE_COLORS["idle"])

            layers = [
                {"alpha": 0.08, "freq_mult": 1.0, "amp_mult": 0.6, "time_off": 0.7, "width": 16, "color_key": "tertiary"},
                {"alpha": 0.20, "freq_mult": 1.3, "amp_mult": 0.85, "time_off": 0.3, "width": 7, "color_key": "secondary"},
                {"alpha": 0.55, "freq_mult": 1.6, "amp_mult": 1.0, "time_off": 0.0, "width": 3, "color_key": "primary"},
            ]

            for layer in layers:
                t = self._phase + layer["time_off"]
                r, g, b = colors[layer["color_key"]]
                points = []
                num_points = 90

                for i in range(num_points + 1):
                    nx = i / num_points
                    x = nx * w

                    if self._state == "idle":
                        amp = 3 + self._rms * 5
                    elif self._state == "listening":
                        amp = 14 + self._rms * 35
                    elif self._state == "thinking":
                        amp = 8 + 6 * math.sin(t * 2.5)
                    elif self._state == "speaking":
                        amp = 16 + self._rms * 40
                    else:
                        amp = 5

                    amp *= layer["amp_mult"]
                    freq = layer["freq_mult"]
                    wave = (
                        math.sin(nx * math.pi * 2.8 * freq + t * 2.0) * amp
                        + math.sin(nx * math.pi * 4.2 * freq - t * 1.5) * amp * 0.5
                        + math.sin(nx * math.pi * 6.8 * freq + t * 3.0) * amp * 0.25
                        + math.sin(nx * math.pi * 1.2 * freq + t * 0.8) * amp * 0.4
                    )

                    envelope = math.sin(nx * math.pi) ** 1.5
                    y = cy + wave * envelope
                    points.append(QPointF(x, y))

                # Filled path
                path = QPainterPath()
                path.moveTo(points[0])
                for i in range(1, len(points) - 1):
                    mx = (points[i].x() + points[i + 1].x()) / 2
                    my = (points[i].y() + points[i + 1].y()) / 2
                    path.quadTo(points[i], QPointF(mx, my))
                path.lineTo(points[-1])

                for i in range(len(points) - 1, -1, -1):
                    mirror_y = cy - (points[i].y() - cy)
                    path.lineTo(QPointF(points[i].x(), mirror_y))
                path.closeSubpath()

                grad = QLinearGradient(0, cy, w, cy)
                grad.setColorAt(0.0, QColor(r, g, b, int(255 * layer["alpha"] * 0.5)))
                grad.setColorAt(0.5, QColor(r, g, b, int(255 * layer["alpha"])))
                grad.setColorAt(1.0, QColor(r, g, b, int(255 * layer["alpha"] * 0.5)))
                painter.fillPath(path, QBrush(grad))

                # Top stroke line
                stroke_path = QPainterPath()
                stroke_path.moveTo(points[0])
                for i in range(1, len(points) - 1):
                    mx = (points[i].x() + points[i + 1].x()) / 2
                    my = (points[i].y() + points[i + 1].y()) / 2
                    stroke_path.quadTo(points[i], QPointF(mx, my))
                stroke_path.lineTo(points[-1])

                pen = QPen(QColor(r, g, b, int(255 * layer["alpha"] * 1.5)), layer["width"])
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawPath(stroke_path)

            # Center glow
            pr, pg, pb = colors["primary"]
            glow_r = 18 + self._rms * 12
            glow = QRadialGradient(cx, cy, glow_r)
            glow.setColorAt(0.0, QColor(pr, pg, pb, 50))
            glow.setColorAt(1.0, QColor(pr, pg, pb, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))
        finally:
            painter.end()


class ChatBubble(QFrame):
    """A glassmorphism chat bubble for either User or Assistant."""

    def __init__(self, role: str, text: str, time_str: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = role
        self._text = text
        self._time_str = time_str or datetime.datetime.now().strftime("%I:%M %p")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        if self.role == "user":
            self.setStyleSheet("""
                ChatBubble {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(99, 102, 241, 0.35), stop:1 rgba(139, 92, 246, 0.25));
                    border: 1px solid rgba(139, 92, 246, 0.40);
                    border-radius: 14px;
                }
            """)
        else:
            self.setStyleSheet("""
                ChatBubble {
                    background: rgba(255, 255, 255, 0.07);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 14px;
                }
            """)

        # Sender label + time header for assistant
        if self.role == "assistant":
            header = QLabel("Wodi")
            header.setFont(QFont("Inter", 8, QFont.Weight.DemiBold))
            header.setStyleSheet("color: #a78bfa; background: transparent;")
            layout.addWidget(header)

        # Message text
        self.text_label = QLabel(self._text)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text_label.setFont(QFont("Inter", 10))
        self.text_label.setStyleSheet("color: rgba(255, 255, 255, 0.95); background: transparent;")
        layout.addWidget(self.text_label)

        # Time footer
        time_label = QLabel(self._time_str)
        time_label.setFont(QFont("Inter", 7))
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        time_label.setStyleSheet("color: rgba(255, 255, 255, 0.35); background: transparent;")
        layout.addWidget(time_label)

    def set_text(self, text: str) -> None:
        self._text = text
        self.text_label.setText(text)


class WodiOverlay(QWidget):
    """
    Premium Apple-Intelligence-Inspired Desktop AI Widget.
    Deep glassmorphism, aurora waveforms, scrollable conversation history.
    """

    COMPACT_HEIGHT = 280
    EXPANDED_HEIGHT = 520
    OVERLAY_WIDTH = 540

    def __init__(self, bridge: Any | None = None, submit_callback: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._submit_callback = submit_callback
        self._caption_text = ""
        self._is_visible = False
        self._current_state = "idle"
        self._history_open = False
        self._active_assistant_bubble: ChatBubble | None = None
        self._conversation_history: list[dict] = []

        # Frameless, Always On Top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.OVERLAY_WIDTH, self.COMPACT_HEIGHT)

        self._setup_ui()
        self.position_bottom_center()

        # Connect signals directly to this overlay
        if bridge:
            bridge.response_chunk.connect(self.append_caption)
            bridge.response_complete.connect(lambda resp: self._on_response_done(resp))
            bridge.speech_started.connect(lambda: self.set_state("listening"))
            bridge.wake_detected.connect(self.show_listening)

    def _setup_ui(self) -> None:
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(20, 16, 20, 16)
        self._main_layout.setSpacing(8)

        # ── Top Bar ───────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        # Brand
        brand_dot = QLabel()
        brand_dot.setFixedSize(8, 8)
        brand_dot.setStyleSheet("background: #a855f7; border-radius: 4px;")
        top_bar.addWidget(brand_dot)

        brand_name = QLabel("Wodi")
        brand_name.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        brand_name.setStyleSheet("color: rgba(255, 255, 255, 0.92); letter-spacing: -0.2px;")
        top_bar.addWidget(brand_name)

        top_bar.addStretch(1)

        # Status Indicator Badge (Center)
        self._status_badge = QLabel("●  Ready")
        self._status_badge.setFont(QFont("Inter", 9, QFont.Weight.DemiBold))
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_badge.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.88);
                background: rgba(45, 45, 45, 0.35);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 9999px;
                padding: 4px 14px;
            }
        """)
        top_bar.addWidget(self._status_badge)

        top_bar.addStretch(1)

        # History Toggle Button
        self._history_btn = QPushButton("⏱ History")
        self._history_btn.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        self._history_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._history_btn.setStyleSheet("""
            QPushButton {
                color: rgba(255, 255, 255, 0.70);
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background: rgba(99, 102, 241, 0.25);
                border-color: rgba(99, 102, 241, 0.50);
            }
            QPushButton:pressed {
                background: rgba(99, 102, 241, 0.40);
            }
        """)
        self._history_btn.clicked.connect(self.toggle_history)
        top_bar.addWidget(self._history_btn)

        # Close Button (✕)
        close_btn = QPushButton("✕")
        close_btn.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet("""
            QPushButton {
                color: rgba(255, 255, 255, 0.60);
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 13px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background: rgba(244, 63, 94, 0.35);
                border-color: rgba(244, 63, 94, 0.60);
            }
        """)
        close_btn.clicked.connect(self.hide)
        top_bar.addWidget(close_btn)

        self._main_layout.addLayout(top_bar)

        # ── Scrollable Conversation History Area ───────────────────
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.03);
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.18);
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(99, 102, 241, 0.50);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self._history_container = QWidget()
        self._history_container.setStyleSheet("background: transparent;")
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(4, 4, 4, 4)
        self._history_layout.setSpacing(10)
        self._history_layout.addStretch(1)

        self._scroll_area.setWidget(self._history_container)
        self._scroll_area.setVisible(False)  # Hidden initially in compact mode
        self._main_layout.addWidget(self._scroll_area)

        # ── Compact Mode: Active Caption Text ──────────────────────
        self._caption = QLabel("Say 'Hey Jarvis' or type below")
        self._caption.setWordWrap(True)
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._caption.setFont(QFont("Inter", 11))
        self._caption.setStyleSheet("color: rgba(255, 255, 255, 0.85); background: transparent;")
        self._caption.setMaximumHeight(44)
        self._main_layout.addWidget(self._caption)

        # ── Aurora Visualizer ─────────────────────────────────────
        self._orb = AuroraVisualizer()
        self._orb.setFixedHeight(64)
        self._main_layout.addWidget(self._orb)

        # ── Input Bar ─────────────────────────────────────────────
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message Wodi...   Ctrl+Space")
        self._input.setFont(QFont("Inter", 11))
        self._input.setStyleSheet("""
            QLineEdit {
                background: rgba(30, 30, 46, 0.35);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 14px;
                color: rgba(255, 255, 255, 0.96);
                padding: 9px 18px;
                selection-background-color: rgba(99, 102, 241, 0.50);
            }
            QLineEdit:focus {
                border: 1px solid rgba(168, 85, 247, 0.50);
                background: rgba(40, 40, 60, 0.45);
            }
        """)
        self._input.returnPressed.connect(self._submit_text)
        input_layout.addWidget(self._input)

        # Send Button
        send_btn = QPushButton("↑")
        send_btn.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        send_btn.setFixedSize(38, 38)
        send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        send_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #6366f1, stop:0.5 #8b5cf6, stop:1 #d946ef);
                border: 1px solid rgba(255, 255, 255, 0.25);
                border-radius: 12px;
                color: #FFFFFF;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4f46e5, stop:0.5 #7c3aed, stop:1 #c026d3);
                border-color: rgba(255, 255, 255, 0.40);
            }
            QPushButton:pressed {
                background: #4f46e5;
            }
        """)
        send_btn.clicked.connect(self._submit_text)
        input_layout.addWidget(send_btn)

        self._main_layout.addWidget(input_container)

    def paintEvent(self, event: Any) -> None:
        """Draw Apple Intelligence frosted liquid glass background with spectrum border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        corner_r = 22.0

        path = QPainterPath()
        path.addRoundedRect(rect, corner_r, corner_r)

        # Deep frosted liquid glass backdrop
        bg_grad = QLinearGradient(0, 0, 0, self.height())
        bg_grad.setColorAt(0.0, QColor(14, 14, 24, 235))
        bg_grad.setColorAt(0.5, QColor(10, 10, 18, 245))
        bg_grad.setColorAt(1.0, QColor(8, 8, 14, 250))
        painter.fillPath(path, QBrush(bg_grad))

        # State-reactive Apple spectrum border
        colors = STATE_COLORS.get(self._current_state, STATE_COLORS["idle"])
        pr, pg, pb = colors["primary"]
        sr, sg, sb = colors["secondary"]

        border_grad = QLinearGradient(0, 0, self.width(), self.height())
        border_grad.setColorAt(0.0, QColor(pr, pg, pb, 110))
        border_grad.setColorAt(0.5, QColor(sr, sg, sb, 70))
        border_grad.setColorAt(1.0, QColor(pr, pg, pb, 110))

        border_pen = QPen(QBrush(border_grad), 1.5)
        painter.setPen(border_pen)
        painter.drawPath(path)

        # Specular top catch-light
        glow_grad = QLinearGradient(0, 2, 0, 36)
        glow_grad.setColorAt(0.0, QColor(pr, pg, pb, 30))
        glow_grad.setColorAt(1.0, QColor(pr, pg, pb, 0))
        glow_path = QPainterPath()
        glow_path.addRoundedRect(QRectF(rect.x(), rect.y(), rect.width(), 32), corner_r, corner_r)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(glow_path, QBrush(glow_grad))

        painter.end()

    def position_bottom_center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + geo.height() - self.height() - 36
            self.move(x, y)

    def toggle_history(self) -> None:
        self._history_open = not self._history_open
        self._scroll_area.setVisible(self._history_open)
        self._caption.setVisible(not self._history_open)

        # Resize overlay smoothly
        target_height = self.EXPANDED_HEIGHT if self._history_open else self.COMPACT_HEIGHT
        self.setFixedHeight(target_height)
        self.position_bottom_center()

        self._history_btn.setText("▲ Compact" if self._history_open else "⏱ History")
        if self._history_open:
            self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(50, lambda: self._scroll_area.verticalScrollBar().setValue(
            self._scroll_area.verticalScrollBar().maximum()
        ))

    def _submit_text(self) -> None:
        text = self._input.text().strip()
        if not text:
            return

        self._input.clear()
        self._caption_text = ""

        # Auto-open history view on first message
        if not self._history_open:
            self.toggle_history()

        # Add User Chat Bubble to History
        user_bubble = ChatBubble(role="user", text=text, parent=self)
        self._history_layout.insertWidget(self._history_layout.count() - 1, user_bubble)

        # Add placeholder Assistant Chat Bubble
        self._active_assistant_bubble = ChatBubble(role="assistant", text="Thinking...", parent=self)
        self._history_layout.insertWidget(self._history_layout.count() - 1, self._active_assistant_bubble)
        self._scroll_to_bottom()

        # Set status
        self._caption.setText(f"You: {text}")
        self.set_state("thinking")

        if self._submit_callback:
            self._submit_callback(text)

    def show_listening(self) -> None:
        self.set_state("listening")
        if not self._is_visible:
            self.show()
            self._is_visible = True
        self._input.setFocus()

    def toggle(self) -> None:
        if self._is_visible:
            self.hide()
            self._is_visible = False
        else:
            self.show_listening()

    def set_state(self, state: str) -> None:
        self._current_state = state
        self._orb.set_state(state)

        label = STATE_LABELS.get(state, "Ready")
        colors = STATE_COLORS.get(state, STATE_COLORS["idle"])
        pr, pg, pb = colors["primary"]

        dot = "◉" if state in ("listening", "speaking") else "◎" if state == "thinking" else "●"
        self._status_badge.setText(f"{dot}  {label}")

        self._status_badge.setStyleSheet(f"""
            QLabel {{
                color: rgba(255, 255, 255, 0.92);
                background: rgba({pr}, {pg}, {pb}, 0.18);
                border: 1px solid rgba({pr}, {pg}, {pb}, 0.35);
                border-radius: 9999px;
                padding: 4px 14px;
                letter-spacing: 0.5px;
            }}
        """)
        self.update()

    def append_caption(self, text: str) -> None:
        """Stream chunks into the active assistant bubble and caption."""
        self._caption_text += text

        # Update the active assistant bubble live
        if self._active_assistant_bubble:
            self._active_assistant_bubble.set_text(self._caption_text)
            self._scroll_to_bottom()

        # Update compact caption view
        display = self._caption_text[-120:] if len(self._caption_text) > 120 else self._caption_text
        self._caption.setText(display)

        self.set_state("speaking")
        self._orb.set_rms(0.55)

    def _on_response_done(self, response: str = "") -> None:
        """Handle response completion — keep conversation permanently in history."""
        final_text = response or self._caption_text
        if self._active_assistant_bubble and final_text:
            self._active_assistant_bubble.set_text(final_text)
            self._scroll_to_bottom()

        self._active_assistant_bubble = None
        self.set_state("idle")
        # Keep response visible in caption or show Ready
        if not self._history_open:
            self._caption.setText(final_text if len(final_text) < 140 else final_text[:140] + "…")

    def get_history(self) -> list[dict]:
        return list(self._conversation_history)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: Any) -> None:
        if hasattr(self, "_drag_pos") and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self._is_visible = False
