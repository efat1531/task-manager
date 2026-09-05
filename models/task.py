"""Task entity — a plain data object, completely UI- and storage-unaware."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Optional


class Priority(IntEnum):
    """Priority levels. Higher value = more urgent (useful for sorting)."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @property
    def label(self) -> str:
        return self.name.capitalize()

    @classmethod
    def from_label(cls, label: str) -> "Priority":
        return cls[label.strip().upper()]


@dataclass
class Task:
    """A single task.

    `deadline` is stored/handled as an ISO-8601 date string ("YYYY-MM-DD")
    or None. `id` is None until the task has been persisted.
    """
    title: str
    description: str = ""
    priority: Priority = Priority.MEDIUM
    deadline: Optional[str] = None          # ISO 8601 date, e.g. "2026-09-30"
    completed: bool = False
    category: str = ""
    sort_order: int = 0
    id: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def _due_date(self):
        """Parsed deadline date, or None if unset/uncompletable/malformed."""
        if not self.deadline:
            return None
        try:
            return datetime.fromisoformat(self.deadline).date()
        except ValueError:
            return None

    @property
    def is_overdue(self) -> bool:
        """True if the task has a past deadline and is not yet complete."""
        if self.completed:
            return False
        due = self._due_date()
        return due is not None and due < datetime.now().date()

    @property
    def is_due_today(self) -> bool:
        """True if an incomplete task's deadline is today."""
        if self.completed:
            return False
        due = self._due_date()
        return due is not None and due == datetime.now().date()
