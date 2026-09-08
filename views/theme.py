"""Light / dark theming via Qt palette + an app-wide stylesheet.

The look is imported from the "Industry" design system: a flat, square
"blueprint" aesthetic — hairline dividers, no rounded corners, a slate-blue
accent, and the Barlow / Barlow Condensed type family (with graceful fallback
to the platform UI font when those aren't installed).

Everything here is presentation only. Colours and component rules are derived
from the design tokens below; :func:`apply_theme` installs the matching palette
and stylesheet on the running :class:`QApplication`.
"""
from __future__ import annotations

import os
import tempfile
from string import Template

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

from views import icons

try:  # QtSvg ships with PySide6 but guard so a trimmed build can't break the UI.
    from PySide6.QtSvg import QSvgRenderer
except Exception:  # pragma: no cover - defensive
    QSvgRenderer = None

# Chevron glyphs used for combo / date / spin drop-down arrows. Styling a
# control's ::drop-down in QSS suppresses Qt's native arrow, so we supply our
# own themed image (Qt QSS can't use data URIs — it must be a real file).
_CHEVRON_DOWN = '<path d="m6 9 6 6 6-6"/>'
_CHEVRON_UP = '<path d="m6 15 6-6 6 6"/>'

_ORG = "TaskManager"
_APP = "TaskManager"
_KEY = "ui/dark_mode"

# Overdue text colour differs per theme so it stays legible on either ground
# (matches --tm-overdue in the design).
OVERDUE_LIGHT = QColor(208, 67, 63)     # #d0433f
OVERDUE_DARK = QColor(255, 125, 125)    # #ff7d7d

# Type stacks — the design's fonts first, then the platform UI font.
_FONT_BODY = '"Barlow", "Segoe UI", "Inter", system-ui, sans-serif'
_FONT_HEADING = '"Barlow Condensed", "Barlow", "Segoe UI Semibold", "Segoe UI", sans-serif'


# --- design tokens ---------------------------------------------------------
# One dict per theme; keys are consumed by both the palette and the stylesheet.
_LIGHT = {
    "bg": "#f2f2f3",
    "surface": "#e9e9ea",
    "text": "#1d1f20",
    "muted": "rgba(29,31,32,0.55)",
    "divider": "rgba(29,31,32,0.16)",
    "hover": "rgba(29,31,32,0.07)",
    "pressed": "rgba(29,31,32,0.14)",
    "accent": "#5980a6",
    "accent_hover": "#597ea3",
    "accent_pressed": "#416180",
    "accent_soft": "#eef6ff",
    "accent_deep": "#2c455d",
    "accent_300": "#b5d9fd",
    "accent_900": "#1d2d3d",
    "on_accent": "#f2f2f3",
    "neutral_200": "#e7e7ea",
    "neutral_300": "#d4d4d7",
    "neutral_600": "#7a7a7d",
    "neutral_700": "#5d5d60",
    "neutral_800": "#424244",
    "overdue": "#d0433f",
    "sel_text": "#ffffff",
    "badge_urgent_text": "#ffffff",
}

_DARK = {
    "bg": "#212124",
    "surface": "#2b2b2f",
    "text": "#e6e6e8",
    "muted": "rgba(230,230,232,0.55)",
    "divider": "rgba(255,255,255,0.15)",
    "hover": "rgba(255,255,255,0.08)",
    "pressed": "rgba(255,255,255,0.15)",
    "accent": "#7ba2c9",
    "accent_hover": "#a8c6e4",
    "accent_pressed": "#cfe1f4",
    "accent_soft": "#233648",
    "accent_deep": "#cfe1f4",
    "accent_300": "#3a5876",
    "accent_900": "#3a5876",
    "on_accent": "#212124",
    "neutral_200": "#3b3b42",
    "neutral_300": "#4a4a52",
    "neutral_600": "#a2a2aa",
    "neutral_700": "#bcbcc3",
    "neutral_800": "#d6d6db",
    "overdue": "#ff7d7d",
    "sel_text": "#17171a",
    "badge_urgent_text": "#ffffff",
}


