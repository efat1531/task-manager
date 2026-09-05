"""Task table widget with internal drag-and-drop row reordering.

Reordering is only meaningful under manual sort, so the owning window
enables/disables dragging via :meth:`set_reorder_enabled`. On a successful
drop the widget computes the new order of task ids and emits
``rows_reordered`` — it does *not* mutate its own cells; the window persists
the new order and rebuilds the table from the database.
"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTableWidget


class TaskTable(QTableWidget):
    """A QTableWidget whose rows can be reordered by dragging.

    Column 0 of each row is expected to carry the row's ``Task`` in
    ``Qt.ItemDataRole.UserRole`` (the window populates it that way).
    """

    #: Emitted with the full list of task ids in their new top-to-bottom order.
    rows_reordered = Signal(list)

    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.set_reorder_enabled(True)

    def set_reorder_enabled(self, enabled: bool) -> None:
        """Allow dragging only in manual-order mode."""
        self.setDragEnabled(enabled)
        self.setAcceptDrops(enabled)
        self.viewport().setAcceptDrops(enabled)

    # ---- drag-and-drop ---------------------------------------------------
    def _row_id(self, row: int) -> int | None:
        item = self.item(row, 0)
        if item is None:
            return None
        task = item.data(Qt.ItemDataRole.UserRole)
        return getattr(task, "id", None)

    def _drop_row(self, event) -> int:
        """Index at which the dragged rows should be inserted."""
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if not index.isValid():
            return self.rowCount()
        rect = self.visualRect(index)
        return index.row() if pos.y() < rect.center().y() else index.row() + 1

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.source() is not self:
            event.ignore()
            return

        drop_row = self._drop_row(event)
        selected = sorted({idx.row() for idx in self.selectionModel().selectedRows()})
        ids: List[int] = [self._row_id(r) for r in range(self.rowCount())]
        if not selected or None in ids:
            event.ignore()
            return

        moving = [ids[r] for r in selected]
        remaining = [tid for r, tid in enumerate(ids) if r not in selected]
        # Removing rows above the drop point shifts the insertion index left.
        insert_at = drop_row - sum(1 for r in selected if r < drop_row)
        new_order = remaining[:insert_at] + moving + remaining[insert_at:]

        if new_order == ids:
            event.ignore()
            return

        event.accept()
        self.rows_reordered.emit(new_order)
