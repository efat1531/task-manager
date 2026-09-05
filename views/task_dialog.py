"""Add/Edit task dialog with a native calendar date picker."""
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
    QPushButton,
)

from models.task import Priority, Task


class TaskDialog(QDialog):
    """Collects task fields. Use ``get_values()`` after ``exec()`` returns Accepted."""

    def __init__(self, parent=None, task: Optional[Task] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Task" if task else "New Task")
        self.setMinimumWidth(380)

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

        # Deadline: a checkbox toggles whether a due date applies.
        self._has_deadline = QCheckBox("Has deadline")
        self._deadline = QDateEdit()
        self._deadline.setCalendarPopup(True)
        self._deadline.setDisplayFormat("yyyy-MM-dd")
        self._deadline.setDate(QDate.currentDate())
        self._deadline.setEnabled(False)
        self._has_deadline.toggled.connect(self._deadline.setEnabled)

        deadline_row = QHBoxLayout()
        deadline_row.addWidget(self._has_deadline)
        deadline_row.addWidget(self._deadline, 1)

        form = QFormLayout(self)
        form.addRow("Title", self._title)
        form.addRow("Description", self._description)
        form.addRow("Priority", self._priority)
        form.addRow("Category", self._category)
        form.addRow("Deadline", deadline_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if task is not None:
            self._load(task)
        else:
            # New tasks default to Medium; Urgent should be a deliberate choice.
            self._priority.setCurrentIndex(self._priority.findData(Priority.MEDIUM))

    # ---- populate when editing ------------------------------------------
    def _load(self, task: Task) -> None:
        self._title.setText(task.title)
        self._description.setPlainText(task.description)
        idx = self._priority.findData(task.priority)
        if idx >= 0:
            self._priority.setCurrentIndex(idx)
        self._category.setText(task.category)
        if task.deadline:
            self._has_deadline.setChecked(True)
            self._deadline.setDate(QDate.fromString(task.deadline, "yyyy-MM-dd"))

    # ---- validation ------------------------------------------------------
    def _on_accept(self) -> None:
        if not self._title.text().strip():
            QMessageBox.warning(self, "Missing title", "Please enter a task title.")
            self._title.setFocus()
            return
        self.accept()

    # ---- output ----------------------------------------------------------
    def get_values(self) -> dict:
        deadline = (
            self._deadline.date().toString("yyyy-MM-dd")
            if self._has_deadline.isChecked()
            else None
        )
        return {
            "title": self._title.text().strip(),
            "description": self._description.toPlainText().strip(),
            "priority": self._priority.currentData(),
            "deadline": deadline,
            "category": self._category.text().strip(),
        }
