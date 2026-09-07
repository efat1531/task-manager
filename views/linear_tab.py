"""Linear tab: configure the Linear connection and sync assigned issues to tasks.

The network calls run on a worker thread (:class:`_LinearWorker`) so the UI never
freezes. Configuration is progressive: enter an API key, load the teams, then load
each team's workflow statuses and labels. For every status you can choose whether
it creates tasks; the task's priority comes from the Linear ticket itself. Any
label you tick excludes issues that carry it. On a successful sync the worker
hands the fetched issues back to the
window via the ``issues_fetched`` signal; the window reconciles them through the
controller and refreshes the task list.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.linear import LinearConfig
from services import credentials, linear_settings
from services.linear_client import LinearClient, LinearError


class _LinearWorker(QObject):
    """Runs one Linear operation off the UI thread and reports back."""

    #: (list[LinearIssue],) on a successful sync.
    synced = Signal(list)
    #: (ok, message) for a connection test.
    tested = Signal(bool, str)
    #: (list[team dict],) after loading teams.
    teams_loaded = Signal(list)
    #: (list[state dict], list[label name]) after loading statuses + labels.
    meta_loaded = Signal(list, list)
    #: human-readable error string.
    failed = Signal(str)
    finished = Signal()

    def __init__(self, api_key: str, mode: str, config: LinearConfig) -> None:
        super().__init__()
        self._api_key = api_key
        self._mode = mode  # "test" | "teams" | "meta" | "sync"
        self._config = config

    def run(self) -> None:
        try:
            client = LinearClient(self._api_key)
            if self._mode == "test":
                ok, message = client.test_connection()
                self.tested.emit(ok, message)
            elif self._mode == "teams":
                self.teams_loaded.emit(client.list_teams())
            elif self._mode == "meta":
                states = client.list_workflow_states(self._config.team_ids)
                labels = client.list_labels(self._config.team_ids)
                self.meta_loaded.emit(states, labels)
            else:  # sync
                issues = client.list_assigned_issues(
                    self._config.team_ids, self._config.synced_state_ids()
                )
                self.synced.emit(issues)
        except LinearError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"Unexpected error: {exc}")
        finally:
            self.finished.emit()


class LinearIntegrationTab(QWidget):
    """Form for the Linear integration plus Load/Test/Sync actions."""

    #: Emitted with the reconcile summary dict after a successful sync.
    sync_completed = Signal(dict)
    #: Emitted (list[LinearIssue],) so the window runs the controller sync.
    issues_fetched = Signal(list)
    #: Emitted after the integration is removed, so the window forgets links.
    cleared = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _LinearWorker | None = None
        # Per-state rows: state_id -> (checkbox, name).
        self._status_rows: dict[str, tuple[QCheckBox, str]] = {}
        self._build_ui()
        self._load()

    # ---- UI --------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)

        box = QGroupBox("Linear")
        form = QFormLayout(box)

        self._enabled = QCheckBox("Enable Linear integration")
        form.addRow(self._enabled)

        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("Personal API key (lin_api_…)")
        form.addRow("API key", self._api_key)

        self._poll = QSpinBox()
        self._poll.setRange(1, 1440)
        self._poll.setSuffix(" min")
        form.addRow("Auto-sync every", self._poll)
        root.addWidget(box)

        # ---- teams -------------------------------------------------------
        teams_box = QGroupBox("Teams")
        teams_layout = QVBoxLayout(teams_box)
        self._load_teams_btn = QPushButton("Load teams")
        self._load_teams_btn.clicked.connect(lambda: self._start_worker("teams"))
        teams_layout.addWidget(self._load_teams_btn)
        self._teams_list = QListWidget()
        self._teams_list.setMaximumHeight(120)
        teams_layout.addWidget(self._teams_list)
        self._load_meta_btn = QPushButton("Load statuses & labels for selected teams")
        self._load_meta_btn.clicked.connect(self._on_load_meta)
        teams_layout.addWidget(self._load_meta_btn)
        root.addWidget(teams_box)

        # ---- statuses ----------------------------------------------------
        self._status_box = QGroupBox("Create tasks from these statuses")
        self._status_form = QFormLayout(self._status_box)
        self._status_hint = QLabel(
            "Load statuses above, then tick each status you want to become tasks. "
            "Each task takes its priority from the Linear ticket."
        )
        self._status_hint.setWordWrap(True)
        self._status_hint.setEnabled(False)
        self._status_form.addRow(self._status_hint)
        root.addWidget(self._status_box)

        # ---- exclude labels ---------------------------------------------
        labels_box = QGroupBox("Exclude issues with any of these labels")
        labels_layout = QVBoxLayout(labels_box)
        self._labels_list = QListWidget()
        self._labels_list.setMaximumHeight(120)
        labels_layout.addWidget(self._labels_list)
        root.addWidget(labels_box)

        # ---- buttons -----------------------------------------------------
        buttons = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._test_btn = QPushButton("Test connection")
        self._sync_btn = QPushButton("Sync now")
        self._save_btn.clicked.connect(self._on_save)
        self._test_btn.clicked.connect(lambda: self._start_worker("test"))
        self._sync_btn.clicked.connect(lambda: self.trigger_sync(auto=False))
        self._remove_btn = QPushButton("Remove integration")
        self._remove_btn.clicked.connect(self._on_remove)
        buttons.addWidget(self._save_btn)
        buttons.addWidget(self._test_btn)
        buttons.addWidget(self._sync_btn)
        buttons.addStretch(1)
        buttons.addWidget(self._remove_btn)
        root.addLayout(buttons)

        self._status = QLabel("Not configured.")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ---- status rows -----------------------------------------------------
    def _populate_status_rows(self, states: list[dict]) -> None:
        """Rebuild the status checkbox rows from fetched workflow states,
        preserving any existing selection from the saved config."""
        saved = {str(s["id"]): s for s in self.current_config().status_priorities}
        # Clear previous rows (keep the hint at row 0).
        while self._status_form.rowCount() > 1:
            self._status_form.removeRow(1)
        self._status_rows.clear()

        for state in states:
            sid = str(state.get("id", ""))
            name = state.get("name", sid)
            if not sid:
                continue
            check = QCheckBox(name)
            if sid in saved:
                check.setChecked(True)
            self._status_form.addRow(check)
            self._status_rows[sid] = (check, name)
        self._status_hint.setVisible(not states)

    def _populate_labels(self, labels: list[str]) -> None:
        saved = set(self.current_config().exclude_labels)
        self._labels_list.clear()
        for name in labels:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if name in saved else Qt.CheckState.Unchecked
            )
            self._labels_list.addItem(item)

    def _populate_teams(self, teams: list[dict]) -> None:
        saved = set(self.current_config().team_ids)
        self._teams_list.clear()
        for team in teams:
            tid = str(team.get("id", ""))
            label = f"{team.get('name', tid)} ({team.get('key', '')})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, tid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if tid in saved else Qt.CheckState.Unchecked
            )
            self._teams_list.addItem(item)

    def _checked_team_ids(self) -> list[str]:
        ids = []
        for i in range(self._teams_list.count()):
            item = self._teams_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    def _checked_labels(self) -> list[str]:
        names = []
        for i in range(self._labels_list.count()):
            item = self._labels_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                names.append(item.text())
        return names

    def _status_priorities(self) -> list[dict]:
        rows = []
        for sid, (check, name) in self._status_rows.items():
            if check.isChecked():
                rows.append({"id": sid, "name": name})
        return rows

    # ---- config load/save ------------------------------------------------
    def _load(self) -> None:
        cfg = linear_settings.load_config()
        self._enabled.setChecked(cfg.enabled)
        self._poll.setValue(cfg.poll_minutes)
        if credentials.load_linear_key():
            self._api_key.setPlaceholderText("•••••••• (saved — type to replace)")
        # Show saved statuses/labels even before a fresh fetch, so the user sees
        # what is configured. Teams are shown by id until "Load teams" resolves names.
        self._populate_status_rows(
            [{"id": s["id"], "name": s.get("name", s["id"])}
             for s in cfg.status_priorities]
        )
        self._populate_labels(cfg.exclude_labels)
        self._populate_teams([{"id": t, "name": t, "key": ""} for t in cfg.team_ids])
        self._refresh_status(cfg)

    def current_config(self) -> LinearConfig:
        """Config as currently shown in the form.

        When no status/label/team widgets have been populated yet (fresh load),
        fall back to the stored values so a save/sync before "Load teams" keeps
        the persisted selection instead of wiping it.
        """
        stored = linear_settings.load_config()
        team_ids = self._checked_team_ids() or stored.team_ids
        status_priorities = self._status_priorities() or stored.status_priorities
        exclude_labels = (
            self._checked_labels() if self._labels_list.count() else stored.exclude_labels
        )
        return LinearConfig(
            enabled=self._enabled.isChecked(),
            team_ids=team_ids,
            poll_minutes=self._poll.value(),
            status_priorities=status_priorities,
            exclude_labels=exclude_labels,
        )

    def _on_save(self) -> None:
        cfg = self.current_config()
        linear_settings.save_config(cfg)
        typed = self._api_key.text().strip()
        if typed:
            if credentials.save_linear_key(typed):
                self._api_key.clear()
                self._api_key.setPlaceholderText("•••••••• (saved — type to replace)")
            else:
                self._status.setText(
                    "Settings saved, but no secure keyring is available to store the "
                    "API key. Install the 'keyring' package or it won't persist."
                )
                return
        self._refresh_status(cfg)
        self._status.setText("Settings saved.")

    def _refresh_status(self, cfg: LinearConfig) -> None:
        if not cfg.enabled:
            self._status.setText("Integration disabled.")
        elif not credentials.load_linear_key() and not self._api_key.text().strip():
            self._status.setText("Enter and save a Linear API key.")
        elif not cfg.team_ids:
            self._status.setText("Load teams and pick at least one to sync.")
        elif not cfg.synced_state_ids():
            self._status.setText("Tick at least one status to create tasks from.")
        else:
            self._status.setText("Ready.")

    # ---- actions ---------------------------------------------------------
    def _on_load_meta(self) -> None:
        if not self._checked_team_ids():
            self._status.setText("Select at least one team first.")
            return
        self._start_worker("meta")

    def _on_remove(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Remove integration",
            "Delete the saved Linear connection?\n\n"
            "This removes the API key and all Linear settings, and forgets which "
            "issues were already synced. Tasks that were already created are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        credentials.delete_linear_key()
        linear_settings.clear_config()
        self.cleared.emit()
        self._reset_form()

    def _reset_form(self) -> None:
        self._enabled.setChecked(False)
        self._poll.setValue(15)
        self._teams_list.clear()
        self._labels_list.clear()
        self._populate_status_rows([])
        self._api_key.clear()
        self._api_key.setPlaceholderText("Personal API key (lin_api_…)")
        self._status.setText("Integration removed.")

    def trigger_sync(self, *, auto: bool = False) -> None:
        """Kick off a background sync of assigned issues. ``auto`` marks
        poll-driven runs (quieter — it no-ops when nothing is configured)."""
        cfg = self.current_config()
        if auto and not cfg.has_active_sources():
            return
        self._start_worker("sync")

    def _start_worker(self, mode: str) -> None:
        if self._thread is not None:  # a run is already in flight
            return
        cfg = self.current_config()
        key = self._api_key.text().strip() or (credentials.load_linear_key() or "")
        if not key:
            self._status.setText("Enter a Linear API key first.")
            return
        if mode == "meta" and not cfg.team_ids:
            self._status.setText("Select at least one team first.")
            return
        if mode == "sync" and not cfg.has_active_sources():
            self._status.setText("Pick a team and at least one status before syncing.")
            return

        self._set_busy(True)
        self._status.setText({
            "test": "Testing…", "teams": "Loading teams…",
            "meta": "Loading statuses & labels…",
        }.get(mode, "Syncing…"))

        self._thread = QThread(self)
        self._worker = _LinearWorker(key, mode, cfg)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.tested.connect(self._on_tested)
        self._worker.teams_loaded.connect(self._on_teams_loaded)
        self._worker.meta_loaded.connect(self._on_meta_loaded)
        self._worker.synced.connect(self._on_synced)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _on_tested(self, ok: bool, message: str) -> None:
        self._status.setText(message)

    def _on_teams_loaded(self, teams: list) -> None:
        self._populate_teams(teams)
        self._status.setText(f"Loaded {len(teams)} team(s). Select some, then load statuses.")

    def _on_meta_loaded(self, states: list, labels: list) -> None:
        self._populate_status_rows(states)
        self._populate_labels(labels)
        self._status.setText(
            f"Loaded {len(states)} status(es) and {len(labels)} label(s)."
        )

    def _on_synced(self, issues: list) -> None:
        # The window owns the controller; let it reconcile + refresh.
        self.issues_fetched.emit(issues)

    def _on_failed(self, message: str) -> None:
        self._status.setText(f"Error: {message}")

    def report_sync_result(self, summary: dict) -> None:
        from datetime import datetime

        stamp = datetime.now().strftime("%H:%M")
        parts = [
            f"{summary['created']} created",
            f"{summary['completed']} completed",
            f"{summary.get('reopened', 0)} reopened",
            f"{summary['skipped']} unchanged",
        ]
        self._status.setText(f"Synced {stamp} · " + ", ".join(parts) + ".")
        self.sync_completed.emit(summary)

    def _cleanup_worker(self) -> None:
        self._set_busy(False)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None

    def _set_busy(self, busy: bool) -> None:
        for btn in (self._test_btn, self._save_btn, self._remove_btn,
                    self._sync_btn, self._load_teams_btn, self._load_meta_btn):
            btn.setEnabled(not busy)
