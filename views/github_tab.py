"""GitHub tab: configure the connection and sync pull requests into tasks.

Mirrors :mod:`views.integration_tab` (Azure). The network calls run on a worker
thread (:class:`_GitHubWorker`) so the UI never freezes. On success the worker hands
the fetched pull requests back via ``prs_fetched``; the window reconciles them
through the controller and refreshes the task list.
"""
from __future__ import annotations

from datetime import datetime

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

from models.github import GitHubConfig
from models.task import Priority
from services import credentials, github_settings
from services.github_client import GitHubClient, GitHubError, token_is_valid
from views.blueprint import BlueprintFrame

_TOKEN_PLACEHOLDER = "Fine-grained token (Pull requests: Read-only)"
_TOKEN_HELP = (
    "Minimal token: GitHub → Settings → Developer settings → Personal access tokens → "
    "Fine-grained tokens. Resource owner: the account or organization that owns the "
    "repositories. Repository access: all repositories (PRs in unselected repositories "
    "are not synced). Permissions: Pull requests → Read-only; nothing else "
    "(Metadata: Read-only is added automatically). To sync PRs across several owners, "
    "use a classic token with the 'repo' scope instead."
)


def _priority_combo() -> QComboBox:
    combo = QComboBox()
    for p in (Priority.URGENT, Priority.HIGH, Priority.MEDIUM, Priority.LOW):
        combo.addItem(p.label, p)
    return combo


class _GitHubWorker(QObject):
    """Runs one GitHub operation off the UI thread and reports back."""

    #: {source: list[GitHubPullRequest]} on a successful sync.
    synced = Signal(dict)
    #: (ok, message) for a connection test.
    tested = Signal(bool, str)
    #: human-readable error string.
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self, config: GitHubConfig, token: str, mode: str,
        sources: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._token = token
        self._mode = mode  # "sync" | "test"
        self._sources = sources or []

    def run(self) -> None:
        try:
            client = GitHubClient(self._token)
            if self._mode == "test":
                ok, message = client.test_connection()
                self.tested.emit(ok, message)
            else:
                login = client.get_viewer_login()
                owner = self._config.owner_slug
                results: dict[str, list] = {}
                if "review" in self._sources:
                    results["review"] = client.list_review_requested_prs(login, owner)
                if "author" in self._sources:
                    results["author"] = client.list_created_prs(login, owner)
                self.synced.emit(results)
        except GitHubError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"Unexpected error: {exc}")
        finally:
            self.finished.emit()


