"""Link detection, urgent-pin sorting, and the tasks-table migration.

Pure logic + in-memory / on-disk SQLite; no Qt or network, so these run headless.
Run with:  pytest
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import linkify  # noqa: E402
from models.task import Priority, Task  # noqa: E402
from models.task_repository import TaskRepository  # noqa: E402


# ---- linkify helpers -----------------------------------------------------
def test_first_url_prefers_title_then_description():
    assert linkify.first_url("see https://a.example/x", "https://b.example/y") \
        == "https://a.example/x"
    assert linkify.first_url("no link here", "go https://b.example/y") \
        == "https://b.example/y"


def test_first_url_none_when_absent():
    assert linkify.first_url("plain text", "still nothing") is None
    assert linkify.first_url("", None or "") is None


def test_first_url_strips_trailing_punctuation():
    assert linkify.first_url("open https://a.example/pr/1.") == "https://a.example/pr/1"


def test_pr_number_detection():
    assert linkify.pr_number("Your PR #123: Fix bug") == "#123"
    assert linkify.pr_number("Review PR #7") == "#7"
    assert linkify.pr_number("No number here") is None
    assert linkify.pr_number("") is None


# ---- urgent-pin sorting --------------------------------------------------
@pytest.fixture()
def repo() -> TaskRepository:
    r = TaskRepository(":memory:")
    yield r
    r.close()


def _add(repo, title, priority=Priority.MEDIUM, unresolved=0):
    task = repo.add(Task(title=title, priority=priority, unresolved_comments=unresolved))
    return task


@pytest.mark.parametrize("order_by", ["sort_order", "priority", "deadline", "created_at"])
def test_unresolved_task_is_pinned_first_in_every_sort(repo, order_by):
    _add(repo, "low-normal", priority=Priority.LOW)
    _add(repo, "urgent-normal", priority=Priority.URGENT)
    _add(repo, "pinned", priority=Priority.LOW, unresolved=2)
    titles = [t.title for t in repo.list(order_by=order_by)]
    assert titles[0] == "pinned", f"{order_by}: {titles}"


def test_set_unresolved_comments_pins_and_clears(repo):
    a = _add(repo, "a", priority=Priority.HIGH)
    b = _add(repo, "b", priority=Priority.LOW)
    # Flag b -> it floats above the higher-priority a.
    repo.set_unresolved_comments(b.id, 3)
    assert [t.title for t in repo.list(order_by="priority")][0] == "b"
    # Resolve -> it drops back below a.
    repo.set_unresolved_comments(b.id, 0)
    assert [t.title for t in repo.list(order_by="priority")] == ["a", "b"]


def test_unresolved_comments_round_trips(repo):
    task = _add(repo, "pr", unresolved=5)
    assert repo.get(task.id).unresolved_comments == 5


# ---- migration of a pre-existing database --------------------------------
def test_migration_adds_column_to_legacy_db(tmp_path):
    db = tmp_path / "legacy.db"
    # Simulate an old database created before the unresolved_comments column.
    conn = sqlite3.connect(db)
    conn.execute(
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
    conn.execute(
        "INSERT INTO tasks (title, created_at) VALUES ('old task', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    # Opening through the repository should migrate it and read cleanly.
    repo = TaskRepository(db)
    try:
        cols = {
            row["name"]
            for row in repo._conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        assert "unresolved_comments" in cols
        tasks = repo.list()
        assert len(tasks) == 1
        assert tasks[0].title == "old task"
        assert tasks[0].unresolved_comments == 0
    finally:
        repo.close()
