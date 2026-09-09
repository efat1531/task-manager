"""Notifications settings tab — persisted preferences that gate OS delivery.

The controls mirror the design mockup (master switch, per-source event toggles,
and delivery options) and are wired to ``services.notification_settings``: Save
persists a ``NotificationConfig`` to QSettings, and the reminder / sync code
reads it live to decide what fires. "Send a test notification" calls the OS
notifier directly.
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

from models.notification import (
    SOURCE_AZURE_COMMENT,
    SOURCE_AZURE_REVIEW,
    SOURCE_AZURE_VOTE,
    SOURCE_LINEAR,
    SOURCE_TASK_DUE,
    SOURCE_TASK_OVERDUE,
    NotificationConfig,
)
from services import notification_settings, notifier

# (source constant, label, hint) per event row.
_AZURE = [
    (SOURCE_AZURE_REVIEW, "PR assigned for review", "When you're added as a reviewer"),
    (SOURCE_AZURE_VOTE, "Changes requested on your PR", "A reviewer asks for changes"),
    (SOURCE_AZURE_COMMENT, "New comment on your PR", "Unresolved comment threads"),
]
_LINEAR = [
    (SOURCE_LINEAR, "Issue assigned to you", "A synced status turns it into a task"),
]
_TASKS = [
    (SOURCE_TASK_DUE, "Task due today", "A reminder while a deadline is today"),
    (SOURCE_TASK_OVERDUE, "Overdue task", "When a deadline has passed"),
]


class NotificationsTab(QWidget):
    """Settings surface for desktop notifications, backed by QSettings."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._toggles: dict[str, QCheckBox] = {}
        self._build_ui()
        self._load_into_widgets(notification_settings.load_config())

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
        save.clicked.connect(self._on_save)
        test = QPushButton("Send a test notification")
        test.clicked.connect(self._on_test)
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

    def _event_card(self, title: str, rows: list[tuple[str, str, str]]) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(0)
        for i, (source, label, hint) in enumerate(rows):
            layout.addWidget(self._toggle_row(source, label, hint, top_rule=i > 0))
        layout.addStretch(1)
        return box

    def _toggle_row(self, source: str, label: str, hint: str, *, top_rule: bool) -> QWidget:
        row = QFrame()
        row.setObjectName("ruledRow" if top_rule else "plainRow")
        r = QHBoxLayout(row)
        r.setContentsMargins(0, 9, 0, 9)
        r.setSpacing(9)
        check = QCheckBox()
        check.setChecked(True)
        self._toggles[source] = check
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
        self._sound_on = QPushButton("On")
        off = QPushButton("Off")
        group = QButtonGroup(box)
        for b in (self._sound_on, off):
            b.setCheckable(True)
            b.setObjectName("segButton")
            group.addButton(b)
            seg_row.addWidget(b)
        self._sound_on.setChecked(True)
        grid.addWidget(seg, 0, 1, Qt.AlignmentFlag.AlignRight)

        grid.addWidget(QLabel("Quiet hours"), 1, 0)
        quiet = QWidget()
        qrow = QHBoxLayout(quiet)
        qrow.setContentsMargins(0, 0, 0, 0)
        qrow.setSpacing(6)
        self._quiet_start = QLineEdit("22:00")
        self._quiet_end = QLineEdit("07:00")
        for e in (self._quiet_start, self._quiet_end):
            e.setFixedWidth(64)
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        to = QLabel("to")
        to.setObjectName("mutedHint")
        qrow.addWidget(self._quiet_start)
        qrow.addWidget(to)
        qrow.addWidget(self._quiet_end)
        grid.addWidget(quiet, 1, 1, Qt.AlignmentFlag.AlignRight)
        grid.setColumnStretch(0, 1)
        return box

    # ---- persistence -----------------------------------------------------
    def _load_into_widgets(self, cfg: NotificationConfig) -> None:
        self._master.setChecked(cfg.enabled)
        for source, check in self._toggles.items():
            check.setChecked(cfg.source_enabled(source))
        self._sound_on.setChecked(cfg.sound)
        self._quiet_start.setText(cfg.quiet_start)
        self._quiet_end.setText(cfg.quiet_end)

    def _config_from_widgets(self) -> NotificationConfig:
        cfg = NotificationConfig(
            enabled=self._master.isChecked(),
            sound=self._sound_on.isChecked(),
            quiet_start=self._quiet_start.text().strip(),
            quiet_end=self._quiet_end.text().strip(),
        )
        for source, check in self._toggles.items():
            setattr(cfg, source, check.isChecked())
        return cfg

    def _on_save(self) -> None:
        notification_settings.save_config(self._config_from_widgets())
        self._status.setText("Notification settings saved.")

    def _on_test(self) -> None:
        # Deliberately bypasses gating — the point is to verify the OS path works.
        if not notifier.notifications_available():
            self._status.setText(
                "Desktop notifications unavailable (plyer backend missing)."
            )
            return
        if notifier.notify("Task Manager", "This is a test notification."):
            self._status.setText("Test notification sent.")
        else:
            self._status.setText("Could not send the test notification.")
