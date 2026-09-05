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

**Azure DevOps integration — complete:** an **Integrations** tab connects to
Azure DevOps with a Personal Access Token (stored securely in the OS keyring).
Any active pull request where you are a reviewer becomes a task — **required**
reviews at High priority, **optional** ones at Medium — created **once per PR**
(never duplicated on re-sync). When a PR is merged, abandoned, or you're no
longer a reviewer, its task is auto-completed on the next sync. Runs via a
**Sync now** button and a configurable background auto-poll.

**Packaging — complete:** builds to a single-file Windows executable with
PyInstaller; a GitHub Actions workflow builds and publishes a release on every
version tag.

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
  integration_tab.py         # Azure DevOps config + Sync (background worker)
models/
  integration.py             # AzureConfig / PullRequest + PR→task mapping
services/
  notifier.py                # plyer desktop-notification wrapper
  azure_client.py            # Azure DevOps REST client (stdlib urllib)
  credentials.py             # PAT storage via OS keyring (with fallback)
  integration_settings.py    # Azure config persistence (QSettings)
data/tasks.db                # SQLite database (gitignored)
task_manager.spec            # PyInstaller build spec
.github/workflows/release.yml# CI: build exe + publish release on version tags
tests/
  test_task_logic.py         # pytest logic-layer tests (in-memory DB)
  test_schedule_logic.py     # recurrence + schedule persistence tests
  test_integration_logic.py  # PR dedup / auto-complete / parsing tests
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

## Download

Grab the latest **`TaskManager.exe`** from the
[Releases page](../../releases) — no Python install needed, just run it.
Your tasks are stored per-user under `%LOCALAPPDATA%\TaskManager\tasks.db`.

## Build the executable

```powershell
pip install pyinstaller
pyinstaller task_manager.spec
```

The single-file `dist\TaskManager.exe` is produced (windowed, with the app
icon). `assets/` is bundled into the binary.

## Cut a release

Releases are automated. Tag a version and push it — GitHub Actions runs the
tests, builds the exe, and attaches it to a new GitHub Release:

```powershell
git tag v1.0.0
git push origin v1.0.0
```
