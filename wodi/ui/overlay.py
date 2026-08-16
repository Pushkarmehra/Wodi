"""
Wodi Desktop Overlay — Premium Apple-Intelligence-Inspired Glassmorphism UI.

Features:
  - Aurora borealis waveform visualizer (multi-layer sine waves with glow)
  - Deep dark glassmorphism with frosted blur
  - Gradient borders that shift hue based on state
  - Clean professional typography (no emojis)
  - Smooth state transition animations
  - Draggable, always-on-top desktop widget
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QPainter, QRadialGradient, QBrush, QPen,
    QFont, QLinearGradient, QPainterPath, QGuiApplication,
    QConicalGradient,
)
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QLineEdit, QPushButton

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
        self.setMinimumSize(440, 100)

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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0

        colors = STATE_COLORS.get(self._state, STATE_COLORS["idle"])

        # ── Draw 3 wave layers with increasing detail ──────────────────
        layers = [
            {"alpha": 0.08, "freq_mult": 1.0, "amp_mult": 0.6, "time_off": 0.7, "width": 20, "color_key": "tertiary"},
            {"alpha": 0.20, "freq_mult": 1.3, "amp_mult": 0.85, "time_off": 0.3, "width": 8, "color_key": "secondary"},
            {"alpha": 0.55, "freq_mult": 1.6, "amp_mult": 1.0, "time_off": 0.0, "width": 3, "color_key": "primary"},
        ]

        for layer in layers:
            t = self._phase + layer["time_off"]
            r, g, b = colors[layer["color_key"]]
            points = []
            num_points = 100

            for i in range(num_points + 1):
                nx = i / num_points
                x = nx * w

                # Amplitude based on state
                if self._state == "idle":
                    amp = 4 + self._rms * 6
                elif self._state == "listening":
                    amp = 16 + self._rms * 40
                elif self._state == "thinking":
                    amp = 10 + 7 * math.sin(t * 2.5)
                elif self._state == "speaking":
                    amp = 18 + self._rms * 45
                else:
                    amp = 6

                amp *= layer["amp_mult"]

                # Multi-frequency wave
                freq = layer["freq_mult"]
                wave = (
                    math.sin(nx * math.pi * 2.8 * freq + t * 2.0) * amp
                    + math.sin(nx * math.pi * 4.2 * freq - t * 1.5) * amp * 0.5
                    + math.sin(nx * math.pi * 6.8 * freq + t * 3.0) * amp * 0.25
                    + math.sin(nx * math.pi * 1.2 * freq + t * 0.8) * amp * 0.4
                )

                # Bell curve envelope
                envelope = math.sin(nx * math.pi) ** 1.5
                y = cy + wave * envelope

                points.append(QPointF(x, y))

            # Draw filled band (top wave mirrored)
            path = QPainterPath()
            path.moveTo(points[0])
            for i in range(1, len(points) - 1):
                mx = (points[i].x() + points[i + 1].x()) / 2
                my = (points[i].y() + points[i + 1].y()) / 2
                path.quadTo(points[i], QPointF(mx, my))
            path.lineTo(points[-1])

            # Mirror for bottom
            for i in range(len(points) - 1, -1, -1):
                mirror_y = cy - (points[i].y() - cy)
                path.lineTo(QPointF(points[i].x(), mirror_y))
            path.closeSubpath()

            # Fill with gradient
            grad = QLinearGradient(0, cy, w, cy)
            grad.setColorAt(0.0, QColor(r, g, b, int(255 * layer["alpha"] * 0.5)))
            grad.setColorAt(0.5, QColor(r, g, b, int(255 * layer["alpha"])))
            grad.setColorAt(1.0, QColor(r, g, b, int(255 * layer["alpha"] * 0.5)))
            painter.fillPath(path, QBrush(grad))

            # Stroke the top wave line
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

        # ── Center glow dot (subtle) ──────────────────────────────────
        pr, pg, pb = colors["primary"]
        glow_r = 20 + self._rms * 15
        glow = QRadialGradient(cx, cy, glow_r)
        glow.setColorAt(0.0, QColor(pr, pg, pb, 60))
        glow.setColorAt(1.0, QColor(pr, pg, pb, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))

        painter.end()


class WodiOverlay(QWidget):
    """
    Premium Apple-Intelligence-Inspired Desktop AI Widget.
    Deep glassmorphism, aurora waveforms, professional typography.
    """

    def __init__(self, bridge: Any | None = None, submit_callback: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._submit_callback = submit_callback
        self._caption_text = ""
        self._is_visible = False
        self._current_state = "idle"
        self._current_user_message = ""   # Track current user input for history pairing
        self._conversation_history: list[dict] = []  # [{"user": ..., "assistant": ..., "time": ...}]

        # Frameless, Always On Top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 280)

        self._setup_ui()
        self.position_bottom_center()

        if bridge:
            bridge.response_chunk.connect(self.append_caption)
            bridge.response_complete.connect(lambda _: self._on_response_done())
            bridge.speech_started.connect(lambda: self.set_state("listening"))
            bridge.wake_detected.connect(self.show_listening)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 18, 24, 18)
        main_layout.setSpacing(10)

        # ── Top Bar: Status Indicator ─────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._status_badge = QLabel("◉  Ready")
        self._status_badge.setFont(QFont("Inter", 10, QFont.Weight.DemiBold))
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_badge.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.88);
                background: rgba(45, 45, 45, 0.35);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 9999px;
                padding: 6px 18px;
                letter-spacing: 0.5px;
            }
        """)
        top_bar.addWidget(self._status_badge)
        main_layout.addLayout(top_bar)

        # ── Caption Text ──────────────────────────────────────────
        self._caption = QLabel("")
        self._caption.setWordWrap(True)
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._caption.setFont(QFont("Inter", 12, QFont.Weight.Normal))
        self._caption.setStyleSheet(
            "color: rgba(255, 255, 255, 0.88); background: transparent;"
        )
        self._caption.setMaximumHeight(50)
        main_layout.addWidget(self._caption)

        # ── Aurora Visualizer ─────────────────────────────────────
        self._orb = AuroraVisualizer()
        self._orb.setFixedHeight(100)
        main_layout.addWidget(self._orb)

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
                background: rgba(35, 35, 35, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
                color: rgba(255, 255, 255, 0.94);
                padding: 10px 20px;
                selection-background-color: rgba(255, 255, 255, 0.25);
            }
            QLineEdit:focus {
                border: 1px solid rgba(255, 255, 255, 0.35);
                background: rgba(60, 60, 60, 0.35);
            }
        """)
        self._input.returnPressed.connect(self._submit_text)
        input_layout.addWidget(self._input)

        # Send Button
        send_btn = QPushButton("↑")
        send_btn.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        send_btn.setFixedSize(40, 40)
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

        main_layout.addWidget(input_container)

    def paintEvent(self, event: Any) -> None:
        """Draw Apple Intelligence frosted liquid glass background with spectrum border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        corner_r = 24.0

        path = QPainterPath()
        path.addRoundedRect(rect, corner_r, corner_r)

        # Deep frosted liquid glass backdrop
        bg_grad = QLinearGradient(0, 0, 0, self.height())
        bg_grad.setColorAt(0.0, QColor(14, 14, 24, 225))
        bg_grad.setColorAt(0.5, QColor(10, 10, 18, 235))
        bg_grad.setColorAt(1.0, QColor(8, 8, 14, 240))
        painter.fillPath(path, QBrush(bg_grad))

        # State-reactive Apple spectrum border
        colors = STATE_COLORS.get(self._current_state, STATE_COLORS["idle"])
        pr, pg, pb = colors["primary"]
        sr, sg, sb = colors["secondary"]

        border_grad = QLinearGradient(0, 0, self.width(), self.height())
        border_grad.setColorAt(0.0, QColor(pr, pg, pb, 90))
        border_grad.setColorAt(0.5, QColor(sr, sg, sb, 60))
        border_grad.setColorAt(1.0, QColor(pr, pg, pb, 90))

        border_pen = QPen(QBrush(border_grad), 1.5)
        painter.setPen(border_pen)
        painter.drawPath(path)

        # Subtle specular top catch-light
        glow_grad = QLinearGradient(0, 3, 0, 40)
        glow_grad.setColorAt(0.0, QColor(pr, pg, pb, 25))
        glow_grad.setColorAt(1.0, QColor(pr, pg, pb, 0))
        glow_path = QPainterPath()
        glow_path.addRoundedRect(QRectF(rect.x(), rect.y(), rect.width(), 36), corner_r, corner_r)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(glow_path, QBrush(glow_grad))

        painter.end()

    def position_bottom_center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + geo.height() - self.height() - 48
            self.move(x, y)

    def _submit_text(self) -> None:
        text = self._input.text().strip()
        if text:
            self._input.clear()
            # Reset response accumulator for new request
            self._caption_text = ""
            self._current_user_message = text
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

        # Unicode geometric dot indicator
        dot = "◉" if state in ("listening", "speaking") else "◎" if state == "thinking" else "●"
        self._status_badge.setText(f"{dot}  {label}")

        self._status_badge.setStyleSheet(f"""
            QLabel {{
                color: rgba(255, 255, 255, 0.90);
                background: rgba({pr}, {pg}, {pb}, 0.15);
                border: 1px solid rgba({pr}, {pg}, {pb}, 0.30);
                border-radius: 9999px;
                padding: 6px 18px;
                letter-spacing: 0.5px;
            }}
        """)

        # Trigger repaint for border color change
        self.update()

    def append_caption(self, text: str) -> None:
        self._caption_text += text
        display = self._caption_text[-120:] if len(self._caption_text) > 120 else self._caption_text
        self._caption.setText(display)
        self.set_state("speaking")
        self._orb.set_rms(0.55)

    def _on_response_done(self) -> None:
        # Save the completed conversation to history
        if self._current_user_message and self._caption_text:
            import time as _time
            self._conversation_history.append({
                "user": self._current_user_message,
                "assistant": self._caption_text.strip(),
                "time": _time.time(),
            })
            # Keep max 50 entries
            if len(self._conversation_history) > 50:
                self._conversation_history = self._conversation_history[-50:]
        self._current_user_message = ""
        self.set_state("idle")
        QTimer.singleShot(4000, self._reset_caption)

    def _reset_caption(self) -> None:
        self._caption_text = ""
        self._caption.setText("")
        self.set_state("idle")

    def get_history(self) -> list[dict]:
        """Return the conversation history."""
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
