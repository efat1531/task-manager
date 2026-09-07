"""Controller — mediates between the views and the repository/model.

Holds no Qt imports so its logic stays unit-testable without a display.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, List, Optional, Set, Tuple

from models.integration import AzureConfig, PullRequest, pr_key, pr_to_task_fields
from models.schedule import Frequency, Occurrence, Schedule, occurs_on
from models.task import Priority, Task
from models.task_repository import TaskRepository


class TaskController:
    def __init__(self, repository: TaskRepository) -> None:
        self._repo = repository
        # Each entry: (human label, callable that reverses the action).
        self._undo_stack: List[Tuple[str, Callable[[], None]]] = []

    def list_tasks(self, order_by: str = "sort_order") -> List[Task]:
        return self._repo.list(order_by=order_by)

    @staticmethod
    def order_rows(tasks: List[Task], occurrences: List[Occurrence], order_by: str):
        """Merge one-off tasks and recurring occurrences into a single ordering.

        Under manual ordering (``sort_order``) occurrences have no place in the
        drag-reorderable sequence, so they simply follow the tasks (in the order
        the caller supplied). For every other sort the two kinds are interleaved
        by the chosen key so, e.g., a Medium occurrence sits above a Low task
        instead of being stranded at the bottom. Tasks with unresolved PR
        comments stay pinned to the very top, matching the repository's sort.
        """
        rows = list(tasks) + list(occurrences)
        if order_by == "sort_order":
            return rows

        def pinned(item) -> int:
            # 0 sorts before 1, so pinned (unresolved) rows come first.
            return 0 if (getattr(item, "unresolved_comments", 0) or 0) > 0 else 1

        def priority_key(item) -> int:
            return -int(item.priority)  # higher priority first

        def optional_asc(value):
            # Missing/empty values sort last, present ones ascending.
            return (1, "") if not value else (0, value)

        def title_key(item) -> str:
            return item.title.lower()

        if order_by == "priority":
            key = lambda i: (pinned(i), priority_key(i),
                             optional_asc(getattr(i, "deadline", None)), title_key(i))
        elif order_by == "deadline":
            key = lambda i: (pinned(i), optional_asc(getattr(i, "deadline", None)),
                             priority_key(i), title_key(i))
        elif order_by == "created_at":
            key = lambda i: (pinned(i), optional_asc(getattr(i, "created_at", None)),
                             title_key(i))
        else:
            return rows
        return sorted(rows, key=key)

    def search_tasks(self, query: str, order_by: str = "sort_order") -> List[Task]:
        """Case-insensitive substring match over title and description."""
        query = query.strip().lower()
        tasks = self._repo.list(order_by=order_by)
        if not query:
            return tasks
        return [
            t for t in tasks
            if query in t.title.lower() or query in t.description.lower()
        ]

    def reminders(self) -> Tuple[List[Task], List[Task]]:
        """Return (overdue, due-today) incomplete tasks for reminder prompts."""
        tasks = self._repo.list()
        overdue = [t for t in tasks if t.is_overdue]
        due_today = [t for t in tasks if t.is_due_today]
        return overdue, due_today

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        deadline: Optional[str] = None,
        category: str = "",
    ) -> Task:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty.")
        # New tasks go to the end of the manual ordering.
        next_order = len(self._repo.list())
        task = Task(
            title=title,
            description=description.strip(),
            priority=priority,
            deadline=deadline,
            category=category.strip(),
            sort_order=next_order,
        )
        return self._repo.add(task)

    def update_task(self, task: Task) -> Task:
        if not task.title.strip():
            raise ValueError("Task title cannot be empty.")
        task.title = task.title.strip()
        self._repo.update(task)
        return task

    def toggle_completed(self, task: Task) -> Task:
        task.completed = not task.completed
        self._repo.set_completed(task.id, task.completed)
        return task

    def delete_task(self, task_id: int) -> None:
        task = self._repo.get(task_id)
        self._repo.delete(task_id)
        if task is not None:
            self._undo_stack.append(
                (f"delete “{task.title}”", lambda t=task: self._repo.restore(t))
            )

    def reorder_tasks(self, ordered_ids: List[int]) -> None:
        """Persist a new manual ordering given task ids in the desired order."""
        self._repo.reorder(ordered_ids)

    # ---- schedules -------------------------------------------------------
    def create_schedule(
        self,
        title: str,
        start_date: str,
        end_date: str,
        freq: Frequency = Frequency.DAILY,
        weekdays: Optional[Set[int]] = None,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        category: str = "",
    ) -> Schedule:
        title = title.strip()
        if not title:
            raise ValueError("Schedule title cannot be empty.")
        if end_date < start_date:
            raise ValueError("End date cannot be before start date.")
        schedule = Schedule(
            title=title,
            start_date=start_date,
            end_date=end_date,
            freq=freq,
            weekdays=set(weekdays or set()),
            description=description.strip(),
            priority=priority,
            category=category.strip(),
            sort_order=len(self._repo.list_schedules()),
        )
        return self._repo.add_schedule(schedule)

    def update_schedule(self, schedule: Schedule) -> Schedule:
        if not schedule.title.strip():
            raise ValueError("Schedule title cannot be empty.")
        if schedule.end_date < schedule.start_date:
            raise ValueError("End date cannot be before start date.")
        schedule.title = schedule.title.strip()
        self._repo.update_schedule(schedule)
        return schedule

    def delete_schedule(self, schedule_id: int) -> None:
        self._repo.delete_schedule(schedule_id)

    def get_schedule(self, schedule_id: int) -> Optional[Schedule]:
        return self._repo.get_schedule(schedule_id)

    def list_schedules(self) -> List[Schedule]:
        return self._repo.list_schedules()

    def occurrences_on(self, iso_date: str) -> List[Occurrence]:
        """Every non-cancelled occurrence that falls on the given date."""
        day = datetime.fromisoformat(iso_date).date()
        result: List[Occurrence] = []
        for schedule in self._repo.list_schedules():
            if not occurs_on(schedule, day):
                continue
            status = self._repo.get_override(schedule.id, iso_date)
            if status == "cancelled":
                continue
            result.append(
                Occurrence(
                    schedule_id=schedule.id,
                    date=iso_date,
                    title=schedule.title,
                    description=schedule.description,
                    priority=schedule.priority,
                    category=schedule.category,
                    completed=(status == "completed"),
                )
            )
        return result

    def toggle_occurrence(self, schedule_id: int, iso_date: str) -> None:
        """Complete/uncomplete a single day only; other days are untouched."""
        if self._repo.get_override(schedule_id, iso_date) == "completed":
            self._repo.clear_override(schedule_id, iso_date)
        else:
            self._repo.set_override(schedule_id, iso_date, "completed")

    def cancel_occurrence_day(self, schedule_id: int, iso_date: str) -> None:
        self._repo.set_override(schedule_id, iso_date, "cancelled")
        self._undo_stack.append(
            (
                "cancel this day",
                lambda sid=schedule_id, d=iso_date: self._repo.clear_override(sid, d),
            )
        )

    def cancel_schedule_from(self, schedule_id: int, iso_date: str) -> None:
        """Hide occurrences on/after ``iso_date``; past days and completions stay."""
        schedule = self._repo.get_schedule(schedule_id)
        previous = schedule.cancelled_from if schedule else None
        self._repo.set_cancelled_from(schedule_id, iso_date)
        self._undo_stack.append(
            (
                "cancel schedule",
                lambda sid=schedule_id, p=previous: self._repo.set_cancelled_from(sid, p),
            )
        )

    # ---- Azure pull-request sync ----------------------------------------
    def sync_pull_requests(
        self,
        prs: List[PullRequest],
        organization: str,
        source: str = "review",
        config: Optional[AzureConfig] = None,
    ) -> dict:
        """Reconcile the fetched PRs for one ``source`` against existing links.

        The network fetch happens in the caller (a background worker); this method
        is pure DB logic so the dedup + auto-complete behaviour stays testable.

        - A PR with no existing link becomes a new task (and is linked).
        - A PR that already has a link is skipped — never duplicated, even if its
          task was since edited or deleted.
        - A previously-linked PR that is *absent* from ``prs`` (merged, abandoned,
          or the user was dropped) has its task completed.

        Reconciliation is scoped to ``source`` ("review" | "author"): only links
        belonging to that source are considered, so syncing one source never
        auto-completes the other's tasks.
        """
        prefix = f"{source}:"
        existing = {
            key: task_id
            for key, task_id in self._repo.list_pr_links().items()
            if key.startswith(prefix)
        }
        current_keys = set()
        created = skipped = completed = 0

        for pr in prs:
            key = pr_key(organization, pr.pr_id, source)
            current_keys.add(key)
            if key in existing:
                task_id = existing[key]
                skipped += 1
            else:
                fields = pr_to_task_fields(pr, config)
                task = self.create_task(**fields)
                self._repo.link_pr(key, task.id)
                task_id = task.id
                created += 1
            # Refresh the unresolved-comment flag for authored PRs every sync so
            # the task is pinned as Urgent while comments are open and drops back
            # once they are resolved. (A no-op if the task was since deleted.)
            if pr.is_author:
                self._repo.set_unresolved_comments(
                    task_id, pr.unresolved_comment_count
                )

        # Auto-complete tasks for PRs of this source that are no longer open.
        for key, task_id in existing.items():
            if key in current_keys:
                continue
            task = self._repo.get(task_id)
            if task is not None and not task.completed:
                self._repo.set_completed(task_id, True)
                completed += 1

        return {"created": created, "skipped": skipped, "completed": completed}

    def clear_pr_links(self) -> None:
        """Forget which PRs have been synced. Tasks already created are kept, but
        an open PR may produce a fresh task on a future sync."""
        self._repo.clear_pr_links()

    # ---- export ----------------------------------------------------------
    def tasks_for_day(self, iso_date: str) -> List[dict]:
        """Serializable records for everything scheduled on ``iso_date``:
        one-off tasks whose deadline is that date, plus every recurring
        occurrence that falls on it. Enums are coerced to plain strings."""
        records: List[dict] = []
        for task in self._repo.list():
            if task.deadline == iso_date:
                records.append({
                    "type": "task",
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "priority": task.priority.label,
                    "deadline": task.deadline,
                    "category": task.category,
                    "completed": task.completed,
                    "created_at": task.created_at,
                })
        for occ in self.occurrences_on(iso_date):
            records.append({
                "type": "occurrence",
                "schedule_id": occ.schedule_id,
                "title": occ.title,
                "description": occ.description,
                "priority": occ.priority.label,
                "date": occ.date,
                "category": occ.category,
                "completed": occ.completed,
            })
        return records

    def export_day_json(self, iso_date: str) -> str:
        """Pretty-printed JSON of :meth:`tasks_for_day`, ready for the clipboard."""
        payload = {"date": iso_date, "tasks": self.tasks_for_day(iso_date)}
        return json.dumps(payload, indent=2, ensure_ascii=False)

    # ---- undo ------------------------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def undo_label(self) -> str:
        return self._undo_stack[-1][0] if self._undo_stack else ""

    def undo(self) -> bool:
        """Reverse the most recent undoable action. Returns True if one ran."""
        if not self._undo_stack:
            return False
        _, reverse = self._undo_stack.pop()
        reverse()
        return True
