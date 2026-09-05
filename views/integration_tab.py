"""Integrations tab: configure the Azure DevOps connection and sync PRs.

The actual network call runs on a worker thread (:class:`_SyncWorker`) so the UI
never freezes. On success the worker hands the fetched pull requests back to the
window via the ``synced`` signal; the window reconciles them through the
controller and refreshes the task list.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.integration import AzureConfig
from services import credentials, integration_settings
from services.azure_client import AzureDevOpsClient, AzureError


class _SyncWorker(QObject):
    """Runs one Azure operation off the UI thread and reports back."""

    #: (list[PullRequest], organization_slug) on a successful sync.
    synced = Signal(list, str)
    #: (ok, message) for a connection test.
    tested = Signal(bool, str)
    #: human-readable error string.
    failed = Signal(str)
    finished = Signal()

    def __init__(self, config: AzureConfig, pat: str, mode: str) -> None:
        super().__init__()
        self._config = config
        self._pat = pat
        self._mode = mode  # "sync" | "test"

    def run(self) -> None:
        try:
            client = AzureDevOpsClient(
                self._config.org_slug, self._pat, self._config.project
            )
            if self._mode == "test":
                ok, message = client.test_connection()
                self.tested.emit(ok, message)
            else:
                reviewer_id = self._config.reviewer_id or client.get_authenticated_user_id()
                prs = client.list_review_requested_prs(reviewer_id)
                self.synced.emit(prs, self._config.org_slug)
        except AzureError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"Unexpected error: {exc}")
        finally:
            self.finished.emit()


class IntegrationTab(QWidget):
    """Form for the Azure DevOps integration plus Test/Sync actions."""

    #: Emitted with the reconcile summary dict after a successful sync.
    sync_completed = Signal(dict)
    #: Emitted (list[PullRequest], org) so the window can run the controller sync.
    prs_fetched = Signal(list, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _SyncWorker | None = None
        self._build_ui()
        self._load()

    # ---- UI --------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        box = QGroupBox("Azure DevOps")
        form = QFormLayout(box)

        self._enabled = QCheckBox("Enable Azure integration")
        form.addRow(self._enabled)

        self._org = QLineEdit()
        self._org.setPlaceholderText("myorg  or  https://dev.azure.com/myorg")
        form.addRow("Organization", self._org)

        self._project = QLineEdit()
        self._project.setPlaceholderText("Optional — leave blank for all projects")
        form.addRow("Project", self._project)

        self._pat = QLineEdit()
        self._pat.setEchoMode(QLineEdit.EchoMode.Password)
        self._pat.setPlaceholderText("Personal Access Token (Code → Read)")
        form.addRow("Access token", self._pat)

        self._poll = QSpinBox()
        self._poll.setRange(1, 1440)
        self._poll.setSuffix(" min")
        form.addRow("Auto-sync every", self._poll)

        root.addWidget(box)

        buttons = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._test_btn = QPushButton("Test connection")
        self._sync_btn = QPushButton("Sync now")
        self._save_btn.clicked.connect(self._on_save)
        self._test_btn.clicked.connect(self._on_test)
        self._sync_btn.clicked.connect(self.trigger_sync)
        buttons.addWidget(self._save_btn)
        buttons.addWidget(self._test_btn)
        buttons.addWidget(self._sync_btn)
        buttons.addStretch(1)
        root.addLayout(buttons)

        self._status = QLabel("Not configured.")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        help_text = QLabel(
            "Any active pull request where you are a reviewer becomes a task — "
            "<b>required</b> reviews are High priority, <b>optional</b> ones Medium. "
            "Each PR creates a task only once. When a PR is merged, abandoned, or you "
            "are no longer a reviewer, its task is marked complete on the next sync."
        )
        help_text.setWordWrap(True)
        help_text.setEnabled(False)
        root.addWidget(help_text)
        root.addStretch(1)

    # ---- config load/save ------------------------------------------------
    def _load(self) -> None:
        cfg = integration_settings.load_config()
        self._enabled.setChecked(cfg.enabled)
        self._org.setText(cfg.organization)
        self._project.setText(cfg.project)
        self._poll.setValue(cfg.poll_minutes)
        if credentials.load_pat():
            self._pat.setPlaceholderText("•••••••• (saved — type to replace)")
        self._refresh_status(cfg)

    def current_config(self) -> AzureConfig:
        """Config as currently shown in the form (reviewer_id kept from storage)."""
        stored = integration_settings.load_config()
        return AzureConfig(
            enabled=self._enabled.isChecked(),
            organization=self._org.text().strip(),
            project=self._project.text().strip(),
            reviewer_id=stored.reviewer_id,
            poll_minutes=self._poll.value(),
        )

    def _on_save(self) -> None:
        cfg = self.current_config()
        integration_settings.save_config(cfg)
        typed = self._pat.text().strip()
        if typed:
            if credentials.save_pat(typed):
                self._pat.clear()
                self._pat.setPlaceholderText("•••••••• (saved — type to replace)")
            else:
                self._status.setText(
                    "Settings saved, but no secure keyring is available to store the "
                    "token. Install the 'keyring' package or the token won't persist."
                )
                return
        self._refresh_status(cfg)
        self._status.setText("Settings saved.")

    def _refresh_status(self, cfg: AzureConfig) -> None:
        if not cfg.enabled:
            self._status.setText("Integration disabled.")
        elif not cfg.org_slug:
            self._status.setText("Enter an organization to get started.")
        elif not credentials.load_pat():
            self._status.setText("Enter and save a Personal Access Token.")
        else:
            self._status.setText(f"Ready — organization '{cfg.org_slug}'.")

    # ---- actions ---------------------------------------------------------
    def _on_test(self) -> None:
        self._start_worker("test")

    def trigger_sync(self, *, auto: bool = False) -> None:
        """Kick off a background sync. ``auto`` marks poll-driven runs (quieter)."""
        cfg = self.current_config()
        if auto and not cfg.is_configured():
            return
        self._start_worker("sync")

    def _start_worker(self, mode: str) -> None:
        if self._thread is not None:  # a run is already in flight
            return
        cfg = self.current_config()
        pat = self._pat.text().strip() or (credentials.load_pat() or "")
        if not cfg.org_slug:
            self._status.setText("Enter an organization first.")
            return
        if not pat:
            self._status.setText("Enter a Personal Access Token first.")
            return

        self._set_busy(True)
        self._status.setText("Testing…" if mode == "test" else "Syncing…")

        self._thread = QThread(self)
        self._worker = _SyncWorker(cfg, pat, mode)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.tested.connect(self._on_tested)
        self._worker.synced.connect(self._on_synced)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _on_tested(self, ok: bool, message: str) -> None:
        self._status.setText(message)
        # A successful test yields the reviewer id — cache it for sync filtering.
        if ok and "identity: " in message:
            reviewer_id = message.rsplit("identity: ", 1)[1].strip()
            cfg = self.current_config()
            cfg.reviewer_id = reviewer_id
            integration_settings.save_config(cfg)

    def _on_synced(self, prs: list, organization: str) -> None:
        # The window owns the controller; let it reconcile + refresh.
        self.prs_fetched.emit(prs, organization)

    def _on_failed(self, message: str) -> None:
        self._status.setText(f"Error: {message}")

    def report_sync_result(self, summary: dict) -> None:
        """Called back by the window after it reconciles the fetched PRs."""
        from datetime import datetime

        stamp = datetime.now().strftime("%H:%M")
        self._status.setText(
            f"Synced {stamp} · {summary['created']} created, "
            f"{summary['completed']} completed, {summary['skipped']} unchanged."
        )
        self.sync_completed.emit(summary)

    def _cleanup_worker(self) -> None:
        self._set_busy(False)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None

    def _set_busy(self, busy: bool) -> None:
        for btn in (self._test_btn, self._sync_btn, self._save_btn):
            btn.setEnabled(not busy)
