"""Controller — mediates between the views and the repository/model.

Holds no Qt imports so its logic stays unit-testable without a display.
"""
from __future__ import annotations

from typing import List, Optional

from models.task import Priority, Task
from models.task_repository import TaskRepository


class TaskController:
    def __init__(self, repository: TaskRepository) -> None:
        self._repo = repository

    def list_tasks(self, order_by: str = "sort_order") -> List[Task]:
        return self._repo.list(order_by=order_by)

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
        self._repo.delete(task_id)

    def reorder_tasks(self, ordered_ids: List[int]) -> None:
        """Persist a new manual ordering given task ids in the desired order."""
        self._repo.reorder(ordered_ids)
