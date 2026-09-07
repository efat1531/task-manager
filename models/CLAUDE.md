# models/ — data & business logic (NO Qt)

Pure Python, headlessly testable. No Qt imports, no network. See root `CLAUDE.md`.

| File | Purpose |
|------|---------|
| `task.py` | `Task` dataclass + `Priority` IntEnum (Low/Medium/High/Urgent) + overdue logic. |
| `schedule.py` | `Schedule` / `Occurrence` dataclasses, `Frequency` enum, `occurs_on(schedule, day)` recurrence rule (daily/weekly-by-weekday/monthly). |
| `integration.py` | Azure `AzureConfig` / `PullRequest`; `pr_key(org, id, source)` → `"{source}:{org}:{id}"`; `pr_to_task_fields` PR→task mapping. |
| `linear.py` | `LinearConfig` / `LinearIssue`; `linear_key(id)` → `"linear:{id}"`; `filter_excluded`, `issue_to_task_fields` (per-status priority). |
| `linkify.py` | Text helpers: `first_url(*texts)`, `pr_number(title)`. |
| `task_repository.py` | **The only place SQL lives.** SQLite DAO for tasks, schedules, `schedule_overrides`, and `pr_links`. |

## Invariants
- **All SQL stays in `task_repository.py`**, parameterized; `list(order_by=...)` uses
  a whitelist. Rows with `unresolved_comments > 0` are pinned to the top.
- Schema changes to existing tables → add an `ALTER TABLE` in `_migrate`
  (`CREATE TABLE IF NOT EXISTS` won't add columns).
- `pr_key` / `linear_key` are stable dedup keys sharing the `pr_links` table; the
  source/`linear:` prefix keeps each integration's tasks isolated.
- Dates are ISO strings.
