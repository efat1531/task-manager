"""Add/Edit dialog for one-off tasks *and* recurring schedules.

A "Repeat / schedule" checkbox flips the dialog between two modes:
- unchecked: a one-off task with an optional single deadline (original behavior);
- checked: a schedule with a start/end range, a frequency, and — for weekly —
  a set of weekdays.

``get_values()`` returns a dict whose ``schedule`` flag tells the caller which
kind to create/update.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QWidget,
)

from models.schedule import Frequency, Schedule
from models.task import Priority, Task

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # index = weekday()


class TaskDialog(QDialog):
    """Collects task/schedule fields. Use ``get_values()`` after Accepted."""

    def __init__(
        self,
        parent=None,
        task: Optional[Task] = None,
        schedule: Optional[Schedule] = None,
    ) -> None:
        super().__init__(parent)
        editing = task is not None or schedule is not None
        self.setWindowTitle("Edit Task" if editing else "New Task")
        self.setMinimumWidth(420)

        self._title = QLineEdit()
        self._title.setPlaceholderText("What needs doing?")

        self._description = QPlainTextEdit()
        self._description.setPlaceholderText("Optional details…")
        self._description.setFixedHeight(80)

        self._priority = QComboBox()
        for p in (Priority.URGENT, Priority.HIGH, Priority.MEDIUM, Priority.LOW):
            self._priority.addItem(p.label, p)

        self._category = QLineEdit()
        self._category.setPlaceholderText("Optional tag / project")

        # One-off deadline (checkbox toggles whether a due date applies).
        self._has_deadline = QCheckBox("Has deadline")
        self._deadline = QDateEdit()
        self._deadline.setCalendarPopup(True)
        self._deadline.setDisplayFormat("yyyy-MM-dd")
        self._deadline.setDate(QDate.currentDate())
        self._deadline.setEnabled(False)
        self._has_deadline.toggled.connect(self._deadline.setEnabled)
        deadline_row = QWidget()
        dl = QHBoxLayout(deadline_row)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self._has_deadline)
        dl.addWidget(self._deadline, 1)

        # Repeat / schedule toggle + its fields.
        self._repeat = QCheckBox("Repeat / schedule")
        self._repeat.toggled.connect(self._on_repeat_toggled)
        self._schedule_widget = self._build_schedule_widget()

        form = QFormLayout(self)
        self._form = form
        form.addRow("Title", self._title)
        form.addRow("Description", self._description)
        form.addRow("Priority", self._priority)
        form.addRow("Category", self._category)
        form.addRow("Deadline", deadline_row)
        self._deadline_row = deadline_row
        form.addRow("", self._repeat)
        form.addRow("Schedule", self._schedule_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._on_repeat_toggled(False)  # start in one-off mode

        if task is not None:
            self._load_task(task)
        elif schedule is not None:
            self._load_schedule(schedule)
        else:
            self._priority.setCurrentIndex(self._priority.findData(Priority.MEDIUM))

    # ---- schedule sub-widget --------------------------------------------
    def _build_schedule_widget(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self._start_date = QDateEdit()
        self._end_date = QDateEdit()
        for edit in (self._start_date, self._end_date):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            edit.setDate(QDate.currentDate())

        self._freq = QComboBox()
        for f in (Frequency.DAILY, Frequency.WEEKLY, Frequency.MONTHLY, Frequency.CUSTOM):
            self._freq.addItem(f.label, f)
        self._freq.currentIndexChanged.connect(self._update_weekday_visibility)

        self._weekday_row = QWidget()
        wl = QHBoxLayout(self._weekday_row)
        wl.setContentsMargins(0, 0, 0, 0)
        self._weekday_checks = []
        for name in _WEEKDAYS:
            cb = QCheckBox(name)
            self._weekday_checks.append(cb)
            wl.addWidget(cb)

        layout.addRow("Start", self._start_date)
        layout.addRow("End", self._end_date)
        layout.addRow("Frequency", self._freq)
        layout.addRow("Repeat on", self._weekday_row)
        self._schedule_form = layout
        return widget

    # ---- visibility toggles ---------------------------------------------
    def _on_repeat_toggled(self, repeat: bool) -> None:
        self._form.setRowVisible(self._deadline_row, not repeat)
        self._form.setRowVisible(self._schedule_widget, repeat)
        if repeat:
            self._update_weekday_visibility()
        self.adjustSize()

    def _update_weekday_visibility(self) -> None:
        # Weekday pickers only apply to a Custom recurrence. currentData() may come
        # back as the flattened str value (Frequency is a str-Enum), so coerce.
        custom = Frequency(self._freq.currentData()) is Frequency.CUSTOM
        self._schedule_form.setRowVisible(self._weekday_row, custom)

    # ---- populate when editing ------------------------------------------
    def _load_common(self, title, description, priority, category) -> None:
        self._title.setText(title)
        self._description.setPlainText(description)
        idx = self._priority.findData(priority)
        if idx >= 0:
            self._priority.setCurrentIndex(idx)
        self._category.setText(category)

    def _load_task(self, task: Task) -> None:
        self._load_common(task.title, task.description, task.priority, task.category)
        if task.deadline:
            self._has_deadline.setChecked(True)
            self._deadline.setDate(QDate.fromString(task.deadline, "yyyy-MM-dd"))

    def _load_schedule(self, schedule: Schedule) -> None:
        self._load_common(schedule.title, schedule.description,
                          schedule.priority, schedule.category)
        self._repeat.setChecked(True)
        self._start_date.setDate(QDate.fromString(schedule.start_date, "yyyy-MM-dd"))
        self._end_date.setDate(QDate.fromString(schedule.end_date, "yyyy-MM-dd"))
        fidx = self._freq.findData(schedule.freq)
        if fidx >= 0:
            self._freq.setCurrentIndex(fidx)
        for i, cb in enumerate(self._weekday_checks):
            cb.setChecked(i in schedule.weekdays)
        self._update_weekday_visibility()

    # ---- validation ------------------------------------------------------
    def _on_accept(self) -> None:
        if not self._title.text().strip():
            QMessageBox.warning(self, "Missing title", "Please enter a task title.")
            self._title.setFocus()
            return
        if self._repeat.isChecked():
            if self._end_date.date() < self._start_date.date():
                QMessageBox.warning(self, "Invalid range",
                                    "End date cannot be before the start date.")
                return
        self.accept()

    # ---- output ----------------------------------------------------------
    def get_values(self) -> dict:
        common = {
            "title": self._title.text().strip(),
            "description": self._description.toPlainText().strip(),
            # Qt may return enums stored as userData flattened to their base type
            # (Frequency is a str-Enum), so coerce back to the enum explicitly.
            "priority": Priority(self._priority.currentData()),
            "category": self._category.text().strip(),
        }
        if self._repeat.isChecked():
            weekdays = {i for i, cb in enumerate(self._weekday_checks) if cb.isChecked()}
            common.update(
                schedule=True,
                start_date=self._start_date.date().toString("yyyy-MM-dd"),
                end_date=self._end_date.date().toString("yyyy-MM-dd"),
                freq=Frequency(self._freq.currentData()),
                weekdays=weekdays,
            )
        else:
            deadline = (
                self._deadline.date().toString("yyyy-MM-dd")
                if self._has_deadline.isChecked()
                else None
            )
            common.update(schedule=False, deadline=deadline)
        return common
