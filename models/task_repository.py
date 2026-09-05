"""SQLite persistence layer (data-access object) for tasks.

All SQL lives here; the rest of the app talks to Task objects only.
Uses parameterized queries throughout to avoid SQL injection.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from models.task import Priority, Task

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    priority    INTEGER NOT NULL DEFAULT 2,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    deadline    TEXT,
    completed   INTEGER NOT NULL DEFAULT 0,
    category    TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
);
"""

# Column order used by _row_to_task / SELECT statements.
_COLUMNS = "id, title, description, priority, sort_order, deadline, completed, category, created_at"


class TaskRepository:
    """CRUD access to the tasks table.

    Pass ``":memory:"`` as the path for an ephemeral database (used in tests).
    """

    def __init__(self, db_path: str | Path = "data/tasks.db") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False keeps things simple for a single-user GUI app.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ---- helpers ---------------------------------------------------------
    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            priority=Priority(row["priority"]),
            sort_order=row["sort_order"],
            deadline=row["deadline"],
            completed=bool(row["completed"]),
            category=row["category"],
            created_at=row["created_at"],
        )

    # ---- create ----------------------------------------------------------
    def add(self, task: Task) -> Task:
        cur = self._conn.execute(
            """INSERT INTO tasks
                   (title, description, priority, sort_order, deadline, completed, category, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.title, task.description, int(task.priority), task.sort_order,
             task.deadline, int(task.completed), task.category, task.created_at),
        )
        self._conn.commit()
        task.id = cur.lastrowid
        return task

    # ---- read ------------------------------------------------------------
    def get(self, task_id: int) -> Optional[Task]:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return self._row_to_task(row) if row else None

    def list(self, order_by: str = "sort_order") -> List[Task]:
        """Return all tasks. ``order_by`` is validated against a whitelist."""
        allowed = {
            "sort_order": "sort_order ASC, id ASC",
            "priority": "priority DESC, deadline IS NULL, deadline ASC",
            "deadline": "deadline IS NULL, deadline ASC, priority DESC",
            "created_at": "created_at ASC",
        }
        clause = allowed.get(order_by, allowed["sort_order"])
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM tasks ORDER BY {clause}"
        ).fetchall()
        return [self._row_to_task(r) for r in rows]

    # ---- update ----------------------------------------------------------
    def update(self, task: Task) -> None:
        if task.id is None:
            raise ValueError("Cannot update a task without an id.")
        self._conn.execute(
            """UPDATE tasks SET
                   title = ?, description = ?, priority = ?, sort_order = ?,
                   deadline = ?, completed = ?, category = ?
               WHERE id = ?""",
            (task.title, task.description, int(task.priority), task.sort_order,
             task.deadline, int(task.completed), task.category, task.id),
        )
        self._conn.commit()

    def reorder(self, ordered_ids: List[int]) -> None:
        """Persist a new manual ordering: ``sort_order`` becomes list position."""
        self._conn.executemany(
            "UPDATE tasks SET sort_order = ? WHERE id = ?",
            [(position, task_id) for position, task_id in enumerate(ordered_ids)],
        )
        self._conn.commit()

    def set_completed(self, task_id: int, completed: bool) -> None:
        self._conn.execute(
            "UPDATE tasks SET completed = ? WHERE id = ?",
            (int(completed), task_id),
        )
        self._conn.commit()

    # ---- delete ----------------------------------------------------------
    def delete(self, task_id: int) -> None:
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
