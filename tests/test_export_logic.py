"""Per-day JSON export: date scoping and serialization (no Qt, no display)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controllers.task_controller import TaskController  # noqa: E402
from models.schedule import Frequency  # noqa: E402
from models.task import Priority  # noqa: E402
from models.task_repository import TaskRepository  # noqa: E402

DAY = "2026-09-07"
OTHER = "2026-09-08"


@pytest.fixture()
def controller() -> TaskController:
    repo = TaskRepository(":memory:")
    yield TaskController(repo)
    repo.close()


def test_export_includes_matching_deadline_only(controller):
    controller.create_task("On the day", deadline=DAY, priority=Priority.HIGH)
    controller.create_task("Another day", deadline=OTHER)
    controller.create_task("No deadline")

    records = controller.tasks_for_day(DAY)
    titles = [r["title"] for r in records]
    assert titles == ["On the day"]
    assert records[0]["type"] == "task"
    assert records[0]["priority"] == "High"
    assert records[0]["deadline"] == DAY


def test_export_includes_recurring_occurrence(controller):
    controller.create_task("On the day", deadline=DAY)
    controller.create_schedule(
        "Daily standup",
        start_date="2026-09-01",
        end_date="2026-09-30",
        freq=Frequency.DAILY,
    )

    records = controller.tasks_for_day(DAY)
    types = {r["type"] for r in records}
    assert types == {"task", "occurrence"}
    occ = next(r for r in records if r["type"] == "occurrence")
    assert occ["title"] == "Daily standup"
    assert occ["date"] == DAY


def test_export_excludes_other_days(controller):
    controller.create_task("Elsewhere", deadline=OTHER)
    assert controller.tasks_for_day(DAY) == []


def test_export_day_json_is_valid_json(controller):
    controller.create_task("On the day", deadline=DAY, category="Work")
    payload = controller.export_day_json(DAY)
    data = json.loads(payload)  # round-trips → valid JSON
    assert data["date"] == DAY
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["category"] == "Work"
