# tests/ — pytest suite

Run from the project root: `pytest` (currently **172 tests**, ~0.9s). Each test
module prepends the repo root to `sys.path`, so no install/packaging is needed.

| File | Covers |
|------|--------|
| `test_task_logic.py` | Task CRUD, validation, completion, undo (in-memory DB). |
| `test_schedule_logic.py` | `occurs_on` recurrence + schedule/override persistence. |
| `test_integration_logic.py` | Azure PR dedup, auto-complete, parsing, source + priority. |
| `test_linear_logic.py` | Linear dedup, auto-complete, status-priority, label exclusion, parsing. |
| `test_export_logic.py` | Per-day JSON export scoping + serialization. |
| `test_updater_logic.py` | Version compare / asset pick / release parsing (no network). |
| `test_linkify_and_pinning.py` | `linkify` helpers + unresolved-comment pinning. |
| `test_notification_logic.py` | Notification feed CRUD/dedup, reminder + sync event recording, `NotificationConfig` gating/quiet-hours, `relative_time`. |
| `test_row_ordering_and_reorder.py` | `order_rows` merge/sort + manual reorder (logic, no Qt). |
| `test_title_cell_rendering.py` | Title-cell rendering — **the only test that needs `pytest-qt`/`qtbot`**. |

## Conventions
- **Logic tests use an in-memory DB** (`TaskRepository(":memory:")`) and no Qt/display
  — they run headless in CI. Add new logic tests this way.
- Only `test_title_cell_rendering.py` uses `pytest-qt` (`qtbot`); keep
  display-dependent assertions out of the logic tests.
- No network in tests — updater/integration tests parse fixed payloads.
