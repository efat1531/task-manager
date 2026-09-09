"""SQLite persistence layer (data-access object) for tasks.

All SQL lives here; the rest of the app talks to Task objects only.
Uses parameterized queries throughout to avoid SQL injection.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from models.notification import Notification
from models.schedule import Frequency, Schedule
from models.task import Priority, Task

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT    NOT NULL,
    description         TEXT    NOT NULL DEFAULT '',
    priority            INTEGER NOT NULL DEFAULT 2,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    deadline            TEXT,
    completed           INTEGER NOT NULL DEFAULT 0,
    category            TEXT    NOT NULL DEFAULT '',
    created_at          TEXT    NOT NULL,
    unresolved_comments INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS schedules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT    NOT NULL,
    description    TEXT    NOT NULL DEFAULT '',
    priority       INTEGER NOT NULL DEFAULT 2,
    category       TEXT    NOT NULL DEFAULT '',
    start_date     TEXT    NOT NULL,
    end_date       TEXT    NOT NULL,
    freq           TEXT    NOT NULL DEFAULT 'daily',
    weekdays       TEXT    NOT NULL DEFAULT '',
    cancelled_from TEXT,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS schedule_overrides (
    schedule_id INTEGER NOT NULL,
    date        TEXT    NOT NULL,
    status      TEXT    NOT NULL,          -- 'completed' | 'cancelled'
    PRIMARY KEY (schedule_id, date),
    FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pr_links (
    pr_key     TEXT    PRIMARY KEY,        -- "{org}:{pullRequestId}"
    task_id    INTEGER NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL,           -- icon bucket: 'pr'|'linear'|'reminder'|'sync'
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,           -- ISO datetime
    read       INTEGER NOT NULL DEFAULT 0,
    dedup_key  TEXT                        -- stable key; NULL = never de-duped
);

-- Partial unique index: the de-dup engine. NULL dedup_keys never collide, so an
-- ``INSERT OR IGNORE`` only skips a genuine repeat of the same keyed event.
CREATE UNIQUE INDEX IF NOT EXISTS ux_notifications_dedup
    ON notifications(dedup_key) WHERE dedup_key IS NOT NULL;
"""

# Column order used by _row_to_task / SELECT statements.
_COLUMNS = (
    "id, title, description, priority, sort_order, deadline, completed, "
    "category, created_at, unresolved_comments"
)