class GitHubIntegrationTab(QWidget):
    """Form for the GitHub integration plus Test/Sync actions."""

    #: Emitted with the reconcile summary dict after a successful sync.
    sync_completed = Signal(dict)
    #: Emitted {source: list[GitHubPullRequest]} so the window runs the controller sync.
    prs_fetched = Signal(dict)
    #: Emitted after the integration is removed, so the window can forget PR links.
    cleared = Signal()
    #: Emitted (is_busy, operation_label) around every network worker run so the
    #: window can show a shared footer busy indicator.
    busy_changed = Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _GitHubWorker | None = None
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

        heading = QLabel("GitHub")
        heading.setObjectName("pageHeading")
        subtitle = QLabel(
            "Turn your pull requests into tasks. The access token is stored in the OS "
            "keyring — never in the app database."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(subtitle)
        token_help = QLabel(_TOKEN_HELP)
        token_help.setObjectName("pageSubtitle")
        token_help.setWordWrap(True)
        root.addWidget(token_help)

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
        panel = BlueprintFrame()

        self._enabled = QCheckBox("Enable GitHub integration")
        self._enabled.setObjectName("cardHeading")
        panel.body.addWidget(self._enabled)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(11)

        self._owner = QLineEdit()
        self._owner.setPlaceholderText("Optional — organization, blank for all")
        form.addRow("Organization", self._owner)

        self._token = QLineEdit()
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        self._token.setPlaceholderText(_TOKEN_PLACEHOLDER)
        form.addRow("Access token", self._token)

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
        panel = BlueprintFrame()

        title = QLabel("Create tasks from pull requests")
        title.setObjectName("blueprintTitle")
        panel.body.addWidget(title)

        reviewer_card, rc = self._source_card("Create tasks for PRs I'm asked to review")
        self._cb_reviewer = reviewer_card.findChild(QCheckBox)
        self._cb_reviewer.toggled.connect(self._update_source_visibility)
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self._priority_review = _priority_combo()
        self._review_label = QLabel("Review priority")
        form.addRow(self._review_label, self._priority_review)
        rc.addLayout(form)
        panel.body.addWidget(reviewer_card)

        author_card, ac = self._source_card("Create tasks for PRs I opened")
        self._cb_author = author_card.findChild(QCheckBox)
        self._cb_author.toggled.connect(self._update_source_visibility)
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self._priority_author = _priority_combo()
        self._author_label = QLabel("My-PR priority")
        form.addRow(self._author_label, self._priority_author)
        ac.addLayout(form)
        panel.body.addWidget(author_card)

        return panel

    @staticmethod
    def _source_card(text: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        checkbox = QCheckBox(text)
        checkbox.setObjectName("cardHeading")
        layout.addWidget(checkbox)
        return card, layout

    def _update_source_visibility(self) -> None:
        """Show each source's priority selector when that source is on, and enable
        Sync now while at least one source is active."""
        reviewer_on = self._cb_reviewer.isChecked()
        author_on = self._cb_author.isChecked()
        for w in (self._review_label, self._priority_review):
            w.setVisible(reviewer_on)
        for w in (self._author_label, self._priority_author):
            w.setVisible(author_on)
        self._sync_btn.setEnabled((reviewer_on or author_on) and self._thread is None)

    # ---- config load/save ------------------------------------------------
    def _load(self) -> None:
        cfg = github_settings.load_config()
        self._enabled.setChecked(cfg.enabled)
        self._owner.setText(cfg.owner)
        self._poll.setValue(cfg.poll_minutes)
        self._cb_reviewer.setChecked(cfg.create_for_reviewer)
        self._cb_author.setChecked(cfg.create_for_author)
        self._set_priority(self._priority_review, cfg.priority_review)
        self._set_priority(self._priority_author, cfg.priority_author)
        self._update_source_visibility()
        if credentials.load_github_token():
            self._token.setPlaceholderText("•••••••• (saved — type to replace)")
        self._refresh_status(cfg)

    @staticmethod
    def _set_priority(combo: QComboBox, priority: Priority) -> None:
        idx = combo.findData(priority)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def current_config(self) -> GitHubConfig:
        """Config as currently shown in the form."""
        return GitHubConfig(
            enabled=self._enabled.isChecked(),
            owner=self._owner.text().strip(),
            poll_minutes=self._poll.value(),
            create_for_reviewer=self._cb_reviewer.isChecked(),
            create_for_author=self._cb_author.isChecked(),
            priority_review=self._priority_review.currentData(),
            priority_author=self._priority_author.currentData(),
        )

    def _on_save(self) -> None:
        cfg = self.current_config()
        if not cfg.owner_is_valid:
            self._status.setText(
                "The organization looks invalid — use just the name, e.g. 'contoso'."
            )
            return
        github_settings.save_config(cfg)
        typed = self._token.text().strip()
        if typed and not token_is_valid(typed):
            self._status.setText(
                "Settings saved, but the token contains spaces or control characters — "
                "paste it again."
            )
            return
        if typed:
            if credentials.save_github_token(typed):
                self._token.clear()
                self._token.setPlaceholderText("•••••••• (saved — type to replace)")
            else:
                self._status.setText(
                    "Settings saved, but no secure keyring is available to store the "
                    "token. Install the 'keyring' package or the token won't persist."
                )
                return
        self._refresh_status(cfg)
        self._status.setText("Settings saved.")

    def _refresh_status(self, cfg: GitHubConfig) -> None:
        if not cfg.enabled:
            self._status.setText("Integration disabled.")
        elif not cfg.owner_is_valid:
            self._status.setText("The organization looks invalid.")
        elif not credentials.load_github_token():
            self._status.setText("Enter and save a GitHub access token.")
        elif not cfg.enabled_sources:
            self._status.setText(
                "Ready. Enable a pull-request source above to create tasks."
            )
        else:
            self._status.setText("Ready.")

    # ---- actions ---------------------------------------------------------
    def _on_test(self) -> None:
        self._start_worker("test")

    def _on_remove(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Remove integration",
            "Delete the saved GitHub connection?\n\n"
            "This removes the access token and all integration settings, and forgets "
            "which pull requests were already synced. Tasks that were already created "
            "are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        credentials.delete_github_token()
        github_settings.clear_config()
        self.cleared.emit()          # window forgets PR links + stops polling
        self._reset_form()

    def _reset_form(self) -> None:
        defaults = GitHubConfig()
        self._enabled.setChecked(defaults.enabled)
        self._owner.clear()
        self._poll.setValue(defaults.poll_minutes)
        self._cb_reviewer.setChecked(defaults.create_for_reviewer)
        self._cb_author.setChecked(defaults.create_for_author)
        self._set_priority(self._priority_review, defaults.priority_review)
        self._set_priority(self._priority_author, defaults.priority_author)
        self._update_source_visibility()
        self._token.clear()
        self._token.setPlaceholderText(_TOKEN_PLACEHOLDER)
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
        token = self._token.text().strip() or (credentials.load_github_token() or "")
        if not cfg.owner_is_valid:
            self._status.setText("The organization looks invalid.")
            return
        if not token:
            self._status.setText("Enter a GitHub access token first.")
            return
        if mode == "sync" and not cfg.enabled:
            self._status.setText("Tick 'Enable GitHub integration' before syncing.")
            return
        if mode == "sync" and not sources:
            self._status.setText("Enable a pull-request source above before syncing.")
            return

        self._set_busy(True)
        self._status.setText("Testing…" if mode == "test" else "Syncing…")
        self.busy_changed.emit(
            True, "Testing GitHub…" if mode == "test" else "Syncing GitHub…"
        )

        self._thread = QThread(self)
        self._worker = _GitHubWorker(cfg, token, mode, sources)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.tested.connect(self._on_tested)
        self._worker.synced.connect(self.prs_fetched)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _on_tested(self, ok: bool, message: str) -> None:
        # ``tested`` carries (ok, message); the label only takes the text.
        self._status.setText(message)

    def _on_failed(self, message: str) -> None:
        self._status.setText(f"Error: {message}")

    def report_sync_result(self, summary: dict) -> None:
        """Called back by the window after it reconciles the fetched PRs."""
        stamp = datetime.now().strftime("%H:%M")
        parts = [
            f"{summary['created']} created",
            f"{summary['completed']} completed",
        ]
        if summary.get("reopened"):
            parts.append(f"{summary['reopened']} reopened")
        parts.append(f"{summary['skipped']} unchanged")
        text = f"Synced {stamp} · " + ", ".join(parts) + "."
        if summary.get("held"):
            text += (
                f" GitHub returned no pull requests, so {summary['held']} open tasks "
                "were left as they are — check the token's access and the Organization filter."
            )
        self._status.setText(text)
        self.sync_completed.emit(summary)

    def _cleanup_worker(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None
        self._set_busy(False)
        self.busy_changed.emit(False, "")

    def _set_busy(self, busy: bool) -> None:
        for btn in (self._test_btn, self._save_btn, self._remove_btn):
            btn.setEnabled(not busy)
        if busy:
            self._sync_btn.setEnabled(False)
        else:
            self._update_source_visibility()
