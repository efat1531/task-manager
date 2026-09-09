# CLAUDE.md

Agent brief for this repo. See `README.md` for the full feature narrative and
end-user/setup docs — this file covers only what an agent needs to work here.

**What it is:** a cross-platform desktop **Task Manager** — PySide6 (Qt 6) UI +
SQLite (stdlib `sqlite3`), organized as **MVC**. It manages one-off tasks and
recurring schedules, and auto-generates tasks from Azure DevOps PRs and Linear
issues.

## Golden rule — layering

`models/` and `controllers/` contain **no Qt imports** (verified: zero PySide6
references). All business logic — task CRUD, recurrence, PR/issue dedup and
lifecycle — lives there so it stays **headlessly unit-testable**. Qt lives only in
`views/`. Network I/O runs on **`QThread` workers inside the views**; the
controller only ever receives already-fetched data to reconcile. `services/` may
import Qt (`QSettings`) — the no-Qt rule is models + controllers only.

Keep this rule when adding code: put logic in models/controllers, wire Qt in views.

## Layers (wired in `main.py`: model → controller → view)

- `models/` — data + business logic; dataclasses, enums, recurrence, dedup, and the
  **single SQLite data-access layer** (`task_repository.py`, all SQL lives here).
- `controllers/` — `task_controller.py` mediates view ↔ repository; undo stack,
  row merge/sort, sync reconciliation. No Qt, no network.
- `views/` — all Qt UI; tabs, dialogs, table, theme, and the QThread network workers.
- `services/` — I/O adapters: keyring, Azure REST / Linear GraphQL clients (stdlib
  `urllib`), self-updater, plyer notifier, QSettings persistence.
- `version.py` — single source of truth for `APP_VERSION` + repo constants.
- `tests/` — headless logic tests (in-memory DB) + one `pytest-qt` render test.

Each layer directory has its own `CLAUDE.md` with a file→purpose map — read it when
working in that directory.

## Commands (Windows / PowerShell)

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1   # first time
pip install -r requirements.txt
python main.py                    # run from source (DB at data\tasks.db)
pytest                            # 139 tests, headless, ~0.3s
pyinstaller task_manager.spec     # build dist\TaskManager.exe
```

## Conventions

- `from __future__ import annotations` at the top of every module.
- Dataclasses for models; `Priority` (IntEnum) and `Frequency` enums.
- **All SQL is confined to `models/task_repository.py`**, always parameterized.
  `order_by` values are validated against a whitelist — never interpolate raw SQL.
- Dates are **ISO strings** (`YYYY-MM-DD` / ISO datetime), stored as TEXT.
- **Secrets (Azure PAT, Linear key) live only in the OS keyring** via
  `services/credentials.py` — never in the DB or QSettings. Non-secret config goes
  in QSettings (`services/integration_settings.py`, `linear_settings.py`, `theme.py`).

## Data & dedup keys

- DB: `data\tasks.db` from source; `%LOCALAPPDATA%\TaskManager\tasks.db` when frozen
  (see `_data_dir` in `main.py`). Gitignored.
- Tables: `tasks`, `schedules`, `schedule_overrides`, `pr_links`.
- Dedup keys share the `pr_links` table: Azure `review:<org>:<id>` /
  `author:<org>:<id>` (`pr_key`, `models/integration.py`), Linear `linear:<id>`
  (`linear_key`, `models/linear.py`). **`pr_links` rows survive task deletion** by
  design, so a PR/issue is never turned into a task twice.
- Tasks with `unresolved_comments > 0` (authored-PR comment threads) are **pinned to
  the top** in `TaskRepository.list` regardless of sort.

## Release flow

Bump `APP_VERSION` in `version.py` **and** edit `RELEASE_NOTES.md` in the same
commit, then tag `v<APP_VERSION>` and push the tag. CI
(`.github/workflows/release.yml`) **asserts the tag equals `v` + APP_VERSION**, runs
tests, builds the portable `TaskManager.exe`, and publishes the GitHub Release.
Distribution is the portable exe only — there is no installer.

## Gotchas

- Schema changes to existing tables need an `ALTER TABLE` in
  `TaskRepository._migrate` — `CREATE TABLE IF NOT EXISTS` never adds columns to an
  existing table.
- Don't import Qt into model/controller tests; they run headless (`:memory:` DB).
- The controller never does network calls — add fetching to a QThread worker in the
  relevant view and pass results in.
