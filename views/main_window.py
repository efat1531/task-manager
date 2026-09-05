"""Main application window: task table with create/edit/delete/complete + sorting."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from controllers.task_controller import TaskController
from models.task import Task
from services import notifier
from views import theme
from views.task_dialog import TaskDialog
from views.task_list import TaskTable

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
        self._apply_theme()
        self.refresh()
        self._prompt_reminders()

    @property
    def _overdue_color(self) -> QColor:
        return theme.OVERDUE_DARK if self._dark else theme.OVERDUE_LIGHT

    # ---- UI construction -------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        # Toolbar row: add / edit / delete / complete + sort selector.
        toolbar = QHBoxLayout()
        self._add_btn = QPushButton("Add")
        self._edit_btn = QPushButton("Edit")
        self._delete_btn = QPushButton("Delete")
        self._complete_btn = QPushButton("Toggle Complete")
        self._undo_btn = QPushButton("Undo")
        self._add_btn.clicked.connect(self._on_add)
        self._edit_btn.clicked.connect(self._on_edit)
        self._delete_btn.clicked.connect(self._on_delete)
        self._complete_btn.clicked.connect(self._on_toggle_complete)
        self._undo_btn.clicked.connect(self._on_undo)

        self._dark_btn = QPushButton("🌙 Dark")
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
        toolbar.addStretch(1)
        toolbar.addWidget(self._dark_btn)
        toolbar.addWidget(QLabel("Sort by:"))
        toolbar.addWidget(self._sort)
        root.addLayout(toolbar)

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

        self.setCentralWidget(central)

    # ---- data <-> view ---------------------------------------------------
    def refresh(self) -> None:
        order_by = self._sort.currentData()
        all_tasks = self._controller.list_tasks(order_by=order_by)

        self._sync_category_filter(all_tasks)

        # Dragging to reorder only makes sense under manual ordering.
        manual = order_by == "sort_order"
        self._table.set_reorder_enabled(manual)

        tasks = [t for t in all_tasks if self._passes_filters(t)]
        self._table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self._populate_row(row, task)

        total = len(all_tasks)
        done = sum(1 for t in all_tasks if t.completed)
        showing = len(tasks)
        suffix = "" if showing == total else f" · showing {showing}"
        self._status.setText(
            f"{total} task(s) · {done} completed · {total - done} open{suffix}"
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

    def _populate_row(self, row: int, task: Task) -> None:
        status = QTableWidgetItem("✓" if task.completed else "")
        status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        cells = [
            status,
            QTableWidgetItem(task.title),
            QTableWidgetItem(task.priority.label),
            QTableWidgetItem(task.deadline or "—"),
            QTableWidgetItem(task.category or "—"),
        ]
        for col, item in enumerate(cells):
            # Stash the Task on the first column for retrieval on select.
            if col == 0:
                item.setData(Qt.ItemDataRole.UserRole, task)
            if task.completed:
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
                item.setForeground(QColor(140, 140, 140))
            elif task.is_overdue:
                item.setForeground(self._overdue_color)
            self._table.setItem(row, col, item)

    def _selected_task(self) -> Task | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ---- actions ---------------------------------------------------------
    def _on_add(self) -> None:
        dialog = TaskDialog(self)
        if dialog.exec() == TaskDialog.DialogCode.Accepted:
            values = dialog.get_values()
            self._controller.create_task(**values)
            self.refresh()

    def _on_edit(self) -> None:
        task = self._selected_task()
        if task is None:
            self._warn_no_selection()
            return
        dialog = TaskDialog(self, task=task)
        if dialog.exec() == TaskDialog.DialogCode.Accepted:
            values = dialog.get_values()
            task.title = values["title"]
            task.description = values["description"]
            task.priority = values["priority"]
            task.deadline = values["deadline"]
            task.category = values["category"]
            self._controller.update_task(task)
            self.refresh()

    def _on_delete(self) -> None:
        task = self._selected_task()
        if task is None:
            self._warn_no_selection()
            return
        confirm = QMessageBox.question(
            self,
            "Delete task",
            f"Delete “{task.title}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._controller.delete_task(task.id)
            self.refresh()

    def _on_toggle_complete(self) -> None:
        task = self._selected_task()
        if task is None:
            self._warn_no_selection()
            return
        self._controller.toggle_completed(task)
        self.refresh()

    def _on_undo(self) -> None:
        if not self._controller.can_undo():
            return
        label = self._controller.undo_label()
        self._controller.undo()
        self.refresh()
        self._status.setText(f"Undid {label}.")

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
