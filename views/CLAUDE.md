# views/ — all Qt UI lives here

The only layer that imports Qt (PySide6). Talks to the app through
`TaskController`; never touches SQL directly.

| File | Purpose |
|------|---------|
| `main_window.py` | `MainWindow` — tabbed shell: task table, toolbar, sort/filter/search, day picker, Help→update menu, export. |
| `task_dialog.py` | `TaskDialog` — add/edit; one-off deadline **or** repeat schedule. |
| `task_list.py` | `TaskTable` — `QTableWidget` subclass with drag-to-reorder. |
| `integration_tab.py` | Azure config UI + `_SyncWorker` (QThread network worker). |
| `linear_tab.py` | Linear config UI (teams, per-status priority, exclude labels) + `_LinearWorker`. |
| `update_dialog.py` | Auto-update: `_CheckWorker`/`_DownloadWorker`, prompt & "what's new" dialogs, `UpdateManager`. |
| `blueprint.py` | `BlueprintFrame` — hairline-bordered panel with crosshair corner marks (integration tabs). |
| `flow_layout.py` | `FlowLayout` — left-packed wrapping row layout for the Linear exclude-label chips. |
| `theme.py` | Light/dark palettes, persisted via `QSettings`. |

## Invariants
- **Network I/O runs on a `QThread` worker** (`_SyncWorker`, `_LinearWorker`,
  `_CheckWorker`, `_DownloadWorker`) so the UI never blocks; hand fetched data to the
  controller to reconcile — don't do reconciliation logic in the view.
- Both integration tabs emit `busy_changed(bool, str)` around each worker run
  (`_start_worker` → True, `_cleanup_worker` → False); `MainWindow` shows a shared
  footer busy bar + per-integration next-sync countdown from these + the poll timers.
- Put reusable non-UI logic in `models/`/`controllers/`, not here.
- Persisted UI/config state → `QSettings`; secrets → keyring via `services/credentials.py`.
