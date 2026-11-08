"""Footer sync indicator: a small ring that spins while any integration syncs.

Idle, the ring's accent arc shows how much of the soonest auto-sync interval is left.
Hovering it opens a floating card with each active integration's remaining time (or
"Syncing…"); the card fades out shortly after the mouse leaves both the ring and the
card. Pure presentation: ``MainWindow`` feeds it rows via :meth:`set_state`.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from PySide6.QtCore import (
    QEasingCurve, QPoint, QRectF, Qt, QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QWidget

#: (integration name, text shown on the right, is currently syncing)
Row = Tuple[str, str, bool]

SHOW_MS = 150    # fade/slide in
HIDE_MS = 200    # fade/slide out
GRACE_MS = 250   # mouse-left → fade starts; GRACE + HIDE stays under 500 ms
SLIDE_PX = 8
_SIZE = 22       # ring widget edge, px
_SPIN_MS = 900   # one full revolution while syncing


class _SyncPopup(QFrame):
    """The floating card. Tool-tip window: never takes focus from the app."""

    entered = Signal()
    left = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(
            parent,
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setObjectName("syncPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(14, 10, 14, 12)
        self._grid.setHorizontalSpacing(22)
        self._grid.setVerticalSpacing(6)
        title = QLabel("AUTO-SYNC")
        title.setObjectName("syncPopupTitle")
        self._grid.addWidget(title, 0, 0, 1, 2)
        self._cells: Dict[str, Tuple[QLabel, QLabel]] = {}

    def set_rows(self, rows: Sequence[Row]) -> None:
        if [name for name, _, _ in rows] != list(self._cells):
            for name_label, time_label in self._cells.values():
                name_label.deleteLater()
                time_label.deleteLater()
            self._cells.clear()
            for i, (name, _, _) in enumerate(rows, start=1):
                name_label = QLabel(name)
                time_label = QLabel()
                time_label.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self._grid.addWidget(name_label, i, 0)
                self._grid.addWidget(time_label, i, 1)
                self._cells[name] = (name_label, time_label)
        for name, text, busy in rows:
            _, time_label = self._cells[name]
            time_label.setText(text)
            time_label.setObjectName("syncPopupBusy" if busy else "syncPopupTime")
            time_label.style().unpolish(time_label)
            time_label.style().polish(time_label)
        self.adjustSize()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.left.emit()
        super().leaveEvent(event)


class SyncIndicator(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_SIZE, _SIZE)
        self.setAccessibleName("Sync status")
        self._busy = False
        self._fraction: Optional[float] = None  # remaining share of the next interval
        self._angle = 0.0
        self._rows: Sequence[Row] = ()

        self._spin = QVariantAnimation(self)
        self._spin.setStartValue(0.0)
        self._spin.setEndValue(360.0)
        self._spin.setDuration(_SPIN_MS)
        self._spin.setLoopCount(-1)
        self._spin.setEasingCurve(QEasingCurve.Type.Linear)
        self._spin.valueChanged.connect(self._on_spin)

        self._popup = _SyncPopup(self)
        self._popup.hide()
        self._popup.entered.connect(self._cancel_close)
        self._popup.left.connect(self._schedule_close)
        self._progress = 0.0  # popup visibility: 0 hidden … 1 fully shown
        self._closing = False
        self._base = QPoint()
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.finished.connect(self._on_anim_finished)
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.setInterval(GRACE_MS)
        self._close_timer.timeout.connect(self._begin_hide)

    # ---- state from the window ------------------------------------------
    def set_state(
        self, rows: Sequence[Row], busy: bool, fraction: Optional[float] = None
    ) -> None:
        self._rows = tuple(rows)
        self._fraction = fraction
        self._popup.set_rows(self._rows)
        if self._popup.isVisible():
            self._base = self._target_pos()
            self._place()
        if busy != self._busy:
            self._busy = busy
            if busy:
                self._spin.start()
            else:
                self._spin.stop()
                self._angle = 0.0
        self.update()

    # ---- painting --------------------------------------------------------
    def _on_spin(self, value) -> None:
        self._angle = float(value)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = self.palette().color(QPalette.ColorRole.Highlight)
        track = QColor(self.palette().color(QPalette.ColorRole.WindowText))
        track.setAlpha(60)
        width = 2.5
        rect = QRectF(self.rect()).adjusted(width, width, -width, -width)

        pen = QPen(track, width)
        painter.setPen(pen)
        painter.drawEllipse(rect)

        pen = QPen(accent, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        if self._busy:  # a quarter-ish arc chasing round the ring
            painter.drawArc(rect, int((90 - self._angle) * 16), -110 * 16)
        elif self._fraction is not None:
            frac = max(0.0, min(1.0, self._fraction))
            if frac >= 0.999:
                painter.drawEllipse(rect)
            elif frac > 0:
                painter.drawArc(rect, 90 * 16, int(-frac * 360 * 16))

    # ---- hover popup ------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802
        self._cancel_close()
        self._show_popup()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._schedule_close()
        super().leaveEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._anim.stop()
        self._close_timer.stop()
        self._popup.hide()
        self._progress = 0.0
        super().hideEvent(event)

    def _target_pos(self) -> QPoint:
        """Popup's resting position: above the ring, right edges aligned, on-screen."""
        self._popup.adjustSize()
        pos = self.mapToGlobal(
            QPoint(self.width() - self._popup.width(), -self._popup.height() - 6)
        )
        screen = self.screen()
        if screen is not None:
            area = screen.availableGeometry()
            pos.setX(max(area.left(), min(pos.x(), area.right() - self._popup.width())))
            pos.setY(max(area.top(), pos.y()))
        return pos

    def _place(self) -> None:
        self._popup.setWindowOpacity(self._progress)
        self._popup.move(
            self._base.x(), self._base.y() + round((1 - self._progress) * SLIDE_PX)
        )

    def _show_popup(self) -> None:
        if not self._rows:
            return
        self._closing = False
        self._base = self._target_pos()
        if not self._popup.isVisible():
            self._progress = 0.0
            self._place()
            self._popup.show()
        self._animate_to(1.0, SHOW_MS)

    def _schedule_close(self) -> None:
        if self._popup.isVisible():
            self._close_timer.start()

    def _cancel_close(self) -> None:
        self._close_timer.stop()
        if self._closing:  # fading out: turn round and fade back in
            self._closing = False
            self._animate_to(1.0, SHOW_MS)

    def _begin_hide(self) -> None:
        self._closing = True
        self._animate_to(0.0, HIDE_MS)

    def _animate_to(self, target: float, full_ms: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.setDuration(int(abs(target - self._progress) * full_ms))
        self._anim.start()

    def _on_anim(self, value) -> None:
        self._progress = float(value)
        self._place()

    def _on_anim_finished(self) -> None:
        if self._closing and self._progress <= 0.001:
            self._popup.hide()
            self._closing = False
