"""The "blueprint" panel: a hairline-bordered box with crosshair corner marks.

A presentation-only container from the "Industry" design system — a flat, square
panel framed by a 1px divider-coloured border with a small ``+`` crosshair mark
straddling each of its four corners. The Azure and Linear integration tabs group
their controls into these panels.

Colours are derived from the widget palette (text colour at reduced alpha), so the
frame re-tints automatically when :func:`views.theme.apply_theme` swaps the
light/dark palette — matching the design's ``color-mix(text, transparent)`` corner
and divider colours without parsing rgba strings.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QFrame, QVBoxLayout

# Empty margin reserved on every side so the outer arms of the corner crosshairs
# (which straddle the border) are painted, not clipped by the widget edge.
_BLEED = 7
# Half-length of each crosshair arm — an 11px "+" centred on the corner.
_ARM = 5
# Text-colour alpha for the hairline border (~16%) and the crosshair marks (~55%),
# matching the design tokens (divider vs. muted).
_BORDER_ALPHA = 40
_CROSS_ALPHA = 140


class BlueprintFrame(QFrame):
    """A framed panel with crosshair corner marks; add content to :attr:`body`."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.body = QVBoxLayout(self)
        # _BLEED + the design's 18px/16px inner padding.
        self.body.setContentsMargins(_BLEED + 18, _BLEED + 16, _BLEED + 18, _BLEED + 16)
        self.body.setSpacing(12)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        rect = self.rect().adjusted(_BLEED, _BLEED, -_BLEED - 1, -_BLEED - 1)
        text = self.palette().color(QPalette.ColorRole.WindowText)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        border = QColor(text)
        border.setAlpha(_BORDER_ALPHA)
        painter.setPen(border)
        painter.drawRect(rect)

        cross = QColor(text)
        cross.setAlpha(_CROSS_ALPHA)
        painter.setPen(cross)
        for cx, cy in (
            (rect.left(), rect.top()),
            (rect.right(), rect.top()),
            (rect.left(), rect.bottom()),
            (rect.right(), rect.bottom()),
        ):
            painter.drawLine(cx, cy - _ARM, cx, cy + _ARM)
            painter.drawLine(cx - _ARM, cy, cx + _ARM, cy)
        painter.end()
