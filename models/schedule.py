"""Recurring-schedule entities and pure recurrence logic.

A ``Schedule`` is a recurring task definition (a title plus a recurrence rule
over a start→end date range). Projecting a schedule onto a single calendar day
yields an ``Occurrence``, which deliberately exposes the *same* attribute names
as :class:`models.task.Task` so the table-rendering code can treat both alike.

This module is UI- and storage-free so the recurrence maths stay unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional, Set

from models.task import Priority


class Frequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @property
    def label(self) -> str:
        return self.value.capitalize()


def _parse(iso: str) -> date:
    return datetime.fromisoformat(iso).date()


@dataclass
class Schedule:
    """A recurring task definition.

    ``deadline`` has no meaning here; the recurrence range (start/end) plus the
    frequency describe when the task appears. ``id`` is None until persisted.
    """
    title: str
    start_date: str                                   # ISO date, inclusive
    end_date: str                                     # ISO date, inclusive
    freq: Frequency = Frequency.DAILY
    weekdays: Set[int] = field(default_factory=set)   # 0=Mon .. 6=Sun (weekly)
    description: str = ""
    priority: Priority = Priority.MEDIUM
    category: str = ""
    cancelled_from: Optional[str] = None              # ISO date, or None
    sort_order: int = 0
    id: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


@dataclass
class Occurrence:
    """A schedule projected onto one date. Duck-types as ``Task`` for the view."""
    schedule_id: int
    date: str                          # ISO date this occurrence falls on
    title: str
    description: str
    priority: Priority
    category: str
    completed: bool

    @property
    def deadline(self) -> str:
        """The occurrence's own day — lets the view show it in the Deadline column."""
        return self.date

    @property
    def is_overdue(self) -> bool:
        if self.completed:
            return False
        try:
            return _parse(self.date) < datetime.now().date()
        except ValueError:
            return False


def occurs_on(schedule: Schedule, day: date) -> bool:
    """True if the schedule produces an occurrence on ``day`` (ignoring overrides)."""
    start = _parse(schedule.start_date)
    end = _parse(schedule.end_date)
    if day < start or day > end:
        return False
    if schedule.cancelled_from and day >= _parse(schedule.cancelled_from):
        return False

    if schedule.freq is Frequency.DAILY:
        return True
    if schedule.freq is Frequency.WEEKLY:
        weekdays = schedule.weekdays or {start.weekday()}
        return day.weekday() in weekdays
    if schedule.freq is Frequency.MONTHLY:
        # Same day-of-month as the start; months without that day are skipped.
        return day.day == start.day
    return False
