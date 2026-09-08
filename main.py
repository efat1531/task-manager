"""Application entry point.

Wires the data layer (SQLite repository) to the controller and the UI,
following the MVC layering described in the design document.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from controllers.task_controller import TaskController
from models.task_repository import TaskRepository
from version import APP_VERSION
from views.main_window import MainWindow


def _resource_dir() -> Path:
    """Directory holding bundled read-only resources (assets).

    When frozen by PyInstaller, data files are unpacked under ``sys._MEIPASS``;
    otherwise they sit next to this script.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return Path(__file__).parent


def _data_dir() -> Path:
    """Writable directory for the database.

    A frozen one-file exe is extracted to a temporary folder that is wiped on
    exit, so the database must live in a persistent per-user location instead.
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        directory = Path(base) / "TaskManager"
    else:
        directory = Path(__file__).parent / "data"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


BASE_DIR = _resource_dir()
DB_PATH = _data_dir() / "tasks.db"
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


def _load_fonts() -> None:
    """Register the bundled Barlow family so the UI matches the design.

    Missing files degrade gracefully — the stylesheet's fallback stack (Segoe UI
    etc.) applies. When Barlow loads, it becomes the app-wide default font.
    """
    fonts_dir = BASE_DIR / "assets" / "fonts"
    loaded = False
    for ttf in sorted(fonts_dir.glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(ttf)) != -1:
            loaded = True
    if loaded and "Barlow" in QFontDatabase.families():
        font = QFont("Barlow")
        font.setPointSize(10)
        QApplication.instance().setFont(font)


def main() -> int:
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Task Manager")
    app.setApplicationVersion(APP_VERSION)
    _load_fonts()
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
