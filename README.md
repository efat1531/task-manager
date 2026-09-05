# Task Manager

A cross-platform desktop task manager built with **PySide6 (Qt)** and **SQLite**,
following an MVC architecture.

## Status

**Phase 1 (MVP) — complete:** create / edit / delete tasks, priority levels,
deadlines with a calendar date picker, mark complete, SQLite persistence, and
sorting by priority / deadline / created date. Overdue open tasks show in red;
completed tasks show struck through.

**Phase 2 — complete:** drag-and-drop row reordering that persists to
`sort_order` (enabled only under "Manual order" sort), plus filtering by
status (all / open / completed) and by category.

**Phase 3 — complete:** live search over title/description, startup
reminders for overdue / due-today tasks (desktop notification via plyer),
undo for deletes (button + `Ctrl+Z`), and a dark-mode toggle whose choice is
remembered across launches (`QSettings`). Categories/tags are handled by the
existing category field and its filter.

**Scheduled / recurring tasks — complete:** a task can repeat over a
start→end range — **daily**, **weekly** (on selectable weekdays, e.g.
Mon/Thu/Fri), or **monthly**. A date picker at the top chooses which day to
view; each day is independent, so completing one day leaves the next pending.
Cancel a **single day** or the **whole schedule from a chosen day forward**
(past days and their completions are kept). One-off tasks are always shown
regardless of the selected day. There's also an **Urgent** priority above High.

Planned next:
- **Phase 4:** package per-OS with PyInstaller; CI tests.

## Project layout

```
main.py                      # entry point — wires model → controller → view
models/
  task.py                    # Task dataclass + Priority enum + overdue logic
  schedule.py                # Schedule/Occurrence + recurrence logic (occurs_on)
  task_repository.py         # SQLite CRUD for tasks + schedules + overrides
controllers/
  task_controller.py         # mediates view <-> repository (no Qt imports)
views/
  main_window.py             # task table + toolbar + sorting + filters + search + day picker
  task_dialog.py             # add/edit dialog; one-off deadline or repeat schedule
  task_list.py               # drag-to-reorder QTableWidget subclass
  theme.py                   # light/dark palettes + QSettings persistence
services/
  notifier.py                # plyer desktop-notification wrapper
data/tasks.db                # SQLite database (gitignored)
tests/
  test_task_logic.py         # pytest logic-layer tests (in-memory DB)
  test_schedule_logic.py     # recurrence + schedule persistence tests
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
