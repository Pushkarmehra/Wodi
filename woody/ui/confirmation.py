"""
Inline confirmation card for user-confirm tier actions.

Premium glassmorphism design with animated countdown ring,
state-reactive borders, and smooth entry/exit animations.
Appears near the cursor without blocking the main UI.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QBrush, QPen, QPainterPath,
    QLinearGradient, QFont, QConicalGradient,
)
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton

from woody.utils.logging import get_logger

log = get_logger(__name__)


# ── Tool Category Icons (Unicode geometric shapes) ───────────────────────────

TOOL_ICONS = {
    "open_application": "◈",
    "close_application": "◇",
    "type_text": "▤",
    "click_element": "◉",
    "navigate_url": "◎",
    "run_command": "▶",
    "write_file": "▣",
    "delete_file": "▬",
    "capture_screen": "◻",
    "default": "◆",
}


class ConfirmCard(QWidget):
    """
    Non-modal confirmation card shown inline near the cursor.

    Premium glassmorphism with animated countdown ring.
    Emits approved(bool) signal when user decides.
    Auto-denies after timeout_seconds.
    """
    from PySide6.QtCore import Signal
    approved = Signal(bool)

    def __init__(
        self,
        tool_name: str,
        params: dict,
        timeout_seconds: int = 30,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._timeout = timeout_seconds
        self._elapsed = 0
        self._tool_name = tool_name

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 170)
        self._setup_ui(tool_name, params)

        # Auto-deny timer
        self._countdown = QTimer(self)
        self._countdown.timeout.connect(self._tick)
        self._countdown.start(1000)

    def _setup_ui(self, tool_name: str, params: dict) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        # ── Header with icon ──────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon = TOOL_ICONS.get(tool_name, TOOL_ICONS["default"])
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Inter", 16))
        icon_label.setFixedSize(32, 32)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("""
            QLabel {
                color: #f59e0b;
                background: rgba(245, 158, 11, 0.12);
                border: 1px solid rgba(245, 158, 11, 0.20);
                border-radius: 8px;
            }
        """)
        header_row.addWidget(icon_label)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title = QLabel(f"Woody wants to: {tool_name.replace('_', ' ').title()}")
        title.setFont(QFont("Inter", 11, QFont.Weight.DemiBold))
        title.setStyleSheet("color: rgba(255, 255, 255, 0.92); background: transparent;")
        title.setWordWrap(True)
        header_text.addWidget(title)

        # Params preview
        params_str = ", ".join(f"{k}={v}" for k, v in list(params.items())[:3])
        if params_str:
            detail = QLabel(params_str[:90])
            detail.setFont(QFont("JetBrains Mono", 9))
            detail.setStyleSheet("color: rgba(255, 255, 255, 0.40); background: transparent;")
            detail.setWordWrap(True)
            header_text.addWidget(detail)

        header_row.addLayout(header_text)
        layout.addLayout(header_row)

        layout.addStretch()

        # ── Buttons + Timer ───────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._deny_btn = QPushButton("Deny")
        self._deny_btn.setFont(QFont("Inter", 10, QFont.Weight.DemiBold))
        self._deny_btn.setFixedHeight(34)
        self._deny_btn.setStyleSheet("""
            QPushButton {
                background: rgba(244, 63, 94, 0.12);
                border: 1px solid rgba(244, 63, 94, 0.25);
                border-radius: 8px;
                color: #f43f5e;
                padding: 0 20px;
            }
            QPushButton:hover {
                background: rgba(244, 63, 94, 0.22);
                border-color: rgba(244, 63, 94, 0.40);
            }
            QPushButton:pressed { background: rgba(244, 63, 94, 0.30); }
        """)
        self._deny_btn.clicked.connect(lambda: self._decide(False))

        self._allow_btn = QPushButton("Allow")
        self._allow_btn.setFont(QFont("Inter", 10, QFont.Weight.DemiBold))
        self._allow_btn.setFixedHeight(34)
        self._allow_btn.setStyleSheet("""
            QPushButton {
                background: rgba(52, 211, 153, 0.12);
                border: 1px solid rgba(52, 211, 153, 0.25);
                border-radius: 8px;
                color: #34d399;
                padding: 0 20px;
            }
            QPushButton:hover {
                background: rgba(52, 211, 153, 0.22);
                border-color: rgba(52, 211, 153, 0.40);
            }
            QPushButton:pressed { background: rgba(52, 211, 153, 0.30); }
        """)
        self._allow_btn.clicked.connect(lambda: self._decide(True))

        btn_row.addWidget(self._deny_btn)
        btn_row.addStretch()

        self._timer_label = QLabel(f"{self._timeout}s")
        self._timer_label.setFont(QFont("JetBrains Mono", 9, QFont.Weight.DemiBold))
        self._timer_label.setStyleSheet("color: rgba(245, 158, 11, 0.6); background: transparent;")
        btn_row.addWidget(self._timer_label)

        btn_row.addStretch()
        btn_row.addWidget(self._allow_btn)
        layout.addLayout(btn_row)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        corner_r = 16.0
        path = QPainterPath()
        path.addRoundedRect(rect, corner_r, corner_r)

        # Deep dark glassmorphism background
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor(14, 12, 24, 240))
        gradient.setColorAt(1.0, QColor(10, 10, 18, 245))
        painter.fillPath(path, QBrush(gradient))

        # Amber warning border
        border_grad = QLinearGradient(0, 0, self.width(), self.height())
        border_grad.setColorAt(0.0, QColor(245, 158, 11, 60))
        border_grad.setColorAt(0.5, QColor(251, 146, 60, 40))
        border_grad.setColorAt(1.0, QColor(245, 158, 11, 60))
        painter.setPen(QPen(QBrush(border_grad), 1.5))
        painter.drawPath(path)

        # ── Countdown ring ────────────────────────────────────────
        progress = 1.0 - (self._elapsed / self._timeout)
        ring_cx = self.width() / 2
        ring_cy = self.height() - 30
        ring_r = 12
        ring_rect = QRectF(ring_cx - ring_r, ring_cy - ring_r, ring_r * 2, ring_r * 2)

        # Background ring
        painter.setPen(QPen(QColor(255, 255, 255, 15), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(ring_rect)

        # Progress arc
        if progress > 0:
            span_angle = int(progress * 360 * 16)  # Qt uses 1/16th of a degree
            start_angle = 90 * 16  # Start from top
            pen = QPen(QColor(245, 158, 11, 150), 2.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(ring_rect, start_angle, span_angle)

        painter.end()

    def _tick(self) -> None:
        self._elapsed += 1
        remaining = self._timeout - self._elapsed
        self._timer_label.setText(f"{remaining}s")
        self.update()  # Repaint for countdown ring
        if remaining <= 0:
            self._decide(False)

    def _decide(self, approved: bool) -> None:
        self._countdown.stop()
        self.approved.emit(approved)
        log.info("confirm.decided", tool=self._tool_name, approved=approved)
        self.close()
