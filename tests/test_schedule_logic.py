"""Recurrence logic + schedule persistence tests (in-memory DB, headless)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controllers.task_controller import TaskController  # noqa: E402
from models.schedule import Frequency, Schedule, occurs_on  # noqa: E402
from models.task_repository import TaskRepository  # noqa: E402


@pytest.fixture()
def controller() -> TaskController:
    repo = TaskRepository(":memory:")
    yield TaskController(repo)
    repo.close()


# ---- pure occurs_on ------------------------------------------------------
def _sched(**kw) -> Schedule:
    base = dict(title="s", start_date="2026-01-01", end_date="2026-12-31")
    base.update(kw)
    return Schedule(**base)


def test_daily_occurs_every_day():
    s = _sched(freq=Frequency.DAILY, start_date="2026-03-01", end_date="2026-03-05")
    assert occurs_on(s, date(2026, 3, 3)) is True
    assert occurs_on(s, date(2026, 2, 28)) is False  # before range
    assert occurs_on(s, date(2026, 3, 6)) is False   # after range


def test_weekly_multiple_weekdays():
    # Mon=0, Thu=3, Fri=4.  2026-03-02 is a Monday.
    s = _sched(freq=Frequency.WEEKLY, weekdays={0, 3, 4},
               start_date="2026-03-01", end_date="2026-03-31")
    assert occurs_on(s, date(2026, 3, 2)) is True   # Monday
    assert occurs_on(s, date(2026, 3, 5)) is True   # Thursday
    assert occurs_on(s, date(2026, 3, 6)) is True   # Friday
    assert occurs_on(s, date(2026, 3, 3)) is False  # Tuesday
    assert occurs_on(s, date(2026, 3, 8)) is False  # Sunday


def test_weekly_defaults_to_start_weekday():
    # No weekdays chosen -> uses the start date's weekday (2026-03-04 is Wed).
    s = _sched(freq=Frequency.WEEKLY, weekdays=set(),
               start_date="2026-03-04", end_date="2026-03-31")
    assert occurs_on(s, date(2026, 3, 11)) is True   # next Wednesday
    assert occurs_on(s, date(2026, 3, 12)) is False  # Thursday


def test_monthly_skips_months_without_the_day():
    s = _sched(freq=Frequency.MONTHLY, start_date="2026-01-31", end_date="2026-12-31")
    assert occurs_on(s, date(2026, 1, 31)) is True
    assert occurs_on(s, date(2026, 3, 31)) is True
    assert occurs_on(s, date(2026, 2, 28)) is False  # February has no 31st


def test_cancelled_from_hides_on_or_after():
    s = _sched(freq=Frequency.DAILY, start_date="2026-03-01", end_date="2026-03-31",
               cancelled_from="2026-03-10")
    assert occurs_on(s, date(2026, 3, 9)) is True
    assert occurs_on(s, date(2026, 3, 10)) is False
    assert occurs_on(s, date(2026, 3, 11)) is False


# ---- controller + repository --------------------------------------------
def test_create_and_list_occurrences(controller):
    controller.create_schedule("Standup", "2026-03-01", "2026-03-03",
                               freq=Frequency.DAILY)
    occ = controller.occurrences_on("2026-03-02")
    assert len(occ) == 1
    assert occ[0].title == "Standup"
    assert occ[0].completed is False
    assert controller.occurrences_on("2026-04-01") == []  # outside range


def test_complete_one_day_leaves_next_pending(controller):
    s = controller.create_schedule("Water plants", "2026-03-01", "2026-03-05")
    controller.toggle_occurrence(s.id, "2026-03-02")
    assert controller.occurrences_on("2026-03-02")[0].completed is True
    assert controller.occurrences_on("2026-03-03")[0].completed is False
    # Toggling again clears it back to pending.
    controller.toggle_occurrence(s.id, "2026-03-02")
    assert controller.occurrences_on("2026-03-02")[0].completed is False


def test_cancel_single_day_hides_only_that_date(controller):
    s = controller.create_schedule("Gym", "2026-03-01", "2026-03-05")
    controller.cancel_occurrence_day(s.id, "2026-03-03")
    assert controller.occurrences_on("2026-03-03") == []
    assert len(controller.occurrences_on("2026-03-04")) == 1
    # Undoable.
    assert controller.undo() is True
    assert len(controller.occurrences_on("2026-03-03")) == 1


def test_cancel_from_forward_keeps_past(controller):
    s = controller.create_schedule("Meds", "2026-03-01", "2026-03-10")
    controller.toggle_occurrence(s.id, "2026-03-02")  # completed in the past
    controller.cancel_schedule_from(s.id, "2026-03-05")
    assert controller.occurrences_on("2026-03-02")[0].completed is True  # kept
    assert len(controller.occurrences_on("2026-03-04")) == 1             # before cutoff
    assert controller.occurrences_on("2026-03-05") == []                 # on cutoff
    assert controller.occurrences_on("2026-03-09") == []                 # after cutoff
    # Undo restores the future occurrences.
    assert controller.undo() is True
    assert len(controller.occurrences_on("2026-03-06")) == 1


def test_schedule_round_trip_persists_fields(controller):
    controller.create_schedule("Review", "2026-03-01", "2026-03-31",
                               freq=Frequency.WEEKLY, weekdays={0, 4},
                               description="weekly review", category="Work")
    (s,) = controller._repo.list_schedules()
    assert s.freq is Frequency.WEEKLY
    assert s.weekdays == {0, 4}
    assert s.category == "Work"
    assert s.description == "weekly review"


def test_delete_schedule_cascades_overrides(controller):
    s = controller.create_schedule("Temp", "2026-03-01", "2026-03-05")
    controller.toggle_occurrence(s.id, "2026-03-02")
    controller.delete_schedule(s.id)
    assert controller._repo.list_schedules() == []
    assert controller._repo.list_overrides(s.id) == {}
