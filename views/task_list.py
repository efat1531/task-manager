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
from PySide6.QtGui import QDrag
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
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
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
    def startDrag(self, supportedActions) -> None:  # noqa: N802 (Qt override)
        """Run our own drag so the base view never deletes the source rows.

        The default ``QAbstractItemView.startDrag`` calls ``clearOrRemove()`` after
        ``drag.exec()`` returns a ``MoveAction`` — which, because we rebuild the whole
        table from the database in response to ``rows_reordered``, deletes a row from
        the *already rebuilt* table and makes a task vanish until the next refresh
        (setting the drop action to Copy in ``dropEvent`` doesn't reliably suppress
        this on Windows). We must still offer ``MoveAction`` so ``InternalMove``'s
        ``dragMoveEvent`` accepts the drop and our ``dropEvent`` fires; we simply
        ignore the returned action and never remove anything ourselves.
        """
        indexes = self.selectedIndexes()
        if not indexes:
            return
        mime = self.model().mimeData(indexes)
        if mime is None:
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supportedActions, Qt.DropAction.MoveAction)

    def _row_id(self, row: int) -> int | None:
        item = self.item(row, 0)
        if item is None:
            return None
        task = item.data(Qt.ItemDataRole.UserRole)
        return getattr(task, "id", None)

    @staticmethod
    def _drop_index_for_invalid(pos_y: int, row_count: int, first_row_top: int) -> int:
        """Insertion index when the cursor is not over a valid row.

        ``indexAt`` returns an invalid index both above the first row and below
        the last one. Dragging a row all the way to the top lands the cursor
        above row 0's rect, so decide by vertical position: above the first
        row's top (or an empty table) inserts at the top, otherwise at the
        bottom. Without this, a top drop was mis-read as ``rowCount()`` (bottom)
        and silently became a no-op — the "move one row at a time" bug.
        """
        if row_count == 0 or pos_y < first_row_top:
            return 0
        return row_count

    def _drop_row(self, event) -> int:
        """Index at which the dragged rows should be inserted."""
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if not index.isValid():
            first_rect = self.visualRect(self.model().index(0, 0))
            return self._drop_index_for_invalid(
                pos.y(), self.rowCount(), first_rect.top()
            )
        rect = self.visualRect(index)
        return index.row() if pos.y() < rect.center().y() else index.row() + 1

    @staticmethod
    def _reordered_ids(
        row_ids: List[int | None], selected_rows, drop_row: int
    ) -> List[int] | None:
        """New task-id ordering after moving ``selected_rows`` to ``drop_row``.

        Rows without an id (recurring occurrences) never move and are excluded
        from the result; crucially, their mere presence no longer blocks the
        reorder. Returns ``None`` when nothing would change.
        """
        selected = sorted(
            r for r in selected_rows
            if 0 <= r < len(row_ids) and row_ids[r] is not None
        )
        if not selected:
            return None

        moving = [row_ids[r] for r in selected]
        remaining = [
            tid for r, tid in enumerate(row_ids)
            if tid is not None and r not in selected
        ]
        # ``drop_row`` counts every visible row (occurrences included); translate
        # it into an index within the task-only ordering, then shift left by the
        # moved rows that sat above the drop point.
        tasks_before_drop = sum(
            1 for r in range(min(drop_row, len(row_ids))) if row_ids[r] is not None
        )
        insert_at = tasks_before_drop - sum(1 for r in selected if r < drop_row)
        insert_at = max(0, min(insert_at, len(remaining)))
        new_order = remaining[:insert_at] + moving + remaining[insert_at:]

        current = [tid for tid in row_ids if tid is not None]
        return None if new_order == current else new_order

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.source() is not self:
            event.ignore()
            return

        drop_row = self._drop_row(event)
        row_ids: List[int | None] = [self._row_id(r) for r in range(self.rowCount())]
        selected = {idx.row() for idx in self.selectionModel().selectedRows()}
        new_order = self._reordered_ids(row_ids, selected, drop_row)
        if new_order is None:
            event.ignore()
            return

        event.accept()
        self.rows_reordered.emit(new_order)
