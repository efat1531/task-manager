"""Notifications settings tab — a visual shell matching the design mockup.

The controls here mirror the mockup (master switch, per-source event toggles,
and delivery options) but are not yet wired to persistence or to the notifier;
they exist so the UI matches the design. Turning them into real settings is a
follow-up (QSettings-backed, in ``services/``). Presentation only.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_AZURE = [
    ("PR assigned for review", "When you're added as a reviewer"),
    ("Your PR was approved or rejected", "Vote changes on PRs you created"),
    ("New comment on your PR", "Unresolved comment threads"),
]
_LINEAR = [
    ("Issue assigned to you", "A synced status turns it into a task"),
]
_TASKS = [
    ("Task due today", "A summary when the app starts"),
    ("Overdue task", "When a deadline has passed"),
    ("Recurring task generated", "A schedule creates today's task"),
]


class NotificationsTab(QWidget):
    """Static settings surface for desktop notifications (no backend wiring)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(16)

        heading = QLabel("Notifications")
        heading.setObjectName("pageHeading")
        subtitle = QLabel(
            "Choose which events send a desktop notification. Alerts appear in the "
            "bell menu and, when enabled, as system notifications."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(subtitle)

        # Master switch card.
        master = QFrame()
        master.setObjectName("card")
        mbox = QVBoxLayout(master)
        mbox.setContentsMargins(16, 14, 16, 14)
        mbox.setSpacing(4)
        self._master = QCheckBox("Enable desktop notifications")
        self._master.setObjectName("cardHeading")
        self._master.setChecked(True)
        master_hint = QLabel(
            "Master switch — turns everything below on or off. "
            "Delivered via the OS notifier (plyer)."
        )
        master_hint.setObjectName("mutedHint")
        master_hint.setWordWrap(True)
        master_hint.setContentsMargins(24, 0, 0, 0)
        mbox.addWidget(self._master)
        mbox.addWidget(master_hint)
        root.addWidget(master)

        # 2×2 grid of event / delivery cards.
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.addWidget(self._event_card("Azure DevOps", _AZURE), 0, 0)
        grid.addWidget(self._event_card("Linear", _LINEAR), 0, 1)
        grid.addWidget(self._event_card("Tasks && reminders", _TASKS), 1, 0)
        grid.addWidget(self._delivery_card(), 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)

        # Actions + status.
        actions = QHBoxLayout()
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(lambda: self._status.setText("Notification settings saved."))
        test = QPushButton("Send a test notification")
        test.clicked.connect(lambda: self._status.setText("Test notification sent."))
        actions.addWidget(save)
        actions.addWidget(test)
        actions.addStretch(1)
        root.addLayout(actions)

        self._status = QLabel("Notifications are enabled.")
        self._status.setObjectName("statusStrip")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def _event_card(self, title: str, rows: list[tuple[str, str]]) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(0)
        for i, (label, hint) in enumerate(rows):
            layout.addWidget(self._toggle_row(label, hint, checked=True, top_rule=i > 0))
        layout.addStretch(1)
        return box

    @staticmethod
    def _toggle_row(label: str, hint: str, *, checked: bool, top_rule: bool) -> QWidget:
        row = QFrame()
        row.setObjectName("ruledRow" if top_rule else "plainRow")
        r = QHBoxLayout(row)
        r.setContentsMargins(0, 9, 0, 9)
        r.setSpacing(9)
        check = QCheckBox()
        check.setChecked(checked)
        r.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        title = QLabel(label)
        title.setObjectName("toggleTitle")
        sub = QLabel(hint)
        sub.setObjectName("toggleHint")
        sub.setWordWrap(True)
        col.addWidget(title)
        col.addWidget(sub)
        r.addLayout(col, 1)
        return row

    def _delivery_card(self) -> QGroupBox:
        box = QGroupBox("Delivery")
        grid = QGridLayout(box)
        grid.setContentsMargins(16, 16, 16, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)

        grid.addWidget(QLabel("Play a sound"), 0, 0)
        seg = QWidget()
        seg_row = QHBoxLayout(seg)
        seg_row.setContentsMargins(0, 0, 0, 0)
        seg_row.setSpacing(0)
        on = QPushButton("On")
        off = QPushButton("Off")
        group = QButtonGroup(box)
        for b in (on, off):
            b.setCheckable(True)
            b.setObjectName("segButton")
            group.addButton(b)
            seg_row.addWidget(b)
        on.setChecked(True)
        grid.addWidget(seg, 0, 1, Qt.AlignmentFlag.AlignRight)

        grid.addWidget(QLabel("Quiet hours"), 1, 0)
        quiet = QWidget()
        qrow = QHBoxLayout(quiet)
        qrow.setContentsMargins(0, 0, 0, 0)
        qrow.setSpacing(6)
        start = QLineEdit("22:00")
        end = QLineEdit("07:00")
        for e in (start, end):
            e.setFixedWidth(64)
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        to = QLabel("to")
        to.setObjectName("mutedHint")
        qrow.addWidget(start)
        qrow.addWidget(to)
        qrow.addWidget(end)
        grid.addWidget(quiet, 1, 1, Qt.AlignmentFlag.AlignRight)
        grid.setColumnStretch(0, 1)
        return box