# Stylesheet template. Placeholders use ``$name`` (string.Template) so the many
# literal ``{ }`` of CSS pass through untouched.
_QSS = Template(r"""
* {
    font-family: $font_body;
}
QWidget {
    background: $bg;
    color: $text;
    font-size: 14px;
}
QToolTip {
    background: $surface;
    color: $text;
    border: 1px solid $divider;
    padding: 4px 7px;
}

/* --- menu bar / menus --- */
/* Ground the menu bar in $bg so it reads as one strip with the corner
   widget (notification bell + version tag), which sits on $bg. */
QMenuBar {
    background: $bg;
    border-bottom: 1px solid $divider;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    color: $neutral_700;
}
QMenuBar::item:selected { background: $hover; color: $text; }
QMenu {
    background: $bg;
    border: 1px solid $divider;
    padding: 4px;
}
QMenu::item { padding: 6px 22px; }
QMenu::item:selected { background: $accent; color: $sel_text; }
QMenu::separator { height: 1px; background: $divider; margin: 4px 6px; }

/* --- tabs --- */
QTabWidget::pane {
    border: 1px solid $divider;
    top: -1px;
}
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab {
    background: transparent;
    color: $neutral_600;
    font-family: $font_heading;
    font-size: 15px;
    padding: 7px 16px;
    border: 0;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
}
QTabBar::tab:hover { color: $text; }
QTabBar::tab:selected {
    color: $accent;
    border-bottom: 2px solid $accent;
}

/* --- buttons --- */
QPushButton {
    background: transparent;
    color: $text;
    font-family: $font_heading;
    font-size: 14px;
    border: 1px solid $divider;
    border-radius: 0;
    padding: 6px 13px;
}
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $pressed; }
QPushButton:disabled { color: $muted; border-color: $divider; }
QPushButton:checked { background: $accent; color: $on_accent; border-color: $accent; }

/* Primary (filled accent) — Add / Save / dialog default action. */
QPushButton#primary, QPushButton:default {
    background: $accent;
    color: $on_accent;
    border: 1px solid $accent;
}
QPushButton#primary:hover, QPushButton:default:hover { background: $accent_hover; }
QPushButton#primary:pressed, QPushButton:default:pressed { background: $accent_pressed; }
QPushButton#primary:disabled, QPushButton:default:disabled {
    background: $surface; color: $muted; border-color: $divider;
}

/* Danger — "Remove integration". */
QPushButton#danger {
    color: $overdue;
    border: 1px solid $divider;
}
QPushButton#danger:hover { background: $hover; border-color: $overdue; }

/* --- inputs --- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QDateEdit, QDateTimeEdit {
    background: $surface;
    color: $text;
    border: 1px solid $divider;
    border-radius: 0;
    padding: 5px 9px;
    min-height: 22px;
    selection-background-color: $accent;
    selection-color: $sel_text;
}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QSpinBox:hover,
QComboBox:hover, QDateEdit:hover, QDateTimeEdit:hover {
    border-color: $neutral_600;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QComboBox:focus, QDateEdit:focus, QDateTimeEdit:focus {
    border-color: $accent;
}
QComboBox::drop-down, QDateEdit::drop-down, QDateTimeEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 20px;
    border-left: 1px solid $divider;
}
QComboBox::down-arrow, QDateEdit::down-arrow, QDateTimeEdit::down-arrow {
    image: url($arrow_down); width: 10px; height: 10px;
}
QSpinBox::up-arrow { image: url($arrow_up); width: 9px; height: 9px; }
QSpinBox::down-arrow { image: url($arrow_down); width: 9px; height: 9px; }
QComboBox QAbstractItemView {
    background: $bg;
    border: 1px solid $divider;
    selection-background-color: $accent;
    selection-color: $sel_text;
    outline: 0;
}
QSpinBox::up-button, QSpinBox::down-button { width: 16px; background: $surface; }

/* --- group boxes as "blueprint" cards --- */
QGroupBox {
    background: transparent;
    border: 1px solid $divider;
    border-radius: 0;
    margin-top: 14px;
    padding: 14px 16px 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: $text;
    font-family: $font_heading;
    font-size: 15px;
}

/* --- table --- */
QTableWidget, QTableView {
    background: $bg;
    alternate-background-color: $bg;
    border: 1px solid $divider;
    gridline-color: transparent;
    outline: 0;
}
QTableView::item { padding: 6px 8px; border: 0; }
QTableView::item:selected { background: $neutral_200; color: $text; }
QHeaderView::section {
    background: $bg;
    color: $muted;
    font-size: 11px;
    font-weight: 600;
    padding: 8px;
    border: 0;
    border-bottom: 1px solid $divider;
}
QTableCornerButton::section { background: $bg; border: 0; border-bottom: 1px solid $divider; }
QTableView::indicator {
    width: 15px; height: 15px;
    border: 1px solid $divider; background: $surface;
}
QTableView::indicator:hover { border-color: $accent; }
QTableView::indicator:checked { background: $accent; border-color: $accent; }
/* Cell-widget wrappers stay transparent so the row selection band shows. */
QWidget#cellWrap { background: transparent; }
QLabel#grip { color: $neutral_600; font-size: 13px; }

/* --- lists (Linear teams / labels) --- */
QListWidget {
    background: $surface;
    border: 1px solid $divider;
    border-radius: 0;
    outline: 0;
}
QListWidget::item { padding: 5px 8px; }
QListWidget::item:selected { background: $accent; color: $sel_text; }

/* --- checkboxes render as round radio-dot toggles (per the design). The
       table's own row checkboxes stay square — see QTableView::indicator. --- */
QCheckBox { spacing: 8px; }
QCheckBox::indicator, QListView::indicator {
    width: 16px; height: 16px;
    image: url($radio_off);
}
QCheckBox::indicator:checked, QListView::indicator:checked {
    image: url($radio_on);
}

/* Exclude-label chips on the Linear tab: bordered pills that highlight when
   ticked (the radio-dot indicator stays as the toggle). */
QCheckBox#blueprintChip {
    border: 1px solid $divider;
    padding: 3px 10px;
    font-size: 11px;
}
QCheckBox#blueprintChip:checked {
    border-color: $accent_300;
    background: $accent_soft;
    color: $accent_deep;
}

/* --- scroll areas / bars --- */
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 0; }
QScrollBar::handle {
    background: $divider;
    min-height: 28px; min-width: 28px;
    border-radius: 0;
}
QScrollBar::handle:hover { background: $neutral_600; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* --- misc --- */
QProgressBar {
    background: $surface;
    border: 1px solid $divider;
    border-radius: 0;
    height: 6px;
}
QProgressBar::chunk { background: $accent; }
QStatusBar { background: $surface; border-top: 1px solid $divider; color: $neutral_700; }
QStatusBar::item { border: 0; }
QLabel { background: transparent; }

/* Footer busy indicator ("⟳ Syncing…") — accent color while a worker runs. */
QLabel#busyIndicator { color: $accent; }

/* Accent status strip on the integration tabs. */
QLabel#statusStrip {
    color: $accent_deep;
    border-left: 2px solid $accent;
    padding: 2px 0 2px 12px;
}

/* Heading inside a blueprint panel (integration tabs). */
QLabel#blueprintTitle {
    font-family: $font_heading;
    font-size: 15px;
    font-weight: 600;
}

/* Small captions / tags. */
QLabel#dayCaption { color: $neutral_600; font-size: 12px; }
QLabel#versionTag { color: $neutral_600; font-size: 11px; padding-right: 12px; }

/* Priority badges in the task table (square pills, per the design). */
QLabel#badge { font-size: 11px; padding: 2px 9px; }
QLabel#badge[prio="urgent"] {
    background: $accent_900; color: $badge_urgent_text; border: 1px solid $accent_900;
}
QLabel#badge[prio="high"] {
    background: $accent_soft; color: $accent_deep; border: 1px solid $accent_300;
}
QLabel#badge[prio="medium"] {
    background: $neutral_200; color: $neutral_800; border: 1px solid transparent;
}
QLabel#badge[prio="low"] {
    background: transparent; color: $neutral_600; border: 1px solid $divider;
}
QLabel#badge[muted="true"] { color: $neutral_600; }

/* --- notification bell + badge --- */
QToolButton#bell {
    border: 0; background: transparent; padding: 2px;
}
QToolButton#bell:hover { background: $hover; }
QLabel#notifBadge {
    background: $accent; color: $on_accent;
    font-size: 9px; font-weight: 700;
    min-width: 14px; min-height: 14px;
    padding: 0 2px; border-radius: 7px;
}

/* --- notification pop-over panel --- */
QFrame#notifPanel { background: $bg; border: 1px solid $accent; }
QWidget#notifPanelHeader { border-bottom: 1px solid $divider; }
QLabel#notifPanelTitle { font-family: $font_heading; font-size: 15px; }
QPushButton#linkButton {
    border: 0; background: transparent; color: $accent;
    font-family: $font_heading; font-size: 12px; padding: 2px 6px;
}
QPushButton#linkButton:hover { color: $accent_hover; }
QFrame#notifItem { border-bottom: 1px solid $divider; }
QFrame#notifItem:hover { background: $hover; }
QLabel#notifItemIcon { border: 1px solid $divider; color: $accent; }
QLabel#notifItemTitle { font-family: $font_heading; font-size: 13px; }
QLabel#notifItemTime { color: $neutral_600; font-size: 10px; }
QLabel#notifItemBody { color: $neutral_700; font-size: 12px; }
QLabel#notifUnreadDot { background: $accent; border-radius: 4px; }

/* --- notifications settings tab --- */
QLabel#pageHeading { font-family: $font_heading; font-size: 21px; }
QLabel#pageSubtitle { color: $muted; font-size: 13px; }
QFrame#card { border: 1px solid $divider; }
QCheckBox#cardHeading { font-family: $font_heading; font-size: 15px; }
QLabel#mutedHint { color: $neutral_600; font-size: 12px; }
QFrame#ruledRow { border-top: 1px solid $divider; }
QLabel#toggleTitle { font-size: 13px; }
QLabel#toggleHint { color: $neutral_600; font-size: 11px; }
QPushButton#segButton { font-family: $font_body; font-size: 13px; padding: 6px 14px; }

/* --- reminder toast --- */
QFrame#toast { background: $surface; border: 1px solid $accent; }
QLabel#toastTitle { font-family: $font_heading; font-size: 14px; }
QLabel#toastBody { color: $neutral_700; font-size: 13px; }
""")


