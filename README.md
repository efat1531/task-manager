# Task Manager

A cross-platform desktop task manager built with **PySide6 (Qt)** and **SQLite**,
following an MVC architecture.

## Status

**Phase 1 (MVP) — complete:** create / edit / delete tasks, priority levels,
deadlines with a calendar date picker, mark complete, SQLite persistence, and
sorting by priority / deadline / created date. Overdue open tasks show in red;
completed tasks show struck through.

Planned next:
- **Phase 2:** drag-and-drop reordering (writes back `sort_order`), filtering.
- **Phase 3:** notifications/reminders, categories/tags, search, dark mode, undo.
- **Phase 4:** package per-OS with PyInstaller; CI tests.

## Project layout

```
main.py                      # entry point — wires model → controller → view
models/
  task.py                    # Task dataclass + Priority enum + overdue logic
  task_repository.py         # SQLite CRUD (data-access layer)
controllers/
  task_controller.py         # mediates view <-> repository (no Qt imports)
views/
  main_window.py             # task table + toolbar + sorting
  task_dialog.py             # add/edit dialog with QDateEdit calendar
services/
  notifier.py                # (Phase 3) plyer notification wrapper
data/tasks.db                # SQLite database (gitignored)
tests/test_task_logic.py     # pytest logic-layer tests (in-memory DB)
```

## Setup

Requires Python 3.10+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## Test

```powershell
pytest
```

The logic tests use an in-memory SQLite database and need no display, so they
run headless / in CI.
