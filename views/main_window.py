"""Main application window: task table with create/edit/delete/complete + sorting."""
from __future__ import annotations

import html

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from controllers.task_controller import TaskController
from models import linkify
from models.schedule import Occurrence
from models.task import Task
from services import notifier
from version import APP_VERSION
from views import theme
from views.integration_tab import IntegrationTab
from views.linear_tab import LinearIntegrationTab
from views.task_dialog import TaskDialog
from views.task_list import TaskTable
from views.update_dialog import UpdateManager

_ALL_CATEGORIES = "All categories"

# Columns: [status, title, priority, deadline, category]
_HEADERS = ["✓", "Title", "Priority", "Deadline", "Category"]


class MainWindow(QMainWindow):
    def __init__(self, controller: TaskController) -> None:
        super().__init__()
        self._controller = controller
        self._dark = theme.load_dark_preference()
        self.setWindowTitle("Task Manager")
        self.resize(720, 480)
        self._build_ui()
        self._build_menu()
        self._apply_theme()
        self.refresh()
        self._prompt_reminders()

        # Auto-update: show the changelog once after an update, then quietly
        # check GitHub for a newer release in the background.
        self._updates = UpdateManager(self)
        self._updates.maybe_show_whats_new()
        self._updates.check_silent()

    @property
    def _overdue_color(self) -> QColor:
        return theme.OVERDUE_DARK if self._dark else theme.OVERDUE_LIGHT

    # ---- UI construction -------------------------------------------------
    def _build_ui(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tasks_tab(), "Tasks")

        self._integration_tab = IntegrationTab()
        self._integration_tab.prs_fetched.connect(self._on_prs_fetched)
        self._integration_tab.cleared.connect(self._on_integration_cleared)
        self._tabs.addTab(self._integration_tab, "Integrations")

        self._linear_tab = LinearIntegrationTab()
        self._linear_tab.issues_fetched.connect(self._on_linear_issues_fetched)
        self._linear_tab.cleared.connect(self._on_linear_cleared)
        self._tabs.addTab(self._linear_tab, "Linear")

        self.setCentralWidget(self._tabs)

        # Footer: a permanent status-bar label counting down to the next Azure
        # auto-sync. Shown only while Azure has active sources (see
        # _update_sync_countdown); hidden otherwise.
        self._sync_countdown = QLabel()
        self.statusBar().addPermanentWidget(self._sync_countdown)

        # Background auto-poll for the Azure integration.
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._auto_sync)
        self._start_poll_timer()

        # Ticks once a second to refresh the countdown label from the poll timer.
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._update_sync_countdown)
        self._countdown_timer.start(1000)
        self._update_sync_countdown()

        # Background auto-poll for the Linear integration.
        self._linear_poll_timer = QTimer(self)
        self._linear_poll_timer.timeout.connect(self._auto_sync_linear)
        self._start_linear_poll_timer()

    def _build_menu(self) -> None:
        """Menu bar: a Help menu hosting the update check and About box."""
        help_menu = self.menuBar().addMenu("&Help")
        check_action = help_menu.addAction("Check for updates…")
        check_action.triggered.connect(self._on_check_for_updates)
        about_action = help_menu.addAction("About Task Manager")
        about_action.triggered.connect(self._on_about)

    def _on_check_for_updates(self) -> None:
        self._updates.check_manual()

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About Task Manager",
            f"<b>Task Manager</b><br>Version {APP_VERSION}",
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Let any in-flight update check/download thread finish before we go.
        self._updates.shutdown()
        super().closeEvent(event)

    def _build_tasks_tab(self) -> QWidget:
        central = QWidget()
        root = QVBoxLayout(central)

        # Toolbar row: add / edit / delete / complete + sort selector.
        toolbar = QHBoxLayout()
        self._add_btn = QPushButton("Add")
        self._edit_btn = QPushButton("Edit")
        self._delete_btn = QPushButton("Delete")
        self._complete_btn = QPushButton("Toggle Complete")
        self._undo_btn = QPushButton("Undo")
        self._export_btn = QPushButton("Export day…")
        self._add_btn.clicked.connect(self._on_add)
        self._edit_btn.clicked.connect(self._on_edit)
        self._delete_btn.clicked.connect(self._on_delete)
        self._complete_btn.clicked.connect(self._on_toggle_complete)
        self._undo_btn.clicked.connect(self._on_undo)
        self._export_btn.clicked.connect(self._on_export_day)

        self._dark_btn = QPushButton("☀ Light" if self._dark else "🌙 Dark")
        self._dark_btn.setCheckable(True)
        self._dark_btn.setChecked(self._dark)
        self._dark_btn.toggled.connect(self._on_toggle_dark)

        self._sort = QComboBox()
        self._sort.addItem("Manual order", "sort_order")
        self._sort.addItem("Priority", "priority")
        self._sort.addItem("Deadline", "deadline")
        self._sort.addItem("Created", "created_at")
        self._sort.currentIndexChanged.connect(self.refresh)

        toolbar.addWidget(self._add_btn)
        toolbar.addWidget(self._edit_btn)
        toolbar.addWidget(self._delete_btn)
        toolbar.addWidget(self._complete_btn)
        toolbar.addWidget(self._undo_btn)
        toolbar.addWidget(self._export_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self._dark_btn)
        toolbar.addWidget(QLabel("Sort by:"))
        toolbar.addWidget(self._sort)
        root.addLayout(toolbar)

        # Day row: which calendar day the scheduled tasks are shown for.
        day_row = QHBoxLayout()
        self._prev_day_btn = QPushButton("◀")
        self._next_day_btn = QPushButton("▶")
        self._today_btn = QPushButton("Today")
        for b in (self._prev_day_btn, self._next_day_btn):
            b.setFixedWidth(32)
        self._day = QDateEdit()
        self._day.setCalendarPopup(True)
        self._day.setDisplayFormat("ddd, yyyy-MM-dd")
        self._day.setDate(QDate.currentDate())
        self._day.dateChanged.connect(self.refresh)
        self._prev_day_btn.clicked.connect(lambda: self._step_day(-1))
        self._next_day_btn.clicked.connect(lambda: self._step_day(1))
        self._today_btn.clicked.connect(lambda: self._day.setDate(QDate.currentDate()))

        day_row.addWidget(QLabel("Day:"))
        day_row.addWidget(self._prev_day_btn)
        day_row.addWidget(self._day)
        day_row.addWidget(self._next_day_btn)
        day_row.addWidget(self._today_btn)
        day_row.addStretch(1)
        root.addLayout(day_row)

        # Filter row: search + status + category.
        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search title / description…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self.refresh)

        self._status_filter = QComboBox()
        self._status_filter.addItem("All", "all")
        self._status_filter.addItem("Open", "open")
        self._status_filter.addItem("Completed", "completed")
        # Default to Open so completed tasks drop out of the list once ticked.
        self._status_filter.setCurrentIndex(self._status_filter.findData("open"))
        self._status_filter.currentIndexChanged.connect(self.refresh)

        self._category_filter = QComboBox()
        self._category_filter.addItem(_ALL_CATEGORIES)
        self._category_filter.currentIndexChanged.connect(self.refresh)

        filters.addWidget(self._search, 1)
        filters.addSpacing(12)
        filters.addWidget(QLabel("Status:"))
        filters.addWidget(self._status_filter)
        filters.addSpacing(12)
        filters.addWidget(QLabel("Category:"))
        filters.addWidget(self._category_filter)
        root.addLayout(filters)

        # Ctrl+Z undoes the last delete.
        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_shortcut.activated.connect(self._on_undo)

        # Table.
        self._table = TaskTable(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._on_edit)
        self._table.rows_reordered.connect(self._on_rows_reordered)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in range(2, len(_HEADERS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table)

        self._status = QLabel()
        root.addWidget(self._status)

        return central

    # ---- day selection ---------------------------------------------------
    def _selected_date(self) -> str:
        return self._day.date().toString("yyyy-MM-dd")

    def _step_day(self, delta: int) -> None:
        self._day.setDate(self._day.date().addDays(delta))

    # ---- data <-> view ---------------------------------------------------
    def refresh(self) -> None:
        order_by = self._sort.currentData()
        tasks = self._controller.list_tasks(order_by=order_by)
        # Scheduled occurrences for the selected day, most-urgent first.
        occurrences = sorted(
            self._controller.occurrences_on(self._selected_date()),
            key=lambda o: (-int(o.priority), o.title.lower()),
        )
        # Merge tasks and occurrences. Under manual order the occurrences follow
        # the tasks; under every other sort they are interleaved by the sort key
        # so priority/deadline ordering applies to the whole list, not just tasks.
        all_rows = self._controller.order_rows(list(tasks), occurrences, order_by)

        self._sync_category_filter(all_rows)

        # Dragging to reorder only makes sense under manual ordering.
        self._table.set_reorder_enabled(order_by == "sort_order")

        rows = [item for item in all_rows if self._passes_filters(item)]
        self._table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            self._populate_row(row, item)

        total = len(all_rows)
        done = sum(1 for t in all_rows if t.completed)
        showing = len(rows)
        suffix = "" if showing == total else f" · showing {showing}"
        self._status.setText(
            f"{total} item(s) · {done} completed · {total - done} open{suffix}"
        )

        self._undo_btn.setEnabled(self._controller.can_undo())
        label = self._controller.undo_label()
        self._undo_btn.setToolTip(f"Undo {label}" if label else "Nothing to undo")

    def _passes_filters(self, task: Task) -> bool:
        status = self._status_filter.currentData()
        if status == "open" and task.completed:
            return False
        if status == "completed" and not task.completed:
            return False
        category = self._category_filter.currentText()
        if category != _ALL_CATEGORIES and (task.category or "") != category:
            return False
        query = self._search.text().strip().lower()
        if query and query not in task.title.lower() and query not in task.description.lower():
            return False
        return True

    def _sync_category_filter(self, tasks: list[Task]) -> None:
        """Rebuild the category dropdown from existing tasks, keeping the choice."""
        categories = sorted({t.category for t in tasks if t.category})
        current = self._category_filter.currentText()
        self._category_filter.blockSignals(True)
        self._category_filter.clear()
        self._category_filter.addItem(_ALL_CATEGORIES)
        self._category_filter.addItems(categories)
        idx = self._category_filter.findText(current)
        self._category_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self._category_filter.blockSignals(False)

    def _on_rows_reordered(self, ordered_ids: list[int]) -> None:
        self._controller.reorder_tasks(ordered_ids)
        self.refresh()

    def _populate_row(self, row: int, task) -> None:
        unresolved = getattr(task, "unresolved_comments", 0) or 0

        status = QTableWidgetItem("✓" if task.completed else "")
        status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # Stash the Task on the first column for retrieval on select.
        status.setData(Qt.ItemDataRole.UserRole, task)

        # 🔁 marks recurring occurrences; 🔴 marks authored PRs with unresolved
        # comments (pinned to the top and shown as Urgent).
        prefix = "🔁 " if isinstance(task, Occurrence) else ""
        if unresolved > 0:
            prefix += "🔴 "
        title = f"{prefix}{task.title}"

        # While comments are unresolved the task reads as Urgent; the stored
        # priority is left untouched (display + sort override only).
        priority_label = "Urgent" if unresolved > 0 else task.priority.label

        # A URL anywhere in the task turns the title into a link that opens the
        # default browser; the PR "#123" token (when present) is the anchor, with
        # a trailing ↗. Trade-off: clicking the title area of a linked row no
        # longer selects/edit-opens it — select via any other cell instead.
        url = linkify.first_url(task.title, task.description)
        title_item = None if url else QTableWidgetItem(title)

        row_items = [
            status,
            QTableWidgetItem(priority_label),
            QTableWidgetItem(task.deadline or "—"),
            QTableWidgetItem(task.category or "—"),
        ]
        if title_item is not None:
            row_items.append(title_item)
        for item in row_items:
            if task.completed:
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
                item.setForeground(QColor(140, 140, 140))
            elif task.is_overdue:
                item.setForeground(self._overdue_color)

        self._table.setItem(row, 0, status)
        self._table.setItem(row, 2, row_items[1])
        self._table.setItem(row, 3, row_items[2])
        self._table.setItem(row, 4, row_items[3])

        # Clear any link widget AND any leftover item from a previous population
        # of this row index, so a transparent link QLabel is never drawn over
        # stale item text (rows are reused across refresh()).
        self._table.removeCellWidget(row, 1)
        self._table.takeItem(row, 1)
        if url:
            self._table.setCellWidget(row, 1, self._make_title_link(task, title, url))
        else:
            self._table.setItem(row, 1, title_item)

        if unresolved > 0:
            tip = f"{unresolved} unresolved comment(s)"
            for col in range(len(_HEADERS)):
                cell = self._table.item(row, col)
                widget = self._table.cellWidget(row, col)
                if cell is not None:
                    cell.setToolTip(tip)
                if widget is not None:
                    widget.setToolTip(tip)

    def _make_title_link(self, task, display_title: str, url: str) -> QLabel:
        """A rich-text title cell whose PR number / ↗ opens ``url`` in the browser."""
        href = html.escape(url, quote=True)
        text = html.escape(display_title)
        number = linkify.pr_number(task.title)
        if number and number in text:
            anchor = f'<a href="{href}">{html.escape(number)}</a>'
            text = text.replace(html.escape(number), anchor, 1)
        content = f'{text} <a href="{href}">↗</a>'

        # Bake the row styling into the span (completed = struck-through/gray,
        # overdue = tinted); links keep their own colour.
        style = ""
        if task.completed:
            style = "color:#8c8c8c; text-decoration: line-through;"
        elif getattr(task, "is_overdue", False):
            style = f"color:{self._overdue_color.name()};"
        if style:
            content = f'<span style="{style}">{content}</span>'

        label = QLabel(content)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.setContentsMargins(4, 0, 4, 0)
        return label

    def _selected_item(self):
        """Return the focused row's Task or Occurrence, or None (for single-item ops)."""
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_items(self) -> list:
        """Every selected row's Task/Occurrence, top-to-bottom."""
        rows = sorted({idx.row() for idx in self._table.selectionModel().selectedRows()})
        items = []
        for r in rows:
            cell = self._table.item(r, 0)
            if cell is not None:
                items.append(cell.data(Qt.ItemDataRole.UserRole))
        return items

    @staticmethod
    def _apply_schedule_values(schedule, values: dict) -> None:
        schedule.title = values["title"]
        schedule.description = values["description"]
        schedule.priority = values["priority"]
        schedule.category = values["category"]
        schedule.start_date = values["start_date"]
        schedule.end_date = values["end_date"]
        schedule.freq = values["freq"]
        schedule.weekdays = values["weekdays"]

    # ---- actions ---------------------------------------------------------
    def _on_add(self) -> None:
        dialog = TaskDialog(self)
        if dialog.exec() == TaskDialog.DialogCode.Accepted:
            values = dialog.get_values()
            if values.pop("schedule"):
                self._controller.create_schedule(**values)
            else:
                self._controller.create_task(**values)
            self.refresh()

    def _on_edit(self) -> None:
        item = self._selected_item()
        if item is None:
            self._warn_no_selection()
            return
        if isinstance(item, Occurrence):
            self._edit_schedule(item)
        else:
            self._edit_task(item)

    def _edit_task(self, task: Task) -> None:
        dialog = TaskDialog(self, task=task)
        if dialog.exec() != TaskDialog.DialogCode.Accepted:
            return
        values = dialog.get_values()
        if values.pop("schedule"):
            # Converted a one-off task into a schedule.
            self._controller.delete_task(task.id)
            self._controller.create_schedule(**values)
        else:
            task.title = values["title"]
            task.description = values["description"]
            task.priority = values["priority"]
            task.deadline = values["deadline"]
            task.category = values["category"]
            self._controller.update_task(task)
        self.refresh()

    def _edit_schedule(self, occurrence: Occurrence) -> None:
        schedule = self._controller.get_schedule(occurrence.schedule_id)
        if schedule is None:
            return
        dialog = TaskDialog(self, schedule=schedule)
        if dialog.exec() != TaskDialog.DialogCode.Accepted:
            return
        values = dialog.get_values()
        if values.pop("schedule"):
            self._apply_schedule_values(schedule, values)
            self._controller.update_schedule(schedule)
        else:
            # Converted a schedule into a one-off task.
            self._controller.delete_schedule(schedule.id)
            self._controller.create_task(**values)
        self.refresh()

    def _on_delete(self) -> None:
        items = self._selected_items()
        if not items:
            self._warn_no_selection()
            return
        if len(items) == 1:
            item = items[0]
            if isinstance(item, Occurrence):
                self._delete_occurrence(item)
                return
            confirm = QMessageBox.question(
                self,
                "Delete task",
                f"Delete “{item.title}”?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self._controller.delete_task(item.id)
                self.refresh()
            return
        # Bulk: tasks are deleted; scheduled occurrences are cancelled for that day.
        confirm = QMessageBox.question(
            self,
            "Delete items",
            f"Delete/cancel {len(items)} selected item(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for item in items:
            if isinstance(item, Occurrence):
                self._controller.cancel_occurrence_day(item.schedule_id, item.date)
            else:
                self._controller.delete_task(item.id)
        self.refresh()

    def _delete_occurrence(self, occurrence: Occurrence) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Cancel scheduled task")
        box.setText(f"Cancel “{occurrence.title}” on {occurrence.date}?")
        day_btn = box.addButton("This day only", QMessageBox.ButtonRole.AcceptRole)
        rest_btn = box.addButton("From this day on", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Keep", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is day_btn:
            self._controller.cancel_occurrence_day(occurrence.schedule_id, occurrence.date)
            self.refresh()
        elif clicked is rest_btn:
            self._controller.cancel_schedule_from(occurrence.schedule_id, occurrence.date)
            self.refresh()

    def _on_toggle_complete(self) -> None:
        items = self._selected_items()
        if not items:
            self._warn_no_selection()
            return
        for item in items:
            if isinstance(item, Occurrence):
                self._controller.toggle_occurrence(item.schedule_id, item.date)
            else:
                self._controller.toggle_completed(item)
        self.refresh()

    def _on_undo(self) -> None:
        if not self._controller.can_undo():
            return
        label = self._controller.undo_label()
        self._controller.undo()
        self.refresh()
        self._status.setText(f"Undid {label}.")

    # ---- export ----------------------------------------------------------
    def _on_export_day(self) -> None:
        """Pick a date, then copy that day's tasks as JSON to the clipboard."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Export tasks for a day")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Copy the selected day's tasks to the clipboard as JSON."))

        picker_row = QHBoxLayout()
        picker_row.addWidget(QLabel("Date:"))
        picker = QDateEdit()
        picker.setCalendarPopup(True)
        picker.setDisplayFormat("ddd, yyyy-MM-dd")
        picker.setDate(self._day.date())
        picker_row.addWidget(picker)
        picker_row.addStretch(1)
        layout.addLayout(picker_row)

        buttons = QDialogButtonBox()
        export_btn = buttons.addButton("Export", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        export_btn.setDefault(True)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        iso_date = picker.date().toString("yyyy-MM-dd")
        payload = self._controller.export_day_json(iso_date)
        count = len(self._controller.tasks_for_day(iso_date))
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(payload)
        self._status.setText(f"Copied {count} task(s) for {iso_date} to the clipboard.")
        QMessageBox.information(
            self,
            "Export complete",
            f"Copied {count} task(s) for {iso_date} to the clipboard as JSON.",
        )

    # ---- Azure integration ----------------------------------------------
    def _on_prs_fetched(self, results: dict, organization: str) -> None:
        """A background sync returned PRs per source; reconcile and refresh."""
        cfg = self._integration_tab.current_config()
        totals = {"created": 0, "skipped": 0, "completed": 0, "reopened": 0}
        for source, prs in results.items():
            summary = self._controller.sync_pull_requests(
                prs, organization, source=source, config=cfg
            )
            for key in totals:
                totals[key] += summary[key]
        self._integration_tab.report_sync_result(totals)
        self._start_poll_timer()  # pick up any interval/enabled change
        self._update_sync_countdown()
        self.refresh()

    def _auto_sync(self) -> None:
        self._integration_tab.trigger_sync(auto=True)

    def _on_integration_cleared(self) -> None:
        """The integration was removed: forget PR links and stop auto-polling."""
        self._controller.clear_pr_links()
        self._poll_timer.stop()
        self._update_sync_countdown()
        self.refresh()

    def _start_poll_timer(self) -> None:
        """(Re)start the auto-poll timer from the saved config, or stop it."""
        cfg = self._integration_tab.current_config()
        if cfg.has_active_sources():
            self._poll_timer.start(max(1, cfg.poll_minutes) * 60_000)
        else:
            self._poll_timer.stop()
        self._update_sync_countdown()

    @staticmethod
    def _format_countdown(remaining_ms: int) -> str:
        """``"Next Azure sync in mm:ss"`` for a millisecond remaining time."""
        total_seconds = max(0, remaining_ms) // 1000
        return f"Next Azure sync in {total_seconds // 60:02d}:{total_seconds % 60:02d}"

    def _update_sync_countdown(self) -> None:
        """Refresh the footer countdown to the next Azure auto-sync.

        Visible only while Azure has active sources and the poll timer is
        running; hidden otherwise so it never lingers when Azure is off.
        """
        active = self._integration_tab.current_config().has_active_sources()
        if active and self._poll_timer.isActive():
            self._sync_countdown.setText(
                self._format_countdown(self._poll_timer.remainingTime())
            )
            self._sync_countdown.show()
        else:
            self._sync_countdown.clear()
            self._sync_countdown.hide()

    # ---- Linear integration ---------------------------------------------
    def _on_linear_issues_fetched(self, issues: list) -> None:
        """A background sync returned Linear issues; reconcile and refresh."""
        cfg = self._linear_tab.current_config()
        summary = self._controller.sync_linear_issues(issues, cfg)
        self._linear_tab.report_sync_result(summary)
        self._start_linear_poll_timer()  # pick up any interval/enabled change
        self.refresh()

    def _auto_sync_linear(self) -> None:
        self._linear_tab.trigger_sync(auto=True)

    def _on_linear_cleared(self) -> None:
        """The integration was removed: forget Linear links and stop polling."""
        self._controller.clear_linear_links()
        self._linear_poll_timer.stop()
        self.refresh()

    def _start_linear_poll_timer(self) -> None:
        """(Re)start the Linear auto-poll timer from the saved config, or stop it."""
        cfg = self._linear_tab.current_config()
        if cfg.has_active_sources():
            self._linear_poll_timer.start(max(1, cfg.poll_minutes) * 60_000)
        else:
            self._linear_poll_timer.stop()

    # ---- theme -----------------------------------------------------------
    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, self._dark)

    def _on_toggle_dark(self, dark: bool) -> None:
        self._dark = dark
        self._dark_btn.setText("☀ Light" if dark else "🌙 Dark")
        theme.save_dark_preference(dark)
        self._apply_theme()
        self.refresh()  # re-tint overdue rows for the new palette

    # ---- reminders -------------------------------------------------------
    def _prompt_reminders(self) -> None:
        """On startup, surface overdue / due-today tasks via a notification."""
        overdue, due_today = self._controller.reminders()
        if not overdue and not due_today:
            return
        parts = []
        if overdue:
            parts.append(f"{len(overdue)} overdue")
        if due_today:
            parts.append(f"{len(due_today)} due today")
        message = " · ".join(parts)
        notifier.notify("Task reminders", message)
        self._status.setText(f"Reminders: {message}")

    def _warn_no_selection(self) -> None:
        QMessageBox.information(self, "No selection", "Please select a task first.")
