"""
Woody Desktop Overlay — Premium Apple-Intelligence-Inspired Glassmorphism UI.

Features:
  - Full Conversation History feed with user & assistant bubbles (timestamps, Woody badges)
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

import colorsys
import random

if TYPE_CHECKING:
    from woody.ui.app import KernelSignalBridge


# ── Dynamic Voice-Reactive Gradient Color Spectrum ────────────────────────────

def get_voice_spectrum_palette(state: str, rms: float, phase: float, speech_phase: float = 0.0) -> dict[str, tuple[int, int, int]]:
    """Compute rich continuous dynamic voice gradient colors based on state, voice RMS energy, and animation phase."""
    energy = min(1.0, rms * 1.5)

    if state == "idle":
        shift = math.sin(phase * 0.5) * 16.0
        h1 = (240.0 + shift) % 360.0        # Indigo
        h2 = (275.0 + shift * 1.2) % 360.0  # Violet
        h3 = (195.0 + shift * 0.8) % 360.0  # Soft Cyan
    elif state in ("wake", "listening"):
        # Dynamic Siri / Apple Intelligence spectrum: cyan -> purple -> fuchsia
        h1 = (195.0 + energy * 75.0 + math.sin(phase * 1.2) * 18.0) % 360.0
        h2 = (280.0 + energy * 50.0 + math.cos(phase * 1.5) * 22.0) % 360.0
        h3 = (335.0 + energy * 40.0) % 360.0
    elif state == "thinking":
        # Amber & Gold Solar Spectrum
        h1 = (44.0 + math.sin(phase * 2.0) * 16.0) % 360.0
        h2 = (26.0 + math.cos(phase * 1.8) * 16.0) % 360.0
        h3 = (280.0 + math.sin(phase * 1.2) * 20.0) % 360.0
    elif state == "speaking":
        # Dynamic AI Voice Response: Gradient colors morph continuously as the AI responds in voice!
        # Swirls through Luminous Violet (265°) -> Neon Magenta (325°) -> Solar Gold (48°) -> Electric Cyan (185°) -> Azure (215°)
        shift = (speech_phase * 32.0 + phase * 20.0) % 360.0
        h1 = (265.0 + shift + energy * 68.0 + math.sin(phase * 1.8) * 26.0) % 360.0
        h2 = (325.0 + shift * 1.15 + energy * 52.0 + math.cos(phase * 1.5) * 28.0) % 360.0
        h3 = (185.0 + shift * 0.88 + energy * 60.0 + math.sin(phase * 1.2) * 24.0) % 360.0
    else:
        h1, h2, h3 = 240.0, 275.0, 195.0

    def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
        h_norm = (h % 360.0) / 360.0
        s_norm = max(0.0, min(1.0, s / 100.0))
        l_norm = max(0.0, min(1.0, l / 100.0))
        r, g, b = colorsys.hls_to_rgb(h_norm, l_norm, s_norm)
        return int(r * 255), int(g * 255), int(b * 255)

    c1 = _hsl_to_rgb(h1, 88.0 + energy * 12.0, 60.0 + energy * 18.0)
    c2 = _hsl_to_rgb(h2, 92.0 + energy * 8.0, 62.0 + energy * 20.0)
    c3 = _hsl_to_rgb(h3, 85.0 + energy * 15.0, 65.0 + energy * 15.0)
    peak = _hsl_to_rgb((h1 + 60.0 + math.sin(phase * 2.0) * 20.0) % 360.0, 100.0, 80.0 + energy * 18.0)

    return {"primary": c1, "secondary": c2, "tertiary": c3, "peak": peak}


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
    Draws multi-layer sinusoidal wave ribbons with real-time voice-reactive gradient morphing.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(440, 75)

        self._rms: float = 0.0
        self._state: str = "idle"
        self._phase: float = 0.0
        self._speech_phase: float = 0.0
        self._target_rms: float = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60fps

    def set_rms(self, rms: float) -> None:
        self._target_rms = min(1.0, max(0.0, rms))

    def set_speech_pulse(self, text: str = "") -> None:
        self._speech_phase += 0.28
        self.set_rms(0.55 + min(0.35, len(text) * 0.03))

    def set_state(self, state: str) -> None:
        self._state = state

    def _tick(self) -> None:
        try:
            self._phase += 0.035
            if self._state == "speaking":
                self._speech_phase += 0.036
            # Smooth RMS interpolation
            self._rms += (self._target_rms - self._rms) * 0.14
            self._target_rms *= 0.92
            self.update()
        except Exception:
            pass

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

            colors = get_voice_spectrum_palette(self._state, self._rms, self._phase, self._speech_phase)
            pr, pg, pb = colors["primary"]
            sr, sg, sb = colors["secondary"]
            tr, tg, tb = colors["tertiary"]
            pkr, pkg, pkb = colors["peak"]

            layers = [
                {"alpha": 0.12, "freq_mult": 0.8, "amp_mult": 0.50, "time_off": 1.0, "width": 18, "rgb": (tr, tg, tb)},
                {"alpha": 0.25, "freq_mult": 1.2, "amp_mult": 0.70, "time_off": 0.5, "width": 8,  "rgb": (sr, sg, sb)},
                {"alpha": 0.50, "freq_mult": 1.6, "amp_mult": 0.90, "time_off": 0.2, "width": 4,  "rgb": (pr, pg, pb)},
                {"alpha": 0.85, "freq_mult": 2.1, "amp_mult": 1.00, "time_off": 0.0, "width": 2.2, "rgb": (pkr, pkg, pkb)},
            ]

            for layer in layers:
                t = self._phase + layer["time_off"]
                r, g, b = layer["rgb"]
                points = []
                num_points = 96

                for i in range(num_points + 1):
                    nx = i / num_points
                    x = nx * w

                    if self._state == "idle":
                        amp = 4 + self._rms * 6
                    elif self._state in ("wake", "listening"):
                        amp = 15 + self._rms * 42
                    elif self._state == "thinking":
                        amp = 10 + 7 * math.sin(t * 2.5)
                    elif self._state == "speaking":
                        amp = 18 + self._rms * 48
                    else:
                        amp = 5

                    amp *= layer["amp_mult"]
                    freq = layer["freq_mult"]
                    wave = (
                        math.sin(nx * math.pi * 2.8 * freq + t * 2.0) * amp
                        + math.sin(nx * math.pi * 4.4 * freq - t * 1.5) * amp * 0.5
                        + math.sin(nx * math.pi * 6.8 * freq + t * 3.0) * amp * 0.25
                        + math.sin(nx * math.pi * 1.2 * freq + t * 0.8) * amp * 0.4
                    )

                    envelope = math.sin(nx * math.pi) ** 1.4
                    y = cy + wave * envelope
                    points.append(QPointF(x, y))

                # Filled ribbon path
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

                # Multi-stop linear gradient fill across the sound wave
                grad = QLinearGradient(0, cy, w, cy)
                grad.setColorAt(0.0, QColor(tr, tg, tb, int(255 * layer["alpha"] * 0.35)))
                grad.setColorAt(0.25, QColor(pr, pg, pb, int(255 * layer["alpha"] * 0.75)))
                grad.setColorAt(0.5, QColor(sr, sg, sb, int(255 * layer["alpha"])))
                grad.setColorAt(0.75, QColor(pkr, pkg, pkb, int(255 * layer["alpha"] * 0.75)))
                grad.setColorAt(1.0, QColor(tr, tg, tb, int(255 * layer["alpha"] * 0.35)))
                painter.fillPath(path, QBrush(grad))

                # Top stroke with glowing highlight
                stroke_path = QPainterPath()
                stroke_path.moveTo(points[0])
                for i in range(1, len(points) - 1):
                    mx = (points[i].x() + points[i + 1].x()) / 2
                    my = (points[i].y() + points[i + 1].y()) / 2
                    stroke_path.quadTo(points[i], QPointF(mx, my))
                stroke_path.lineTo(points[-1])

                pen = QPen(QColor(r, g, b, min(255, int(255 * layer["alpha"] * 1.6))), layer["width"])
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawPath(stroke_path)

            # Center Multi-Stop Radiant Core Bloom
            glow_r = 22 + self._rms * 28
            glow = QRadialGradient(cx, cy, glow_r)
            glow.setColorAt(0.0, QColor(255, 255, 255, int(110 + self._rms * 100)))
            glow.setColorAt(0.35, QColor(pr, pg, pb, int(80 + self._rms * 60)))
            glow.setColorAt(0.75, QColor(sr, sg, sb, int(40 + self._rms * 30)))
            glow.setColorAt(1.0, QColor(tr, tg, tb, 0))
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
            header = QLabel("Woody")
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


class WoodyOverlay(QWidget):
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
            bridge.speech_transcribed.connect(self.add_user_speech)
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

        brand_name = QLabel("Woody")
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

        # Pet Mode Button
        self._pet_btn = QPushButton("🐾 Pet Mode")
        self._pet_btn.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        self._pet_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pet_btn.setStyleSheet("""
            QPushButton {
                color: #c084fc;
                background: rgba(168, 85, 247, 0.14);
                border: 1px solid rgba(168, 85, 247, 0.35);
                border-radius: 8px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background: rgba(168, 85, 247, 0.32);
                border-color: rgba(168, 85, 247, 0.65);
            }
            QPushButton:pressed {
                background: rgba(168, 85, 247, 0.50);
            }
        """)
        self._pet_btn.clicked.connect(self._launch_pet_mode)
        top_bar.addWidget(self._pet_btn)

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
        self._caption = QLabel("Say 'hey woody' or type below")
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
        self._input.setPlaceholderText("Message Woody...   Ctrl+Space")
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

        # State-reactive & Voice-reactive Apple spectrum border
        rms_val = getattr(self._orb, "_rms", 0.0) if hasattr(self, "_orb") else 0.0
        phase_val = getattr(self._orb, "_phase", 0.0) if hasattr(self, "_orb") else 0.0
        speech_phase_val = getattr(self._orb, "_speech_phase", 0.0) if hasattr(self, "_orb") else 0.0
        colors = get_voice_spectrum_palette(self._current_state, rms_val, phase_val, speech_phase_val)
        pr, pg, pb = colors["primary"]
        sr, sg, sb = colors["secondary"]
        tr, tg, tb = colors["tertiary"]

        border_grad = QLinearGradient(0, 0, self.width(), self.height())
        border_grad.setColorAt(0.0, QColor(pr, pg, pb, int(120 + rms_val * 100)))
        border_grad.setColorAt(0.5, QColor(sr, sg, sb, int(80 + rms_val * 80)))
        border_grad.setColorAt(1.0, QColor(tr, tg, tb, int(120 + rms_val * 100)))

        border_pen = QPen(QBrush(border_grad), 1.5 + rms_val * 0.8)
        painter.setPen(border_pen)
        painter.drawPath(path)

        # Specular top catch-light with voice glow
        glow_grad = QLinearGradient(0, 2, 0, 36)
        glow_grad.setColorAt(0.0, QColor(pr, pg, pb, int(35 + rms_val * 50)))
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

    def _launch_pet_mode(self) -> None:
        """Launch the animated Desktop AI Pet companion and hide the overlay."""
        import subprocess
        import sys
        from pathlib import Path
        try:
            script_path = str(Path(__file__).parent / "desktop_pet.py")
            subprocess.Popen(
                [sys.executable, script_path],
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if sys.platform == "win32" else 0,
            )
            self.hide()
        except Exception as e:
            print(f"Failed to launch pet mode: {e}")

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

    def add_user_speech(self, text: str) -> None:
        """Called when speech transcription arrives — creates user bubble and prepares assistant bubble."""
        clean_text = text.strip()
        if not clean_text:
            return

        self._caption_text = ""

        # Ensure overlay is visible on desktop
        if not self._is_visible:
            self.show()
            self._is_visible = True

        # Auto-open history view so the user sees their speech in the chat
        if not self._history_open:
            self.toggle_history()

        # Add User Chat Bubble to History
        user_bubble = ChatBubble(role="user", text=clean_text, parent=self)
        self._history_layout.insertWidget(self._history_layout.count() - 1, user_bubble)

        # Add placeholder Assistant Chat Bubble for response
        self._active_assistant_bubble = ChatBubble(role="assistant", text="Thinking...", parent=self)
        self._history_layout.insertWidget(self._history_layout.count() - 1, self._active_assistant_bubble)
        self._scroll_to_bottom()

        # Update caption & state
        self._caption.setText(f"You: {clean_text}")
        self.set_state("thinking")

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
        rms_val = getattr(self._orb, "_rms", 0.0) if hasattr(self, "_orb") else 0.0
        phase_val = getattr(self._orb, "_phase", 0.0) if hasattr(self, "_orb") else 0.0
        speech_phase_val = getattr(self._orb, "_speech_phase", 0.0) if hasattr(self, "_orb") else 0.0
        colors = get_voice_spectrum_palette(state, rms_val, phase_val, speech_phase_val)
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
        """Stream chunks into the active assistant bubble and caption with dynamic voice pulses."""
        self._caption_text += text

        # Update the active assistant bubble live
        if self._active_assistant_bubble:
            self._active_assistant_bubble.set_text(self._caption_text)
            self._scroll_to_bottom()

        # Update compact caption view
        display = self._caption_text[-120:] if len(self._caption_text) > 120 else self._caption_text
        self._caption.setText(display)

        self.set_state("speaking")
        self._orb.set_speech_pulse(text)

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
