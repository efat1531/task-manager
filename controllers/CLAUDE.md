# controllers/ — view ↔ repository mediator (NO Qt)

| File | Purpose |
|------|---------|
| `task_controller.py` | `TaskController` — the single controller. Task/schedule CRUD via the repository, undo stack, day/export logic, and Azure/Linear **sync reconciliation**. |

## Invariants
- **No Qt imports, no network I/O** — stays headlessly unit-testable.
- Sync methods **receive already-fetched** PRs/issues (fetched by a QThread worker in
  the view) and reconcile them against `pr_links`: create exactly one task per
  PR/issue, re-prioritize on status change, auto-complete when it leaves scope.
- `order_rows(tasks, occurrences, order_by)` merges one-off tasks with recurring
  occurrences into one ordering; under manual `sort_order` occurrences follow tasks,
  otherwise both are interleaved by the sort key. Pinned (unresolved-comment) rows
  stay first — matches `TaskRepository.list`.
- Undo stack entries are `(label, reverse_callable)`.
