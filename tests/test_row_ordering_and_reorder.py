"""Row ordering (tasks + occurrences merged) and drag-reorder id computation.

Regression coverage for two bugs:

* Sorting by priority/deadline left recurring occurrences stranded at the
  bottom instead of interleaving them by the sort key.
* Drag-and-drop reordering was aborted whenever a recurring occurrence was on
  screen, because occurrence rows carry no id.

Pure logic — no Qt widgets, no display.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controllers.task_controller import TaskController  # noqa: E402
from models.schedule import Occurrence  # noqa: E402
from models.task import Priority, Task  # noqa: E402
from views.task_list import TaskTable  # noqa: E402


def _task(title, priority=Priority.MEDIUM, deadline=None, tid=None,
          created_at="2026-01-01T00:00:00", unresolved=0) -> Task:
    return Task(title=title, priority=priority, deadline=deadline, id=tid,
                created_at=created_at, unresolved_comments=unresolved)


def _occ(title, priority=Priority.MEDIUM, date="2026-09-07") -> Occurrence:
    return Occurrence(schedule_id=1, date=date, title=title, description="",
                      priority=priority, category="Meeting", completed=False)


# ---- Bug #2: merged priority ordering ------------------------------------
def test_priority_sort_interleaves_occurrences():
    tasks = [_task("PR-medium", Priority.MEDIUM, tid=1),
             _task("PR-low", Priority.LOW, tid=2)]
    occurrences = [_occ("Meeting-medium", Priority.MEDIUM)]
    ordered = TaskController.order_rows(tasks, occurrences, "priority")
    titles = [r.title for r in ordered]
    # Both Mediums precede the Low — the meeting is no longer stranded last.
    # (Among equal priority, the dated occurrence sorts before the undated PR,
    # matching the repository's "priority DESC, deadline IS NULL, deadline ASC".)
    assert titles == ["Meeting-medium", "PR-medium", "PR-low"], titles
    assert titles.index("PR-low") == 2


def test_priority_sort_full_ordering():
    rows = TaskController.order_rows(
        [_task("t-low", Priority.LOW, tid=1), _task("t-urgent", Priority.URGENT, tid=2)],
        [_occ("o-high", Priority.HIGH), _occ("o-medium", Priority.MEDIUM)],
        "priority",
    )
    assert [r.priority for r in rows] == [
        Priority.URGENT, Priority.HIGH, Priority.MEDIUM, Priority.LOW
    ]


def test_deadline_sort_interleaves_and_nulls_last():
    rows = TaskController.order_rows(
        [_task("t-none", deadline=None, tid=1),
         _task("t-later", deadline="2026-09-10", tid=2)],
        [_occ("o-day", date="2026-09-07")],
        "deadline",
    )
    assert [r.title for r in rows] == ["o-day", "t-later", "t-none"]


def test_unresolved_task_stays_pinned_when_merged():
    rows = TaskController.order_rows(
        [_task("normal", Priority.URGENT, tid=1),
         _task("pinned", Priority.LOW, tid=2, unresolved=3)],
        [_occ("occ", Priority.URGENT)],
        "priority",
    )
    assert rows[0].title == "pinned"


def test_manual_order_keeps_tasks_then_occurrences():
    tasks = [_task("a", tid=1), _task("b", tid=2)]
    occurrences = [_occ("meeting", Priority.URGENT)]
    ordered = TaskController.order_rows(tasks, occurrences, "sort_order")
    assert [r.title for r in ordered] == ["a", "b", "meeting"]


# ---- Bug #1: reorder ignores occurrence rows -----------------------------
def test_reorder_works_with_occurrence_present():
    # rows: task(10), task(20), occurrence(None). Move row 0 to the end of tasks.
    row_ids = [10, 20, None]
    new_order = TaskTable._reordered_ids(row_ids, {0}, drop_row=2)
    assert new_order == [20, 10]


def test_reorder_ignores_selected_occurrence_rows():
    row_ids = [10, 20, None]
    # Selecting only the occurrence row is a no-op, not a crash.
    assert TaskTable._reordered_ids(row_ids, {2}, drop_row=0) is None


def test_reorder_move_to_top():
    row_ids = [10, 20, 30, None]
    assert TaskTable._reordered_ids(row_ids, {2}, drop_row=0) == [30, 10, 20]


def test_reorder_noop_returns_none():
    row_ids = [10, 20, None]
    assert TaskTable._reordered_ids(row_ids, {0}, drop_row=0) is None


def test_reorder_drop_past_end_appends():
    row_ids = [10, 20, 30]
    assert TaskTable._reordered_ids(row_ids, {0}, drop_row=3) == [20, 30, 10]


def test_reorder_multi_select_block_moves_together():
    row_ids = [10, 20, 30, 40]
    # Move rows 0 and 1 to just before row 3.
    assert TaskTable._reordered_ids(row_ids, {0, 1}, drop_row=3) == [30, 10, 20, 40]
