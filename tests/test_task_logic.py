"""Logic-layer tests — repository + controller against an in-memory database.

No Qt / display needed, so these run anywhere (including headless CI).
Run with:  pytest
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Allow running pytest from the project root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controllers.task_controller import TaskController  # noqa: E402
from models.task import Priority, Task  # noqa: E402
from models.task_repository import TaskRepository  # noqa: E402


@pytest.fixture()
def controller() -> TaskController:
    repo = TaskRepository(":memory:")
    yield TaskController(repo)
    repo.close()


def test_create_and_list(controller):
    controller.create_task("Write report", priority=Priority.HIGH)
    tasks = controller.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].title == "Write report"
    assert tasks[0].priority is Priority.HIGH
    assert tasks[0].id is not None


def test_empty_title_rejected(controller):
    with pytest.raises(ValueError):
        controller.create_task("   ")


def test_update_task(controller):
    task = controller.create_task("Draft")
    task.title = "Final draft"
    task.priority = Priority.LOW
    controller.update_task(task)
    reloaded = controller.list_tasks()[0]
    assert reloaded.title == "Final draft"
    assert reloaded.priority is Priority.LOW


def test_toggle_completed_persists(controller):
    task = controller.create_task("Buy milk")
    assert task.completed is False
    controller.toggle_completed(task)
    assert controller.list_tasks()[0].completed is True


def test_delete_task(controller):
    task = controller.create_task("Temp")
    controller.delete_task(task.id)
    assert controller.list_tasks() == []


def test_sort_by_priority(controller):
    controller.create_task("low", priority=Priority.LOW)
    controller.create_task("high", priority=Priority.HIGH)
    controller.create_task("med", priority=Priority.MEDIUM)
    titles = [t.title for t in controller.list_tasks(order_by="priority")]
    assert titles == ["high", "med", "low"]


def test_sort_by_deadline_nulls_last(controller):
    controller.create_task("no-date")
    controller.create_task("soon", deadline="2026-01-01")
    controller.create_task("later", deadline="2026-12-31")
    titles = [t.title for t in controller.list_tasks(order_by="deadline")]
    assert titles == ["soon", "later", "no-date"]


def test_is_overdue():
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
    assert Task("past", deadline=yesterday).is_overdue is True
    assert Task("future", deadline=tomorrow).is_overdue is False
    assert Task("done", deadline=yesterday, completed=True).is_overdue is False
    assert Task("no-deadline").is_overdue is False
