"""Persist desktop-notification preferences in QSettings (same store as the
theme and integration configs).

Only non-secret UI preferences live here; the gating *logic* (quiet hours,
per-source toggles) lives on ``NotificationConfig`` in ``models.notification``
so it stays Qt-free and unit-testable.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

from models.notification import NotificationConfig

_ORG = "TaskManager"
_APP = "TaskManager"

# Field name → default, driving both load and clear so the two never drift.
_DEFAULTS = NotificationConfig()
_BOOL_KEYS = (
    "enabled",
    "azure_pr_review",
    "azure_pr_vote",
    "azure_pr_comment",
    "linear_issue",
    "task_due_today",
    "task_overdue",
    "sound",
)
_STR_KEYS = ("quiet_start", "quiet_end")


def _settings() -> QSettings:
    return QSettings(_ORG, _APP)


def load_config() -> NotificationConfig:
    s = _settings()
    values = {
        key: s.value(f"notifications/{key}", getattr(_DEFAULTS, key), type=bool)
        for key in _BOOL_KEYS
    }
    for key in _STR_KEYS:
        values[key] = s.value(
            f"notifications/{key}", getattr(_DEFAULTS, key), type=str
        )
    return NotificationConfig(**values)


def save_config(config: NotificationConfig) -> None:
    s = _settings()
    for key in _BOOL_KEYS + _STR_KEYS:
        s.setValue(f"notifications/{key}", getattr(config, key))


def clear_config() -> None:
    """Remove every stored notification preference (restores defaults on load)."""
    s = _settings()
    for key in _BOOL_KEYS + _STR_KEYS:
        s.remove(f"notifications/{key}")