def token(name: str, dark: bool) -> str:
    """Public read of a single design-token value for the given theme."""
    return (_DARK if dark else _LIGHT)[name]


def _arrow_image(svg: str, color: QColor, name: str) -> str:
    """Render a chevron to a temp PNG and return a QSS-friendly url() path."""
    pix = icons.svg_icon(svg, color, 12).pixmap(12, 12)
    path = os.path.join(tempfile.gettempdir(), f"tm_{name}_{color.name().lstrip('#')}.png")
    pix.save(path)
    return path.replace("\\", "/")


def _png_from_svg(markup: str, name: str, size: int = 16) -> str:
    """Rasterise an SVG string to a temp PNG; return a QSS-friendly url() path."""
    if QSvgRenderer is None:
        return ""
    renderer = QSvgRenderer(bytearray(markup, "utf-8"))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    path = os.path.join(tempfile.gettempdir(), f"tm_{name}.png")
    pix.save(path)
    return path.replace("\\", "/")


def _radio_images(tokens: dict) -> tuple[str, str]:
    """(unchecked, checked) radio-dot indicator PNGs for the current theme."""
    accent = QColor(tokens["accent"]).name()
    ring = QColor(tokens["neutral_300"]).name()
    head = "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'>"
    off = (f"{head}<circle cx='12' cy='12' r='9' fill='none' stroke='{ring}' "
           "stroke-width='1.6'/></svg>")
    on = (f"{head}<circle cx='12' cy='12' r='9' fill='none' stroke='{accent}' "
          f"stroke-width='1.6'/><circle cx='12' cy='12' r='4.8' fill='{accent}'/></svg>")
    return (
        _png_from_svg(off, f"radio_off_{ring.lstrip('#')}"),
        _png_from_svg(on, f"radio_on_{accent.lstrip('#')}"),
    )


