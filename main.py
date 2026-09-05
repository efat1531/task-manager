"""Application entry point.

Wires the data layer (SQLite repository) to the controller and the UI,
following the MVC layering described in the design document.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from controllers.task_controller import TaskController
from models.task_repository import TaskRepository
from views.main_window import MainWindow

DB_PATH = Path(__file__).parent / "data" / "tasks.db"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Task Manager")

    repository = TaskRepository(DB_PATH)
    controller = TaskController(repository)

    window = MainWindow(controller)
    window.show()

    exit_code = app.exec()
    repository.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
