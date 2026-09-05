"""Controller — mediates between the views and the repository/model.

Holds no Qt imports so its logic stays unit-testable without a display.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from models.task import Priority, Task
from models.task_repository import TaskRepository


class TaskController:
    def __init__(self, repository: TaskRepository) -> None:
        self._repo = repository
        # Each entry: (human label, callable that reverses the action).
        self._undo_stack: List[Tuple[str, Callable[[], None]]] = []

    def list_tasks(self, order_by: str = "sort_order") -> List[Task]:
        return self._repo.list(order_by=order_by)

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
