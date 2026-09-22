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


def test_reset_database_clears_everything(controller):
    controller.create_task("Task A")
    controller.create_task("Task B")
    controller.create_schedule("Standup", "2026-01-01", "2026-12-31")
    controller.delete_task(controller.list_tasks()[0].id)  # leave something to undo
    assert controller.can_undo() is True

    controller.reset_database()

    assert controller.list_tasks() == []
    assert controller.list_schedules() == []
    assert controller.can_undo() is False


def test_reset_database_resets_ids(controller):
    controller.create_task("First")
    controller.reset_database()
    fresh = controller.create_task("After reset")
    # AUTOINCREMENT counter is reset, so ids start over from 1.
    assert fresh.id == 1


def test_reorder_persists_new_manual_order(controller):
    a = controller.create_task("a")
    b = controller.create_task("b")
    c = controller.create_task("c")
    controller.reorder_tasks([c.id, a.id, b.id])
    titles = [t.title for t in controller.list_tasks(order_by="sort_order")]
    assert titles == ["c", "a", "b"]
    # sort_order values should be contiguous 0..n-1 in the new order.
    orders = [t.sort_order for t in controller.list_tasks(order_by="sort_order")]
    assert orders == [0, 1, 2]


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


def test_search_matches_title_and_description(controller):
    controller.create_task("Buy groceries", description="milk and eggs")
    controller.create_task("Call plumber", description="fix the sink")
    controller.create_task("Email boss")
    assert [t.title for t in controller.search_tasks("milk")] == ["Buy groceries"]
    assert [t.title for t in controller.search_tasks("SINK")] == ["Call plumber"]
    assert len(controller.search_tasks("")) == 3
    assert controller.search_tasks("nonexistent") == []


def test_undo_delete_restores_task_with_id(controller):
    task = controller.create_task("Important", description="keep me")
    assert controller.can_undo() is False
    controller.delete_task(task.id)
    assert controller.list_tasks() == []
    assert controller.can_undo() is True
    assert task.title in controller.undo_label()
    assert controller.undo() is True
    restored = controller.list_tasks()
    assert len(restored) == 1
    assert restored[0].id == task.id
    assert restored[0].title == "Important"
    assert restored[0].description == "keep me"
    assert controller.can_undo() is False


def test_reminders_split_overdue_and_due_today(controller):
    from datetime import date
    today = date.today().isoformat()
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
    controller.create_task("past", deadline=yesterday)
    controller.create_task("today", deadline=today)
    controller.create_task("future", deadline=tomorrow)
    controller.create_task("no-date")
    done = controller.create_task("done-today", deadline=today)
    controller.toggle_completed(done)  # completed tasks never remind
    overdue, due_today = controller.reminders()
    assert [t.title for t in overdue] == ["past"]
    assert [t.title for t in due_today] == ["today"]


def test_is_overdue():
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
    assert Task("past", deadline=yesterday).is_overdue is True
    assert Task("future", deadline=tomorrow).is_overdue is False
    assert Task("done", deadline=yesterday, completed=True).is_overdue is False
    assert Task("no-deadline").is_overdue is False


# ---- completion timestamp (drives the "Completed today" filter) -------------

def test_completed_on_helper():
    stamp = "2026-09-22T10:30:00"
    assert Task("x", completed=True, completed_at=stamp).completed_on("2026-09-22")
    assert not Task("x", completed=True, completed_at=stamp).completed_on("2026-09-21")
    # An open task, or one with no recorded completion date, never matches.
    assert not Task("y", completed=False, completed_at=stamp).completed_on("2026-09-22")
    assert not Task("z", completed=True).completed_on("2026-09-22")


def test_toggle_completed_stamps_and_clears_completed_at(controller):
    task = controller.create_task("Ship it")
    assert task.completed_at is None

    controller.toggle_completed(task, today="2026-09-22")
    assert task.completed is True and task.completed_at == "2026-09-22"
    reloaded = controller.list_tasks()[0]
    assert reloaded.completed is True and reloaded.completed_at == "2026-09-22"
    assert reloaded.completed_on("2026-09-22") is True

    # Reopening clears the stamp, on the object and in the DB.
    controller.toggle_completed(task)
    assert task.completed is False and task.completed_at is None
    assert controller.list_tasks()[0].completed_at is None


def test_toggle_completed_defaults_to_today(controller):
    from datetime import date
    task = controller.create_task("Now")
    controller.toggle_completed(task)  # no explicit day
    assert controller.list_tasks()[0].completed_at == date.today().isoformat()


def test_migration_adds_completed_at_column(tmp_path):
    """Opening a pre-existing DB without the column backfills it as NULL."""
    import sqlite3

    db = tmp_path / "legacy.db"
    con = sqlite3.connect(db)
    con.execute(
        """CREATE TABLE tasks (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               title TEXT NOT NULL,
               description TEXT NOT NULL DEFAULT '',
               priority INTEGER NOT NULL DEFAULT 2,
               sort_order INTEGER NOT NULL DEFAULT 0,
               deadline TEXT,
               completed INTEGER NOT NULL DEFAULT 0,
               category TEXT NOT NULL DEFAULT '',
               created_at TEXT NOT NULL
           )"""
    )
    con.execute(
        "INSERT INTO tasks (title, completed, created_at) VALUES (?, 1, ?)",
        ("old done", "2020-01-01T00:00:00"),
    )
    con.commit()
    con.close()

    repo = TaskRepository(str(db))
    try:
        cols = {r["name"] for r in repo._conn.execute("PRAGMA table_info(tasks)")}
        assert "completed_at" in cols
        tasks = repo.list()
        assert len(tasks) == 1
        assert tasks[0].completed is True
        assert tasks[0].completed_at is None  # historical completion has no date
    finally:
        repo.close()
