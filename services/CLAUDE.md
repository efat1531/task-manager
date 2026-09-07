# services/ — I/O adapters

External-world boundaries: OS keyring, HTTP APIs, notifications, self-update, and
QSettings persistence. (May import Qt for `QSettings` — that's fine here.)

| File | Purpose |
|------|---------|
| `credentials.py` | **Secrets in the OS keyring only.** `save/load/delete_pat` (Azure) and `save/load/delete_linear_key`; degrades gracefully if no keyring backend. |
| `azure_client.py` | `AzureDevOpsClient` — Azure DevOps REST over stdlib `urllib`; raises `AzureError`. |
| `linear_client.py` | `LinearClient` — Linear GraphQL over stdlib `urllib`; raises `LinearError`. |
| `updater.py` | Self-update: `check_for_update`, `parse_version`/`is_newer`, `parse_release`, asset pick, download + self-replace helper `.bat`. |
| `notifier.py` | `notify()` desktop notifications via `plyer` (`notifications_available()` guard). |
| `integration_settings.py` | Azure non-secret config in `QSettings` (`load/save/clear_config`). |
| `linear_settings.py` | Linear non-secret config in `QSettings`. |

## Invariants
- **No HTTP dependency** — Azure/Linear clients use stdlib `urllib` only.
- **Secrets never leave the keyring** (not in DB, not in QSettings). Only non-secret
  config goes in `*_settings.py`.
- Every keyring/network call is wrapped so a missing backend or offline state
  degrades gracefully rather than crashing the app.
- These are called from `views/` QThread workers, not the controller.
