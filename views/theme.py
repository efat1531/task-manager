"""Light / dark theme handling via Qt palettes, persisted with QSettings."""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

_ORG = "TaskManager"
_APP = "TaskManager"
_KEY = "ui/dark_mode"

# Overdue text colour differs per theme so it stays legible on either ground.
OVERDUE_LIGHT = QColor(200, 60, 60)
OVERDUE_DARK = QColor(255, 120, 120)


def _dark_palette() -> QPalette:
    p = QPalette()
    window = QColor(45, 45, 48)
    base = QColor(30, 30, 32)
    text = QColor(220, 220, 220)
    highlight = QColor(38, 110, 190)
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, window)
    p.setColor(QPalette.ColorRole.ToolTipBase, window)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, window)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.Highlight, highlight)
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    disabled = QColor(120, 120, 120)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                 QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return p


def apply_theme(app: QApplication, dark: bool) -> None:
    if dark:
        app.setStyle("Fusion")
        app.setPalette(_dark_palette())
    else:
        app.setStyle("Fusion")
        app.setPalette(QApplication.style().standardPalette())


def load_dark_preference() -> bool:
    return QSettings(_ORG, _APP).value(_KEY, False, type=bool)


def save_dark_preference(dark: bool) -> None:
    QSettings(_ORG, _APP).setValue(_KEY, dark)
