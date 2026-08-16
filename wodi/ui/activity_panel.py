"""
Activity Panel — Premium Audit Log Viewer UI.

Dark-themed real-time activity feed with:
  - Glassmorphism styling matching the overlay design language
  - Color-coded permission tier badges (emerald/amber/rose)
  - Session grouping with timestamps
  - Search & filter functionality
  - Animated entry addition
  - Custom dark scrollbar styling
"""
from __future__ import annotations

import datetime
from typing import Any, TYPE_CHECKING

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QFont, QColor, QPainter, QPainterPath, QBrush, QLinearGradient, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QLineEdit, QAbstractItemView,
    QStyledItemDelegate, QStyleOptionViewItem,
)

from wodi.utils.logging import get_logger

log = get_logger(__name__)


# ── Tier badge colors ─────────────────────────────────────────────────────────

TIER_COLORS = {
    "read_only":    {"bg": (52, 211, 153, 30), "border": (52, 211, 153, 64), "text": (52, 211, 153), "dot": "#34d399"},
    "user_confirm": {"bg": (245, 158, 11, 30), "border": (245, 158, 11, 64), "text": (245, 158, 11), "dot": "#f59e0b"},
    "privileged":   {"bg": (244, 63, 94, 30),  "border": (244, 63, 94, 64),  "text": (244, 63, 94), "dot": "#f43f5e"},
}

TIER_LABELS = {
    "read_only": "Safe",
    "user_confirm": "Confirm",
    "privileged": "Admin",
}