# Column order for schedule SELECTs / _row_to_schedule.
_SCHED_COLUMNS = (
    "id, title, description, priority, category, start_date, end_date, "
    "freq, weekdays, cancelled_from, sort_order, created_at"
)


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
        self._migrate()
        self._conn.commit()

    # ---- schema migration ------------------------------------------------
    def _migrate(self) -> None:
        """Bring an older database up to the current schema.

        ``CREATE TABLE IF NOT EXISTS`` never adds columns to a table that already
        exists, so new columns are added here with ``ALTER TABLE`` when missing.
        """
        cols = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "unresolved_comments" not in cols:
            self._conn.execute(
                "ALTER TABLE tasks ADD COLUMN "
                "unresolved_comments INTEGER NOT NULL DEFAULT 0"
            )

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
            unresolved_comments=row["unresolved_comments"],
        )

    # ---- create ----------------------------------------------------------
    def add(self, task: Task) -> Task:
        cur = self._conn.execute(
            """INSERT INTO tasks
                   (title, description, priority, sort_order, deadline, completed,
                    category, created_at, unresolved_comments)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.title, task.description, int(task.priority), task.sort_order,
             task.deadline, int(task.completed), task.category, task.created_at,
             int(task.unresolved_comments)),
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
        # Tasks with unresolved PR comments (authored PRs) are pinned to the very
        # top regardless of the chosen sort — a SQLite boolean sorts 1 before 0.
        clause = f"(unresolved_comments > 0) DESC, {clause}"
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
                   deadline = ?, completed = ?, category = ?,
                   unresolved_comments = ?
               WHERE id = ?""",
            (task.title, task.description, int(task.priority), task.sort_order,
             task.deadline, int(task.completed), task.category,
             int(task.unresolved_comments), task.id),
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

    def set_unresolved_comments(self, task_id: int, count: int) -> None:
        """Record how many unresolved PR comment threads a task's PR has."""
        self._conn.execute(
            "UPDATE tasks SET unresolved_comments = ? WHERE id = ?",
            (int(count), task_id),
        )
        self._conn.commit()

    def restore(self, task: Task) -> None:
        """Re-insert a previously deleted task, preserving its original id."""
        if task.id is None:
            raise ValueError("Cannot restore a task without an id.")
        self._conn.execute(
            f"""INSERT INTO tasks ({_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.title, task.description, int(task.priority),
             task.sort_order, task.deadline, int(task.completed),
             task.category, task.created_at, int(task.unresolved_comments)),
        )
        self._conn.commit()

    # ---- delete ----------------------------------------------------------
    def delete(self, task_id: int) -> None:
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()

    # ---- schedules -------------------------------------------------------
    @staticmethod
    def _weekdays_to_csv(weekdays) -> str:
        return ",".join(str(d) for d in sorted(weekdays))

    @staticmethod
    def _csv_to_weekdays(csv: str) -> set:
        return {int(p) for p in csv.split(",") if p.strip() != ""}

    def _row_to_schedule(self, row: sqlite3.Row) -> Schedule:
        return Schedule(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            priority=Priority(row["priority"]),
            category=row["category"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            freq=Frequency(row["freq"]),
            weekdays=self._csv_to_weekdays(row["weekdays"]),
            cancelled_from=row["cancelled_from"],
            sort_order=row["sort_order"],
            created_at=row["created_at"],
        )

    def add_schedule(self, schedule: Schedule) -> Schedule:
        cur = self._conn.execute(
            """INSERT INTO schedules
                   (title, description, priority, category, start_date, end_date,
                    freq, weekdays, cancelled_from, sort_order, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (schedule.title, schedule.description, int(schedule.priority),
             schedule.category, schedule.start_date, schedule.end_date,
             schedule.freq.value, self._weekdays_to_csv(schedule.weekdays),
             schedule.cancelled_from, schedule.sort_order, schedule.created_at),
        )
        self._conn.commit()
        schedule.id = cur.lastrowid
        return schedule

    def get_schedule(self, schedule_id: int) -> Optional[Schedule]:
        row = self._conn.execute(
            f"SELECT {_SCHED_COLUMNS} FROM schedules WHERE id = ?", (schedule_id,)
        ).fetchone()
        return self._row_to_schedule(row) if row else None

    def list_schedules(self) -> List[Schedule]:
        rows = self._conn.execute(
            f"SELECT {_SCHED_COLUMNS} FROM schedules ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        return [self._row_to_schedule(r) for r in rows]

    def update_schedule(self, schedule: Schedule) -> None:
        if schedule.id is None:
            raise ValueError("Cannot update a schedule without an id.")
        self._conn.execute(
            """UPDATE schedules SET
                   title = ?, description = ?, priority = ?, category = ?,
                   start_date = ?, end_date = ?, freq = ?, weekdays = ?,
                   cancelled_from = ?, sort_order = ?
               WHERE id = ?""",
            (schedule.title, schedule.description, int(schedule.priority),
             schedule.category, schedule.start_date, schedule.end_date,
             schedule.freq.value, self._weekdays_to_csv(schedule.weekdays),
             schedule.cancelled_from, schedule.sort_order, schedule.id),
        )
        self._conn.commit()

    def delete_schedule(self, schedule_id: int) -> None:
        # ON DELETE CASCADE removes the overrides too.
        self._conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        self._conn.commit()

    def set_cancelled_from(self, schedule_id: int, iso_date: Optional[str]) -> None:
        self._conn.execute(
            "UPDATE schedules SET cancelled_from = ? WHERE id = ?",
            (iso_date, schedule_id),
        )
        self._conn.commit()

    # ---- schedule per-day overrides -------------------------------------
    def set_override(self, schedule_id: int, date: str, status: str) -> None:
        self._conn.execute(
            """INSERT INTO schedule_overrides (schedule_id, date, status)
               VALUES (?, ?, ?)
               ON CONFLICT(schedule_id, date) DO UPDATE SET status = excluded.status""",
            (schedule_id, date, status),
        )
        self._conn.commit()

    def clear_override(self, schedule_id: int, date: str) -> None:
        self._conn.execute(
            "DELETE FROM schedule_overrides WHERE schedule_id = ? AND date = ?",
            (schedule_id, date),
        )
        self._conn.commit()

    def get_override(self, schedule_id: int, date: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT status FROM schedule_overrides WHERE schedule_id = ? AND date = ?",
            (schedule_id, date),
        ).fetchone()
        return row["status"] if row else None

    def list_overrides(self, schedule_id: int) -> Dict[str, str]:
        rows = self._conn.execute(
            "SELECT date, status FROM schedule_overrides WHERE schedule_id = ?",
            (schedule_id,),
        ).fetchall()
        return {r["date"]: r["status"] for r in rows}

    # ---- pull-request links (Azure integration) -------------------------
    def link_pr(self, pr_key: str, task_id: int) -> None:
        """Record that ``pr_key`` produced ``task_id``. Kept even if the task is
        later deleted, so the PR is never turned into a task a second time."""
        from datetime import datetime

        self._conn.execute(
            """INSERT INTO pr_links (pr_key, task_id, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT(pr_key) DO UPDATE SET task_id = excluded.task_id""",
            (pr_key, task_id, datetime.now().isoformat(timespec="seconds")),
        )
        self._conn.commit()

    def get_pr_link(self, pr_key: str) -> Optional[int]:
        row = self._conn.execute(
            "SELECT task_id FROM pr_links WHERE pr_key = ?", (pr_key,)
        ).fetchone()
        return row["task_id"] if row else None

    def list_pr_links(self) -> Dict[str, int]:
        rows = self._conn.execute("SELECT pr_key, task_id FROM pr_links").fetchall()
        return {r["pr_key"]: r["task_id"] for r in rows}

    def delete_pr_link(self, pr_key: str) -> None:
        self._conn.execute("DELETE FROM pr_links WHERE pr_key = ?", (pr_key,))
        self._conn.commit()

    def clear_pr_links(self, prefix: Optional[str] = None) -> None:
        """Forget stored external->task links (used when removing an integration).

        With no ``prefix`` every link is removed (the original behaviour). With a
        ``prefix`` (e.g. ``"linear:"``) only keys starting with it are removed, so
        removing one integration leaves the other's links intact.
        """
        if prefix:
            self._conn.execute(
                "DELETE FROM pr_links WHERE pr_key LIKE ? || '%'", (prefix,)
            )
        else:
            self._conn.execute("DELETE FROM pr_links")
        self._conn.commit()

    # ---- reset -----------------------------------------------------------
    # ---- notifications ---------------------------------------------------
    @staticmethod
    def _row_to_notification(row: sqlite3.Row) -> Notification:
        return Notification(
            id=row["id"],
            kind=row["kind"],
            title=row["title"],
            body=row["body"],
            created_at=row["created_at"],
            read=bool(row["read"]),
            dedup_key=row["dedup_key"],
        )

    def add_notification(self, notification: Notification) -> Optional[Notification]:
        """Insert a feed entry. Returns it (with id) or None if its ``dedup_key``
        already existed — repeat keyed events are silently skipped."""
        cur = self._conn.execute(
            """INSERT OR IGNORE INTO notifications
                   (kind, title, body, created_at, read, dedup_key)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (notification.kind, notification.title, notification.body,
             notification.created_at, int(notification.read),
             notification.dedup_key),
        )
        self._conn.commit()
        if cur.rowcount == 0:  # dedup_key collided → nothing inserted
            return None
        notification.id = cur.lastrowid
        return notification

    def list_notifications(self, limit: int = 50) -> List[Notification]:
        """Return the most recent notifications, newest first."""
        rows = self._conn.execute(
            "SELECT id, kind, title, body, created_at, read, dedup_key "
            "FROM notifications ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_notification(r) for r in rows]

    def count_unread_notifications(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE read = 0"
        ).fetchone()
        return int(row["n"]) if row else 0

    def mark_all_notifications_read(self) -> None:
        self._conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
        self._conn.commit()

    def prune_notifications(self, keep: int = 200) -> None:
        """Cap the feed at ``keep`` most-recent rows so it can't grow unbounded."""
        self._conn.execute(
            """DELETE FROM notifications WHERE id NOT IN (
                   SELECT id FROM notifications ORDER BY id DESC LIMIT ?
               )""",
            (keep,),
        )
        self._conn.commit()

    def reset(self) -> None:
        """Delete every row from every table, emptying the database.

        Clears tasks, schedules, their per-day overrides, all external
        (Azure/Linear) PR links, and the notification feed, then resets the
        AUTOINCREMENT counters so ids start over from 1. The schema itself is
        left in place.
        """
        with self._conn:  # commits on success, rolls back on error
            self._conn.execute("DELETE FROM schedule_overrides")
            self._conn.execute("DELETE FROM pr_links")
            self._conn.execute("DELETE FROM notifications")
            self._conn.execute("DELETE FROM schedules")
            self._conn.execute("DELETE FROM tasks")
            # sqlite_sequence only exists once an AUTOINCREMENT table has grown;
            # ignore its absence on a brand-new database.
            try:
                self._conn.execute("DELETE FROM sqlite_sequence")
            except sqlite3.OperationalError:
                pass

    def close(self) -> None:
        self._conn.close()
