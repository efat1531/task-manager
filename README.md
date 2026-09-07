# Task Manager

A cross-platform desktop task manager built with **PySide6 (Qt)** and **SQLite**,
organized around a clean **MVC** architecture. Manage one-off tasks and recurring
schedules, and auto-generate tasks from your Azure DevOps pull requests and Linear issues.

[![Release](https://img.shields.io/github/v/release/efat1531/task-manager?sort=semver)](https://github.com/efat1531/task-manager/releases)
[![Build](https://github.com/efat1531/task-manager/actions/workflows/release.yml/badge.svg)](https://github.com/efat1531/task-manager/actions/workflows/release.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## Features

### Tasks
- Create, edit, and delete tasks with **title, description, category, deadline,
  and priority** (Low · Medium · High · **Urgent**).
- Deadlines via a calendar date picker; **overdue** open tasks are shown in red and
  completed tasks are struck through.
- Sort by priority, deadline, created date, or **manual order** — in manual mode,
  **drag-and-drop** rows to reorder (persisted to `sort_order`).
- Filter by **status** (all / open / completed) and by **category**, and **live
  search** across title and description.
- **Undo** deletes with a button or `Ctrl+Z`.
- **Export a day to JSON** — pick a date and copy that day's tasks (one-off tasks due that
  date plus recurring occurrences on it) to the clipboard as JSON via **Export day…**.
- Startup **reminders** for overdue / due-today tasks (desktop notifications via
  `plyer`).
- **Dark mode** toggle, remembered across launches (`QSettings`).

### Recurring schedules
- A task can repeat over a **start → end** range: **daily**, **weekly** (on chosen
  weekdays, e.g. Mon/Thu/Fri), or **monthly**.
- A date picker chooses which day to view; **each day is independent**, so completing
  one occurrence leaves later ones pending.
- Cancel a **single day** or the **whole schedule from a chosen day forward** — past
  days and their completions are always preserved.
- One-off tasks stay visible regardless of the selected day.

### Azure DevOps integration
- An **Integrations** tab connects to Azure DevOps using a **Personal Access Token**,
  stored securely in the **OS keyring** (never in the app database or settings file).
- Choose which pull requests become tasks — enable **PRs you review**, **PRs you
  created**, or both. Each source has its own **Sync now** button.
- **Configurable priorities**: pick the priority for **required** and **optional**
  reviewer PRs, and a separate priority for **your own** PRs. The reviewer priority
  selectors appear only when the reviewer source is enabled; the author priority selector
  appears only when the author source is enabled.
- **Exactly one task per PR** — never duplicated on re-sync, and never re-created even
  if you delete the task (the PR link persists). Each source is tracked independently.
- When a PR is **merged, abandoned, or you're dropped/no longer involved**, its task is
  **auto-completed** on the next sync of that source.
- Runs on demand via each **Sync now** button and on a **configurable background
  auto-poll**, all off the UI thread so the app never freezes.

### Linear integration
- A **Linear** tab connects to Linear using a **personal API key**, stored securely
  in the **OS keyring** (never in the app database or settings file).
- **Assigned to you**: issues assigned to the authenticated user, in the **team(s)**
  you choose, become tasks. Load your teams, then load their **statuses & labels**.
- **Pick which statuses create tasks**: every workflow state is listed with a
  checkbox — tick the ones you want (e.g. *In Progress*, *In Review*).
- **Per-status priority**: each ticked status has its own priority selector, so a
  ticket's task priority follows its status. Moving a ticket between selected
  statuses re-prioritises its task on the next sync.
- **Exclude by label**: tick any labels whose issues should be left out — a ticket
  carrying an excluded label never becomes a task (and an existing task is
  auto-completed once the label is added).
- **Exactly one task per issue** — never duplicated on re-sync. When an issue leaves
  the selected statuses (e.g. moved to *Done*) or is reassigned, its task is
  **auto-completed** on the next sync.
- Runs on demand via **Sync now** and on a **configurable background auto-poll**,
  off the UI thread so the app never freezes.

### Packaging & distribution
- Builds to a **single-file Windows executable** with PyInstaller (windowed, app icon
  bundled).
- A **GitHub Actions** workflow runs the tests, builds the exe, and publishes a
  GitHub Release automatically on every version tag.

## Tech stack

| Layer        | Choice                                                        |
|--------------|---------------------------------------------------------------|
| UI           | PySide6 (Qt 6)                                                |
| Storage      | SQLite (stdlib `sqlite3`)                                      |
| Notifications| `plyer`                                                       |
| Secrets      | `keyring` (OS credential store, e.g. Windows Credential Manager) |
| Azure / Linear API | stdlib `urllib` (REST + GraphQL) — no extra HTTP dependency |
| Packaging    | PyInstaller                                                   |
| Tests        | `pytest` / `pytest-qt`                                         |

## Architecture

The codebase follows **MVC** with a strict rule: **the controller and model layers
contain no Qt imports**, so all business logic (task CRUD, recurrence, PR dedup and
lifecycle) is unit-testable headlessly. Network I/O for Azure runs on a `QThread`
worker; the controller only ever receives already-fetched data to reconcile.

## Project layout

```
main.py                       # entry point — wires model → controller → view; frozen-app aware
models/
  task.py                     # Task dataclass + Priority enum + overdue logic
  schedule.py                 # Schedule/Occurrence + recurrence logic (occurs_on)
  integration.py              # AzureConfig / PullRequest + PR→task mapping
  linear.py                   # LinearConfig / LinearIssue + status-priority + issue→task mapping
  task_repository.py          # SQLite CRUD for tasks, schedules, overrides, and external links
controllers/
  task_controller.py          # mediates view ↔ repository (no Qt imports)
views/
  main_window.py              # tabbed UI: task table, toolbar, sort/filter/search, day picker
  task_dialog.py              # add/edit dialog; one-off deadline or repeat schedule
  task_list.py                # drag-to-reorder QTableWidget subclass
  integration_tab.py          # Azure DevOps config + Sync (background worker)
  linear_tab.py               # Linear config: teams, per-status priority, exclude labels + Sync
  theme.py                    # light/dark palettes + QSettings persistence
services/
  notifier.py                 # plyer desktop-notification wrapper
  azure_client.py             # Azure DevOps REST client (stdlib urllib)
  linear_client.py            # Linear GraphQL client (stdlib urllib)
  credentials.py              # PAT / Linear key storage via OS keyring (with graceful fallback)
  integration_settings.py     # Azure config persistence (QSettings)
  linear_settings.py          # Linear config persistence (QSettings)
tests/
  test_task_logic.py          # task logic-layer tests (in-memory DB)
  test_schedule_logic.py      # recurrence + schedule persistence tests
  test_integration_logic.py   # PR dedup / auto-complete / parsing / source + priority tests
  test_linear_logic.py        # Linear dedup / auto-complete / status-priority / exclusion / parsing tests
  test_export_logic.py        # per-day JSON export scoping + serialization tests
assets/                       # app icons (png + multi-res ico)
task_manager.spec             # PyInstaller build spec
.github/workflows/release.yml # CI: run tests, build exe, publish release on version tags
data/tasks.db                 # SQLite database (gitignored)
```

## Getting started

### Download (end users)

Grab the latest **`TaskManager.exe`** from the
[Releases page](https://github.com/efat1531/task-manager/releases) — no Python
install needed, just run it. Your data is stored per-user at
`%LOCALAPPDATA%\TaskManager\tasks.db`.

> Windows SmartScreen may warn about an unknown publisher because the exe is
> unsigned — choose **More info → Run anyway**.

### Run from source (developers)

Requires **Python 3.10+**.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

When run from source, the database lives at `data\tasks.db` next to the project.

## Setting up the Azure integration

1. In Azure DevOps, create a **Personal Access Token** with **Code → Read** scope.
2. Open the **Integrations** tab in the app.
3. Enter your **organization** (e.g. `myorg` or `https://dev.azure.com/myorg`), an
   optional **project**, and paste the **token**, then **Save**.
4. Click **Test connection** to verify and auto-detect your identity.
5. Enable a PR source — **Create tasks for PRs I review** and/or **Create tasks for PRs I
   created** — and choose the priority for each, then **Save**.
6. Click the matching **Sync now** button (**Sync review PRs** / **Sync my PRs**), or
   leave the background auto-poll to keep tasks up to date.

The token is written only to your OS keyring. **Remove integration** deletes the
token and all Azure settings and forgets which PRs were synced (existing tasks are
kept).

## Setting up the Linear integration

1. In Linear, create a **personal API key** (Settings → Security & access → API).
2. Open the **Linear** tab in the app, tick **Enable Linear integration**, paste the
   **API key**, then **Save**. Click **Test connection** to verify.
3. Click **Load teams**, then tick the **team(s)** whose issues you want.
4. Click **Load statuses & labels for selected teams**.
5. Under **Create tasks from these statuses**, tick each status that should become a
   task (e.g. *In Progress*) and choose its **priority**.
6. Under **Exclude issues with any of these labels**, tick any labels whose issues
   should never appear.
7. **Save**, then **Sync now** — or leave the background auto-poll to keep tasks
   current.

Only issues **assigned to you** are synced. Each issue becomes exactly one task at
its status's priority; when an issue leaves the selected statuses, is reassigned, or
gains an excluded label, its task is auto-completed on the next sync. The API key is
written only to your OS keyring. **Remove integration** deletes the key and all
Linear settings and forgets which issues were synced (existing tasks are kept; Azure
links are untouched).

## Testing

```powershell
pytest
```

The logic tests use an in-memory SQLite database and require no display, so they run
headless and in CI (currently **43 tests**).

## Building the executable

```powershell
pip install pyinstaller
pyinstaller task_manager.spec
```

Produces the single-file `dist\TaskManager.exe` (windowed, with the app icon);
`assets/` is bundled into the binary.

## Cutting a release

Releases are automated. Tag a version and push the tag — GitHub Actions runs the
tests, builds the exe, and attaches it to a new GitHub Release:

```powershell
git tag v1.0.1
git push origin v1.0.1
```
