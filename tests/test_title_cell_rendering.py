"""Title-cell rendering: a linked title must not overlap a stale plain item.

Regression for the "colliding titles" bug: rows are reused across refresh(), and
a task with a URL renders its title as a transparent QLabel cell widget while a
task without a URL renders a plain QTableWidgetItem. When a row index switched
from a non-link task to a link task, the old item was left under the transparent
widget, so two titles were painted on top of each other. _populate_row must clear
both the leftover widget and the leftover item when repopulating column 1.

Needs a QApplication; runs headless under QT_QPA_PLATFORM=offscreen (as CI does).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - PySide6 missing
    pytest.skip("PySide6 not available", allow_module_level=True)

from controllers.task_controller import TaskController  # noqa: E402
from models.task import Priority, Task  # noqa: E402
from models.task_repository import TaskRepository  # noqa: E402

try:
    from views.main_window import MainWindow  # noqa: E402
    from views import update_dialog  # noqa: E402
except Exception as exc:  # pragma: no cover - no display/platform plugin
    pytest.skip(f"Qt widgets unavailable: {exc}", allow_module_level=True)


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    yield existing or QApplication([])


@pytest.fixture
def window(app, monkeypatch):
    # Neutralise the startup auto-updater: check_silent() spawns a background
    # thread that hits GitHub, and maybe_show_whats_new() can pop a modal dialog
    # — either would hang this headless widget test.
    monkeypatch.setattr(update_dialog.UpdateManager, "check_silent", lambda self: None)
    monkeypatch.setattr(update_dialog.UpdateManager, "maybe_show_whats_new", lambda self: None)
    db_path = os.path.join(tempfile.mkdtemp(), "tasks.db")
    win = MainWindow(TaskController(TaskRepository(db_path)))
    yield win
    win._updates.shutdown()


def _plain(tid=1):
    return Task(title="Plain task without a link", priority=Priority.MEDIUM, id=tid)


def _linked(tid=2):
    return Task(
        title="Your PR #59978: linked task",
        description="Link: https://dev.azure.com/o/_git/repo/pullrequest/59978",
        priority=Priority.HIGH,
        id=tid,
    )


def test_linked_title_clears_stale_item(window):
    table = window._table
    table.setRowCount(1)

    # First a plain task: a real item, no cell widget.
    window._populate_row(0, _plain())
    assert table.item(0, 1) is not None
    assert table.cellWidget(0, 1) is None

    # Then a linked task on the SAME row: a widget, and NO item left underneath
    # it (the bug left the plain item there, causing overlapping titles).
    window._populate_row(0, _linked())
    assert table.cellWidget(0, 1) is not None
    assert table.item(0, 1) is None


def test_plain_title_after_linked_clears_widget(window):
    table = window._table
    table.setRowCount(1)

    window._populate_row(0, _linked())
    assert table.cellWidget(0, 1) is not None

    # Reverse transition: back to a plain task leaves an item and no widget.
    window._populate_row(0, _plain())
    assert table.cellWidget(0, 1) is None
    assert table.item(0, 1) is not None