def _build_qss(tokens: dict) -> str:
    fields = dict(tokens)
    fields["font_body"] = _FONT_BODY
    fields["font_heading"] = _FONT_HEADING
    arrow_color = QColor(tokens["neutral_600"])
    fields["arrow_down"] = _arrow_image(_CHEVRON_DOWN, arrow_color, "chev_down")
    fields["arrow_up"] = _arrow_image(_CHEVRON_UP, arrow_color, "chev_up")
    fields["radio_off"], fields["radio_on"] = _radio_images(tokens)
    return _QSS.substitute(fields)


def _build_palette(tokens: dict) -> QPalette:
    """A palette so Fusion-drawn chrome (dialogs, popups) matches the sheet."""
    def c(key: str) -> QColor:
        return QColor(tokens[key])

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, c("bg"))
    p.setColor(QPalette.ColorRole.WindowText, c("text"))
    p.setColor(QPalette.ColorRole.Base, c("bg"))
    p.setColor(QPalette.ColorRole.AlternateBase, c("surface"))
    p.setColor(QPalette.ColorRole.ToolTipBase, c("surface"))
    p.setColor(QPalette.ColorRole.ToolTipText, c("text"))
    p.setColor(QPalette.ColorRole.Text, c("text"))
    p.setColor(QPalette.ColorRole.Button, c("surface"))
    p.setColor(QPalette.ColorRole.ButtonText, c("text"))
    p.setColor(QPalette.ColorRole.Highlight, c("accent"))
    p.setColor(QPalette.ColorRole.HighlightedText, c("sel_text"))
    p.setColor(QPalette.ColorRole.Link, c("accent"))
    p.setColor(QPalette.ColorRole.PlaceholderText, c("muted"))

    disabled = c("neutral_600")
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                 QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return p


class _NoMnemonicStyle(QProxyStyle):
    """Fusion with the mnemonic accelerator underlines suppressed.

    Wrapping Fusion lets ``Alt+<key>`` menu navigation keep working while the
    tell-tale underline (e.g. the "D" in "Data") is never drawn — matching the
    design, which shows plain menu labels. The app defines no other ``&``
    mnemonics, so this only affects the menu bar.
    """

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802 - Qt override
        if hint == QStyle.StyleHint.SH_UnderlineShortcut:
            return 0
        return super().styleHint(hint, option, widget, returnData)


def apply_theme(app: QApplication, dark: bool) -> None:
    tokens = _DARK if dark else _LIGHT
    app.setStyle(_NoMnemonicStyle("Fusion"))
    app.setPalette(_build_palette(tokens))
    app.setStyleSheet(_build_qss(tokens))


def load_dark_preference() -> bool:
    return QSettings(_ORG, _APP).value(_KEY, False, type=bool)


def save_dark_preference(dark: bool) -> None:
    QSettings(_ORG, _APP).setValue(_KEY, dark)
