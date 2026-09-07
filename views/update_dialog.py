"""Auto-update UI: background check/download workers, prompt + changelog dialogs.

The threading mirrors :class:`views.integration_tab._SyncWorker` — a plain
``QObject`` moved onto a ``QThread``, reporting back over signals — so network
work never blocks the UI. :class:`UpdateManager` ties it together and is the only
thing the main window needs to touch.
"""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from services import updater
from services.updater import UpdateError, UpdateInfo
from version import APP_VERSION, RELEASES_PAGE_URL

_ORG = "TaskManager"
_APP = "TaskManager"
_LAST_SHOWN_KEY = "updates/last_shown_version"


# ---- resource loading ---------------------------------------------------------
def _release_notes_path() -> Path:
    """Locate the bundled ``RELEASE_NOTES.md`` (unpacked under _MEIPASS if frozen)."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "RELEASE_NOTES.md"


def _load_release_notes() -> str:
    try:
        return _release_notes_path().read_text(encoding="utf-8")
    except OSError:
        return ""


# ---- workers ------------------------------------------------------------------
class _CheckWorker(QObject):
    """Runs one update check off the UI thread and reports back."""

    #: Emitted with an :class:`UpdateInfo` when newer, or ``None`` when up to date.
    done = Signal(object)
    #: Emitted with a human-readable message when the check itself failed.
    failed = Signal(str)
    finished = Signal()

    def run(self) -> None:
        try:
            info = updater.check_for_update_strict(APP_VERSION)
            self.done.emit(info)
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"Unexpected error: {exc}")
        finally:
            self.finished.emit()


class _DownloadWorker(QObject):
    """Downloads the new exe and launches the self-replace helper."""

    progress = Signal(int)
    #: Emitted once the helper is spawned and the app should quit to be replaced.
    ready = Signal()
    failed = Signal(str)
    finished = Signal()

    def __init__(self, info: UpdateInfo) -> None:
        super().__init__()
        self._info = info

    def run(self) -> None:
        try:
            updater.download_and_apply(self._info, self.progress.emit)
            self.ready.emit()
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"Unexpected error: {exc}")
        finally:
            self.finished.emit()


# ---- dialogs ------------------------------------------------------------------
class _NotesDialog(QDialog):
    """Base dialog that renders Markdown notes in a scrollable browser."""

    def __init__(self, title: str, heading: str, notes: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 460)
        layout = QVBoxLayout(self)

        label = QLabel(heading)
        label.setTextFormat(Qt.TextFormat.PlainText)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        layout.addWidget(label)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        if notes.strip():
            browser.setMarkdown(notes)
        else:
            browser.setPlainText("No release notes are available for this version.")
        layout.addWidget(browser)
        self._browser = browser

        self._buttons = QDialogButtonBox()
        layout.addWidget(self._buttons)


class UpdatePromptDialog(_NotesDialog):
    """Offers to install a newer version; shows its release notes."""

    def __init__(self, info: UpdateInfo, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            title="Update available",
            heading=f"Task Manager {info.version} is available "
                    f"(you have {APP_VERSION}).",
            notes=info.notes,
            parent=parent,
        )
        self._update_btn = QPushButton("Update now")
        self._update_btn.setDefault(True)
        later_btn = QPushButton("Later")
        self._buttons.addButton(self._update_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self._buttons.addButton(later_btn, QDialogButtonBox.ButtonRole.RejectRole)
        self._update_btn.clicked.connect(self.accept)
        later_btn.clicked.connect(self.reject)


class WhatsNewDialog(_NotesDialog):
    """Post-update changelog popup, shown once on first launch of a new version."""

    def __init__(self, version: str, notes: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            title="What's new",
            heading=f"Task Manager was updated to {version}.",
            notes=notes,
            parent=parent,
        )
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        self._buttons.addButton(close_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        close_btn.clicked.connect(self.accept)


# ---- orchestration ------------------------------------------------------------
class UpdateManager(QObject):
    """Coordinates update checks, the install flow, and the post-update popup.

    Owned by the main window. Keep a reference alive for the app's lifetime so
    the worker threads it spawns are not garbage-collected mid-run.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self._thread: Optional[QThread] = None
        self._worker: Optional[QObject] = None
        self._manual = False

    # ---- post-update "what's new" ----------------------------------------
    def maybe_show_whats_new(self) -> None:
        """Show the changelog once, the first time a newer build runs.

        On a fresh install (no stored version) the current version is recorded
        silently so notes only ever appear *after* an actual update.
        """
        settings = QSettings(_ORG, _APP)
        last_shown = settings.value(_LAST_SHOWN_KEY, "", type=str)
        if not last_shown:
            settings.setValue(_LAST_SHOWN_KEY, APP_VERSION)
            return
        if updater.is_newer(APP_VERSION, last_shown):
            WhatsNewDialog(APP_VERSION, _load_release_notes(), self._parent).exec()
            settings.setValue(_LAST_SHOWN_KEY, APP_VERSION)

    # ---- checking --------------------------------------------------------
    def check_silent(self) -> None:
        """Background check on startup; only speaks up if an update exists."""
        self._start_check(manual=False)

    def check_manual(self) -> None:
        """User-triggered check; also reports 'up to date' and check failures."""
        self._start_check(manual=True)

    def _start_check(self, manual: bool) -> None:
        if self._thread is not None:  # a check or download is already running
            if manual:
                QMessageBox.information(self._parent, "Check for updates",
                                        "An update check is already in progress.")
            return
        self._manual = manual
        self._thread = QThread(self)
        worker = _CheckWorker()
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.done.connect(self._on_check_done)
        worker.failed.connect(self._on_check_failed)
        worker.finished.connect(self._cleanup)
        self._thread.start()

    def _on_check_done(self, info: Optional[UpdateInfo]) -> None:
        if info is None:
            if self._manual:
                QMessageBox.information(
                    self._parent, "Check for updates",
                    f"You're on the latest version ({APP_VERSION}).")
            return
        self._prompt_and_install(info)

    def _on_check_failed(self, message: str) -> None:
        if self._manual:
            QMessageBox.warning(self._parent, "Check for updates",
                                f"Couldn't check for updates.\n\n{message}")

    # ---- installing ------------------------------------------------------
    def _prompt_and_install(self, info: UpdateInfo) -> None:
        dialog = UpdatePromptDialog(info, self._parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not updater.can_self_install():
            # Non-frozen dev run (or non-Windows): fall back to the download page.
            self._open_releases_page()
            return
        self._start_download(info)

    def _start_download(self, info: UpdateInfo) -> None:
        progress = QProgressDialog("Downloading update…", "Cancel", 0, 100,
                                   self._parent)
        progress.setWindowTitle("Updating")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        self._progress = progress

        self._thread = QThread(self)
        worker = _DownloadWorker(info)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.progress.connect(progress.setValue)
        worker.ready.connect(self._on_download_ready)
        worker.failed.connect(self._on_download_failed)
        worker.finished.connect(self._cleanup)
        # Cancelling only stops the UI wait; the guard in _on_download_ready
        # prevents a relaunch the user cancelled out of.
        progress.canceled.connect(self._on_cancel)
        self._cancelled = False
        self._thread.start()

    def _on_cancel(self) -> None:
        self._cancelled = True

    def _on_download_ready(self) -> None:
        if getattr(self, "_progress", None) is not None:
            self._progress.reset()
        if getattr(self, "_cancelled", False):
            return
        QMessageBox.information(
            self._parent, "Updating",
            "The update was downloaded. Task Manager will now close and reopen "
            "on the new version.")
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _on_download_failed(self, message: str) -> None:
        if getattr(self, "_progress", None) is not None:
            self._progress.reset()
        box = QMessageBox(self._parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Update failed")
        box.setText(f"The update could not be installed.\n\n{message}")
        box.setInformativeText("You can download it manually from the releases page.")
        open_btn = box.addButton("Open releases page", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_releases_page()

    def _open_releases_page(self) -> None:
        if not QDesktopServices.openUrl(QUrl(RELEASES_PAGE_URL)):
            webbrowser.open(RELEASES_PAGE_URL)

    # ---- lifecycle -------------------------------------------------------
    def _cleanup(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None

    def shutdown(self) -> None:
        """Wait for any in-flight check/download so the app can close cleanly.

        Called from the window's ``closeEvent`` — a silent check runs on every
        startup, and quitting mid-check would otherwise destroy a live QThread.
        """
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None
