"""Notification bell + slide-in panel — a visual shell (no real backend).

This reproduces the design mockup's notification affordance: a bell button in
the header with an unread badge, and a pop-over panel listing recent alerts.
The items here are static placeholders; wiring them to real events would be a
follow-up that adds a notifications model/controller. Presentation only.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from views import icons, theme

# Static sample feed (kind, title, time, body, unread) for the shell.
_SAMPLE = [
    ("pr", "PR #482 needs your review", "2m", "auth refactor · Contoso / webapp", True),
    ("sync", "Azure sync complete", "14m", "2 created · 1 completed", True),
    ("reminder", "Task due today", "1h", "Write release notes for v2.3.0", True),
    ("schedule", "Recurring task generated", "3h", "Daily standup notes", False),
]
_KIND_ICON = {
    "pr": icons.PR,
    "sync": icons.SYNC,
    "reminder": icons.REMINDER,
    "schedule": icons.SCHEDULE,
}


class _Panel(QFrame):
    """Frameless pop-over listing recent notifications."""

    def __init__(self, dark: bool, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self._dark = dark
        self.setObjectName("notifPanel")
        self.setFixedWidth(352)
        self._items = list(_SAMPLE)
        self._dots: list[QLabel] = []
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header.
        header = QWidget()
        header.setObjectName("notifPanelHeader")
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(14, 11, 10, 11)
        title = QLabel("Notifications")
        title.setObjectName("notifPanelTitle")
        unread = sum(1 for *_, u in self._items if u)
        self._count = QLabel(f"{unread} unread")
        self._count.setObjectName("dayCaption")
        count = self._count
        mark = QPushButton("Mark all read")
        mark.setObjectName("linkButton")
        mark.setCursor(Qt.CursorShape.PointingHandCursor)
        mark.clicked.connect(self._mark_all_read)
        close = QPushButton("✕")
        close.setObjectName("linkButton")
        close.setFixedWidth(24)
        close.clicked.connect(self.close)
        hrow.addWidget(title)
        hrow.addWidget(count)
        hrow.addStretch(1)
        hrow.addWidget(mark)
        hrow.addWidget(close)
        outer.addWidget(header)

        # Scrolling list.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._list = QVBoxLayout(body)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(0)
        for kind, ttl, when, text, is_unread in self._items:
            self._list.addWidget(self._make_item(kind, ttl, when, text, is_unread))
        self._list.addStretch(1)
        scroll.setWidget(body)
        scroll.setMinimumHeight(min(84 * len(self._items) + 8, 380))
        outer.addWidget(scroll)

    def _make_item(self, kind, ttl, when, text, is_unread) -> QWidget:
        accent = QColor(theme.token("accent", self._dark))
        row = QFrame()
        row.setObjectName("notifItem")
        r = QHBoxLayout(row)
        r.setContentsMargins(14, 11, 14, 11)
        r.setSpacing(11)

        icon = QLabel()
        icon.setObjectName("notifItemIcon")
        icon.setFixedSize(32, 32)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(icons.svg_icon(_KIND_ICON.get(kind, icons.REMINDER), accent, 16).pixmap(16, 16))
        r.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(8)
        t = QLabel(ttl)
        t.setObjectName("notifItemTitle")
        t.setWordWrap(True)
        stamp = QLabel(when)
        stamp.setObjectName("notifItemTime")
        top.addWidget(t, 1)
        top.addWidget(stamp, 0, Qt.AlignmentFlag.AlignTop)
        col.addLayout(top)
        b = QLabel(text)
        b.setObjectName("notifItemBody")
        b.setWordWrap(True)
        col.addWidget(b)
        r.addLayout(col, 1)

        if is_unread:
            dot = QLabel()
            dot.setObjectName("notifUnreadDot")
            dot.setFixedSize(8, 8)
            self._dots.append(dot)
            r.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _mark_all_read(self) -> None:
        for dot in self._dots:
            dot.hide()
        self._count.setText("0 unread")
        parent = self.parent()
        if isinstance(parent, NotificationBell):
            parent.set_unread(0)


class NotificationBell(QToolButton):
    """Header bell button with an unread badge; opens the notifications panel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("bell")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Notifications")
        self.setFixedSize(30, 26)
        self._dark = False
        self._unread = sum(1 for *_, u in _SAMPLE if u)

        self._badge = QLabel(self)
        self._badge.setObjectName("notifBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._panel: _Panel | None = None
        self.clicked.connect(self._toggle_panel)
        self._sync_badge()

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        text = QColor(theme.token("text", dark))
        self.setIcon(icons.svg_icon(icons.BELL, text, 17))
        # A theme switch invalidates the open panel's baked-in colours.
        if self._panel is not None:
            self._panel.close()
            self._panel = None

    def set_unread(self, n: int) -> None:
        self._unread = max(0, n)
        self._sync_badge()

    def _sync_badge(self) -> None:
        if self._unread > 0:
            self._badge.setText(str(self._unread))
            self._badge.adjustSize()
            self._badge.show()
            self._badge.move(self.width() - self._badge.width() - 1, 0)
        else:
            self._badge.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._sync_badge()

    def _toggle_panel(self) -> None:
        if self._panel is not None and self._panel.isVisible():
            self._panel.close()
            self._panel = None
            return
        self._panel = _Panel(self._dark, self)
        pos = self.mapToGlobal(QPoint(self.width() - self._panel.width(), self.height() + 6))
        self._panel.move(pos)
        self._panel.show()