class ActivityItemDelegate(QStyledItemDelegate):
    """Custom delegate for rendering activity list items with dark styling."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Any) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect.adjusted(4, 2, -4, -2)
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 8, 8)

        # Background
        if option.state & 0x0001:  # State_Selected
            painter.fillPath(path, QBrush(QColor(99, 102, 241, 20)))
        elif option.state & 0x0002:  # State_MouseOver (hover approximation)
            painter.fillPath(path, QBrush(QColor(255, 255, 255, 8)))

        # Draw text
        data = index.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        painter.setPen(QColor(255, 255, 255, 220))
        painter.setFont(QFont("Inter", 10))
        text_rect = rect.adjusted(12, 4, -80, -4)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, data.get("display", ""))

        # Draw tier badge
        tier = data.get("tier", "")
        tier_info = TIER_COLORS.get(tier)
        if tier_info:
            badge_text = TIER_LABELS.get(tier, tier)
            badge_width = len(badge_text) * 7 + 20
            badge_x = rect.right() - badge_width - 8
            badge_y = rect.center().y() - 10
            badge_rect = QPainterPath()
            badge_rect.addRoundedRect(badge_x, badge_y, badge_width, 20, 6, 6)

            bg_rgba = tier_info["bg"]
            painter.fillPath(badge_rect, QBrush(QColor(*bg_rgba)))
            text_rgb = tier_info["text"]
            painter.setPen(QColor(*text_rgb))
            painter.setFont(QFont("Inter", 8, QFont.Weight.DemiBold))
            painter.drawText(
                int(badge_x), int(badge_y), int(badge_width), 20,
                Qt.AlignmentFlag.AlignCenter, badge_text
            )

        painter.end()

    def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:
        return QSize(0, 44)


class ActivityPanel(QWidget):
    """
    Premium dark-themed activity feed for Wodi's audit log.
    Real-time streaming with color-coded permission tier badges.
    """

    def __init__(self, audit_log: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._audit_log = audit_log
        self.setWindowTitle("Wodi — Activity Log")
        self.setMinimumSize(480, 640)
        self.setStyleSheet("background: #0a0a12;")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Header ────────────────────────────────────────────────
        header_row = QHBoxLayout()

        header = QLabel("Activity Log")
        header.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        header.setStyleSheet("color: rgba(255, 255, 255, 0.92); background: transparent;")
        header_row.addWidget(header)

        header_row.addStretch()

        # Live indicator
        live_dot = QLabel("●  Live")
        live_dot.setFont(QFont("Inter", 10))
        live_dot.setStyleSheet("color: #34d399; background: transparent;")
        header_row.addWidget(live_dot)

        layout.addLayout(header_row)

        # ── Search Bar ────────────────────────────────────────────
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search actions...")
        self._search.setFont(QFont("Inter", 11))
        self._search.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                color: rgba(255, 255, 255, 0.88);
                padding: 10px 16px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(99, 102, 241, 0.35);
                background: rgba(255, 255, 255, 0.08);
            }
            QLineEdit::placeholder {
                color: rgba(255, 255, 255, 0.25);
            }
        """)
        self._search.textChanged.connect(self._filter_entries)
        layout.addWidget(self._search)

        # ── Action List ───────────────────────────────────────────
        self._list = QListWidget()
        self._list.setFont(QFont("Inter", 10))
        self._list.setStyleSheet("""
            QListWidget {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 12px;
                outline: none;
            }
            QListWidget::item {
                padding: 4px 8px;
                border: none;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background: rgba(99, 102, 241, 0.10);
            }
            QListWidget::item:hover {
                background: rgba(255, 255, 255, 0.04);
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 4px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.10);
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.18);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self._list)

        # ── Controls ──────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setFont(QFont("Inter", 10, QFont.Weight.DemiBold))
        refresh_btn.setFixedHeight(36)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: rgba(99, 102, 241, 0.10);
                border: 1px solid rgba(99, 102, 241, 0.20);
                border-radius: 8px;
                color: #818cf8;
                padding: 0 18px;
            }
            QPushButton:hover {
                background: rgba(99, 102, 241, 0.18);
                border-color: rgba(99, 102, 241, 0.35);
            }
        """)
        refresh_btn.clicked.connect(self.refresh)
        ctrl_row.addWidget(refresh_btn)

        ctrl_row.addStretch()

        # Entry count
        self._count_label = QLabel("0 entries")
        self._count_label.setFont(QFont("Inter", 10))
        self._count_label.setStyleSheet("color: rgba(255, 255, 255, 0.30); background: transparent;")
        ctrl_row.addWidget(self._count_label)

        ctrl_row.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFont(QFont("Inter", 10))
        clear_btn.setFixedHeight(36)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: rgba(255, 255, 255, 0.50);
                padding: 0 18px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.08);
                color: rgba(255, 255, 255, 0.70);
            }
        """)
        clear_btn.clicked.connect(self._clear_display)
        ctrl_row.addWidget(clear_btn)

        layout.addLayout(ctrl_row)

    def refresh(self) -> None:
        """Reload recent entries from the audit log."""
        self._list.clear()
        if not self._audit_log:
            item = QListWidgetItem("No audit log connected")
            item.setForeground(QColor(255, 255, 255, 80))
            item.setFont(QFont("Inter", 10))
            self._list.addItem(item)
            self._count_label.setText("0 entries")
            return

        entries = self._audit_log.get_recent(n=50)
        last_session = None

        for e in entries:
            ts = datetime.datetime.fromtimestamp(e["timestamp"]).strftime("%H:%M:%S")
            tier = e.get("permission_tier", "")
            tool = e.get("tool_name", "?")
            denied = e.get("denied", False)
            session = e.get("session_id", "")

            # Session separator
            if session != last_session and last_session is not None:
                sep = QListWidgetItem("")
                sep.setFlags(Qt.ItemFlag.NoItemFlags)
                sep.setSizeHint(QSize(0, 8))
                self._list.addItem(sep)
            last_session = session

            denied_tag = " [DENIED]" if denied else ""
            display = f"{ts}   {tool}{denied_tag}"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, {
                "display": display,
                "tier": tier,
                "tool": tool,
                "timestamp": ts,
            })
            item.setForeground(QColor(255, 255, 255, 200))
            item.setFont(QFont("Inter", 10))
            item.setSizeHint(QSize(0, 44))
            self._list.addItem(item)

        self._count_label.setText(f"{len(entries)} entries")

    def add_entry(self, entry: dict) -> None:
        """Real-time entry addition (called by AuditLog callback)."""
        ts = datetime.datetime.fromtimestamp(entry.get("timestamp", 0)).strftime("%H:%M:%S")
        tier = entry.get("permission_tier", "")
        tool = entry.get("tool", "?")

        # Tier indicator
        tier_dots = {
            "read_only": "●",
            "user_confirm": "●",
            "privileged": "●",
        }
        dot = tier_dots.get(tier, "○")
        display = f"{ts}   {dot}  {tool}"

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, {
            "display": display,
            "tier": tier,
            "tool": tool,
            "timestamp": ts,
        })
        tier_color = TIER_COLORS.get(tier, {})
        text_rgb = tier_color.get("text", (255, 255, 255))
        item.setForeground(QColor(*text_rgb) if isinstance(text_rgb, tuple) else QColor(text_rgb))
        item.setFont(QFont("Inter", 10))
        item.setSizeHint(QSize(0, 44))
        self._list.insertItem(0, item)

        count = self._list.count()
        self._count_label.setText(f"{count} entries")

    def _filter_entries(self, query: str) -> None:
        """Filter visible entries based on search query."""
        query_lower = query.lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                visible = query_lower in data.get("display", "").lower()
                item.setHidden(not visible)
            else:
                item.setHidden(bool(query))

    def _clear_display(self) -> None:
        """Clear the display."""
        self._list.clear()
        self._count_label.setText("0 entries")
