"""Integrations tab: configure the Azure DevOps connection and sync PRs.

The actual network call runs on a worker thread (:class:`_SyncWorker`) so the UI
never freezes. On success the worker hands the fetched pull requests back to the
window via the ``prs_fetched`` signal; the window reconciles them through the
controller and refreshes the task list.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.integration import AzureConfig
from models.task import Priority
from services import credentials, integration_settings
from services.azure_client import AzureDevOpsClient, AzureError
from views.blueprint import BlueprintFrame


def _priority_combo() -> QComboBox:
    combo = QComboBox()
    for p in (Priority.URGENT, Priority.HIGH, Priority.MEDIUM, Priority.LOW):
        combo.addItem(p.label, p)
    return combo


class _SyncWorker(QObject):
    """Runs one Azure operation off the UI thread and reports back."""

    #: ({source: list[PullRequest]}, organization_slug) on a successful sync.
    synced = Signal(dict, str)
    #: (ok, message) for a connection test.
    tested = Signal(bool, str)
    #: human-readable error string.
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self, config: AzureConfig, pat: str, mode: str, sources: list[str] | None = None
    ) -> None:
        super().__init__()
        self._config = config
        self._pat = pat
        self._mode = mode  # "sync" | "test"
        self._sources = sources or []

    def run(self) -> None:
        try:
            client = AzureDevOpsClient(
                self._config.org_slug, self._pat, self._config.project
            )
            if self._mode == "test":
                ok, message = client.test_connection()
                self.tested.emit(ok, message)
            else:
                identity = self._config.reviewer_id or client.get_authenticated_user_id()
                results: dict[str, list] = {}
                if "review" in self._sources:
                    results["review"] = client.list_review_requested_prs(identity)
                if "author" in self._sources:
                    authored = client.list_created_prs(identity)
                    self._attach_comment_counts(client, authored)
                    results["author"] = authored
                self.synced.emit(results, self._config.org_slug)
        except AzureError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"Unexpected error: {exc}")
        finally:
            self.finished.emit()

    @staticmethod
    def _attach_comment_counts(client: AzureDevOpsClient, prs: list) -> None:
        """Fill in each authored PR's unresolved comment count.

        A failure fetching one PR's threads degrades that PR to 0 rather than
        aborting the whole sync — the rest of the reconciliation still runs.
        """
        for pr in prs:
            try:
                pr.unresolved_comment_count = client.active_comment_count(
                    pr.repository_id, pr.pr_id
                )
            except AzureError:
                pr.unresolved_comment_count = 0


class IntegrationTab(QWidget):
    """Form for the Azure DevOps integration plus Test/Sync actions."""

    #: Emitted with the reconcile summary dict after a successful sync.
    sync_completed = Signal(dict)
    #: Emitted ({source: list[PullRequest]}, org) so the window runs the controller sync.
    prs_fetched = Signal(dict, str)
    #: Emitted after the integration is removed, so the window can forget PR links.
    cleared = Signal()
    #: Emitted (is_busy, operation_label) around every network worker run so the
    #: window can show a shared footer busy indicator.
    busy_changed = Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _SyncWorker | None = None
        self._build_ui()
        self._load()

    # ---- UI --------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        heading = QLabel("Azure DevOps")
        heading.setObjectName("pageHeading")
        subtitle = QLabel(
            "Turn your pull requests into tasks. The access token is stored in the OS "
            "keyring — never in the app database."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(subtitle)

        # ---- two blueprint panels, side by side, top-aligned -------------
        columns = QGridLayout()
        columns.setHorizontalSpacing(18)
        columns.setColumnStretch(0, 1)
        columns.setColumnStretch(1, 1)
        columns.addWidget(self._build_connection_panel(), 0, 0, Qt.AlignmentFlag.AlignTop)
        columns.addWidget(self._build_sources_panel(), 0, 1, Qt.AlignmentFlag.AlignTop)
        root.addLayout(columns)

        buttons = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.setObjectName("primary")
        self._test_btn = QPushButton("Test connection")
        self._sync_btn = QPushButton("Sync now")
        self._save_btn.clicked.connect(self._on_save)
        self._test_btn.clicked.connect(self._on_test)
        self._sync_btn.clicked.connect(lambda: self.trigger_sync(auto=False))
        self._remove_btn = QPushButton("Remove integration")
        self._remove_btn.setObjectName("danger")
        self._remove_btn.clicked.connect(self._on_remove)
        buttons.addWidget(self._save_btn)
        buttons.addWidget(self._test_btn)
        buttons.addWidget(self._sync_btn)
        buttons.addStretch(1)
        buttons.addWidget(self._remove_btn)
        root.addLayout(buttons)

        self._status = QLabel("Not configured.")
        self._status.setObjectName("statusStrip")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def _build_connection_panel(self) -> BlueprintFrame:
        """Left panel: enable switch + connection settings."""
        panel = BlueprintFrame()

        self._enabled = QCheckBox("Enable Azure integration")
        self._enabled.setObjectName("cardHeading")
        panel.body.addWidget(self._enabled)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(11)

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
        self._poll.setFixedWidth(70)
        poll_row = QHBoxLayout()
        poll_row.setSpacing(8)
        poll_row.addWidget(self._poll)
        poll_suffix = QLabel("minutes, off the UI thread")
        poll_suffix.setObjectName("mutedHint")
        poll_row.addWidget(poll_suffix)
        poll_row.addStretch(1)
        form.addRow("Auto-sync every", poll_row)

        panel.body.addLayout(form)
        return panel

    def _build_sources_panel(self) -> BlueprintFrame:
        """Right panel: which PRs become tasks, with per-source priorities."""
        panel = BlueprintFrame()

        title = QLabel("Create tasks from pull requests")
        title.setObjectName("blueprintTitle")
        panel.body.addWidget(title)

        # Reviewer source: enable + required/optional priorities.
        reviewer_card = QFrame()
        reviewer_card.setObjectName("card")
        rc = QVBoxLayout(reviewer_card)
        rc.setContentsMargins(14, 12, 14, 12)
        rc.setSpacing(10)
        self._cb_reviewer = QCheckBox("Create tasks for PRs I review")
        self._cb_reviewer.setObjectName("cardHeading")
        self._cb_reviewer.toggled.connect(self._update_source_visibility)
        rc.addWidget(self._cb_reviewer)

        reviewer_form = QFormLayout()
        reviewer_form.setHorizontalSpacing(16)
        reviewer_form.setVerticalSpacing(10)
        self._priority_required = _priority_combo()
        self._required_label = QLabel("Required-reviewer priority")
        reviewer_form.addRow(self._required_label, self._priority_required)
        self._priority_optional = _priority_combo()
        self._optional_label = QLabel("Optional-reviewer priority")
        reviewer_form.addRow(self._optional_label, self._priority_optional)
        rc.addLayout(reviewer_form)
        panel.body.addWidget(reviewer_card)

        # Author source: enable + priority.
        author_card = QFrame()
        author_card.setObjectName("card")
        ac = QVBoxLayout(author_card)
        ac.setContentsMargins(14, 12, 14, 12)
        ac.setSpacing(10)
        self._cb_author = QCheckBox("Create tasks for PRs I created")
        self._cb_author.setObjectName("cardHeading")
        self._cb_author.toggled.connect(self._update_source_visibility)
        ac.addWidget(self._cb_author)

        author_form = QFormLayout()
        author_form.setHorizontalSpacing(16)
        author_form.setVerticalSpacing(10)
        self._priority_author = _priority_combo()
        self._author_label = QLabel("My-PR priority")
        author_form.addRow(self._author_label, self._priority_author)
        ac.addLayout(author_form)
        panel.body.addWidget(author_card)

        return panel

    def _update_source_visibility(self) -> None:
        """Show each source's priority selectors when that source is switched on,
        and enable Sync now while at least one source is active."""
        reviewer_on = self._cb_reviewer.isChecked()
        author_on = self._cb_author.isChecked()
        for w in (self._required_label, self._priority_required,
                  self._optional_label, self._priority_optional):
            w.setVisible(reviewer_on)
        for w in (self._author_label, self._priority_author):
            w.setVisible(author_on)
        self._sync_btn.setEnabled(reviewer_on or author_on)

    # ---- config load/save ------------------------------------------------
    def _load(self) -> None:
        cfg = integration_settings.load_config()
        self._enabled.setChecked(cfg.enabled)
        self._org.setText(cfg.organization)
        self._project.setText(cfg.project)
        self._poll.setValue(cfg.poll_minutes)
        self._cb_reviewer.setChecked(cfg.create_for_reviewer)
        self._cb_author.setChecked(cfg.create_for_author)
        self._set_priority(self._priority_required, cfg.priority_required)
        self._set_priority(self._priority_optional, cfg.priority_optional)
        self._set_priority(self._priority_author, cfg.priority_author)
        self._update_source_visibility()
        if credentials.load_pat():
            self._pat.setPlaceholderText("•••••••• (saved — type to replace)")
        self._refresh_status(cfg)

    @staticmethod
    def _set_priority(combo: QComboBox, priority: Priority) -> None:
        idx = combo.findData(priority)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def current_config(self) -> AzureConfig:
        """Config as currently shown in the form (reviewer_id kept from storage)."""
        stored = integration_settings.load_config()
        return AzureConfig(
            enabled=self._enabled.isChecked(),
            organization=self._org.text().strip(),
            project=self._project.text().strip(),
            reviewer_id=stored.reviewer_id,
            poll_minutes=self._poll.value(),
            create_for_reviewer=self._cb_reviewer.isChecked(),
            create_for_author=self._cb_author.isChecked(),
            priority_required=self._priority_required.currentData(),
            priority_optional=self._priority_optional.currentData(),
            priority_author=self._priority_author.currentData(),
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
        elif not cfg.enabled_sources:
            self._status.setText(
                f"Ready — organization '{cfg.org_slug}'. Enable a PR source above to "
                "create tasks."
            )
        else:
            self._status.setText(f"Ready — organization '{cfg.org_slug}'.")

    # ---- actions ---------------------------------------------------------
    def _on_test(self) -> None:
        self._start_worker("test")

    def _on_remove(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Remove integration",
            "Delete the saved Azure connection?\n\n"
            "This removes the access token and all integration settings, and forgets "
            "which pull requests were already synced. Tasks that were already created "
            "are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        credentials.delete_pat()
        integration_settings.clear_config()
        self.cleared.emit()          # window forgets PR links + stops polling
        self._reset_form()

    def _reset_form(self) -> None:
        defaults = AzureConfig()
        self._enabled.setChecked(defaults.enabled)
        self._org.clear()
        self._project.clear()
        self._poll.setValue(defaults.poll_minutes)
        self._cb_reviewer.setChecked(defaults.create_for_reviewer)
        self._cb_author.setChecked(defaults.create_for_author)
        self._set_priority(self._priority_required, defaults.priority_required)
        self._set_priority(self._priority_optional, defaults.priority_optional)
        self._set_priority(self._priority_author, defaults.priority_author)
        self._update_source_visibility()
        self._pat.clear()
        self._pat.setPlaceholderText("Personal Access Token (Code → Read)")
        self._status.setText("Integration removed.")

    def trigger_sync(self, *, auto: bool = False) -> None:
        """Kick off a background sync of every enabled source. ``auto`` marks
        poll-driven runs (quieter — it no-ops when nothing is configured)."""
        cfg = self.current_config()
        if auto and not cfg.has_active_sources():
            return
        self._start_worker("sync", sources=cfg.enabled_sources)

    def _start_worker(self, mode: str, sources: list[str] | None = None) -> None:
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
        if mode == "sync" and not sources:
            self._status.setText("Enable a PR source above before syncing.")
            return

        self._set_busy(True)
        self._status.setText("Testing…" if mode == "test" else "Syncing…")
        self.busy_changed.emit(
            True, "Testing Azure…" if mode == "test" else "Syncing Azure…"
        )

        self._thread = QThread(self)
        self._worker = _SyncWorker(cfg, pat, mode, sources)
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

    def _on_synced(self, results: dict, organization: str) -> None:
        # The window owns the controller; let it reconcile + refresh.
        self.prs_fetched.emit(results, organization)

    def _on_failed(self, message: str) -> None:
        self._status.setText(f"Error: {message}")

    def report_sync_result(self, summary: dict) -> None:
        """Called back by the window after it reconciles the fetched PRs."""
        from datetime import datetime

        stamp = datetime.now().strftime("%H:%M")
        parts = [
            f"{summary['created']} created",
            f"{summary['completed']} completed",
        ]
        if summary.get("reopened"):
            parts.append(f"{summary['reopened']} reopened")
        parts.append(f"{summary['skipped']} unchanged")
        self._status.setText(f"Synced {stamp} · " + ", ".join(parts) + ".")
        self.sync_completed.emit(summary)

    def _cleanup_worker(self) -> None:
        self._set_busy(False)
        self.busy_changed.emit(False, "")
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None

    def _set_busy(self, busy: bool) -> None:
        for btn in (self._test_btn, self._save_btn, self._remove_btn):
            btn.setEnabled(not busy)
        # Sync now additionally depends on whether a source is enabled.
        if busy:
            self._sync_btn.setEnabled(False)
        else:
            self._update_source_visibility()
