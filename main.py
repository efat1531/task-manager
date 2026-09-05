"""Application entry point.

Wires the data layer (SQLite repository) to the controller and the UI,
following the MVC layering described in the design document.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from controllers.task_controller import TaskController
from models.task_repository import TaskRepository
from views.main_window import MainWindow

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "tasks.db"
ICON_PATH = BASE_DIR / "assets" / "icon.png"


def _set_windows_app_id() -> None:
    """Make Windows treat us as our own app so the taskbar shows our icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "TaskManager.Desktop.1"
        )
    except Exception:  # pragma: no cover - best-effort cosmetic tweak
        pass


def main() -> int:
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Task Manager")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    repository = TaskRepository(DB_PATH)
    controller = TaskController(repository)

    window = MainWindow(controller)
    window.show()

    exit_code = app.exec()
    repository.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
