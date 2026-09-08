"""Small helper to render the design's stroked line icons as themed QIcons.

Presentation only. Icons are 24×24 line drawings stroked with ``currentColor``;
:func:`svg_icon` bakes in a concrete colour so callers can re-tint per theme.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

try:  # QtSvg ships with PySide6 but guard so a trimmed build can't break the UI.
    from PySide6.QtSvg import QSvgRenderer
except Exception:  # pragma: no cover - defensive
    QSvgRenderer = None

# 24×24 icon path data (from the design system).
PLUS = '<path d="M12 5v14M5 12h14"/>'
UNDO = '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-1"/>'
SEARCH = '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>'
BELL = ('<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
        '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>')
REMINDER = '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M12 2h0M5 3 2 6M22 6l-3-3"/>'
SYNC = ('<path d="M21 12a9 9 0 0 1-9 9 9 9 0 0 1-6.7-3M3 12a9 9 0 0 1 9-9 9 9 0 0 1 6.7 3"/>'
        '<path d="M21 3v5h-5M3 21v-5h5"/>')
PR = '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'
SCHEDULE = ('<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4"/>'
            '<path d="M21 13v1a4 4 0 0 1-4 4H3"/>')


def svg_icon(paths: str, color: QColor, size: int = 16) -> QIcon:
    """Render a stroked 24×24 line icon to a themed :class:`QIcon`."""
    if QSvgRenderer is None:
        return QIcon()
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' "
        "viewBox='0 0 24 24' fill='none' stroke='{c}' stroke-width='1.6' "
        "stroke-linecap='round' stroke-linejoin='round'>{p}</svg>"
    ).format(c=color.name(), p=paths)
    renderer = QSvgRenderer(bytearray(svg, "utf-8"))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)
