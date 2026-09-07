"""Persist the Linear integration config in QSettings (same store as the theme).

The API key is intentionally excluded — it lives only in the OS keyring
(see ``services.credentials``). ``status_priorities`` is a list of dicts, so it
is stored as a JSON string; the plain lists use QSettings' native list support.
"""
from __future__ import annotations

import json

from PySide6.QtCore import QSettings

from models.linear import LinearConfig

_ORG = "TaskManager"
_APP = "TaskManager"


def _settings() -> QSettings:
    return QSettings(_ORG, _APP)


def _as_list(value) -> list:
    """QSettings returns a bare string for a single-element list; normalise."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return list(value)


def load_config() -> LinearConfig:
    s = _settings()
    raw = s.value("linear/status_priorities", "", type=str)
    try:
        status_priorities = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        status_priorities = []
    return LinearConfig(
        enabled=s.value("linear/enabled", False, type=bool),
        team_ids=_as_list(s.value("linear/team_ids", [])),
        poll_minutes=s.value("linear/poll_minutes", 15, type=int),
        status_priorities=status_priorities,
        exclude_labels=_as_list(s.value("linear/exclude_labels", [])),
    )


def save_config(config: LinearConfig) -> None:
    s = _settings()
    s.setValue("linear/enabled", config.enabled)
    s.setValue("linear/team_ids", list(config.team_ids))
    s.setValue("linear/poll_minutes", config.poll_minutes)
    s.setValue("linear/status_priorities", json.dumps(config.status_priorities))
    s.setValue("linear/exclude_labels", list(config.exclude_labels))


def clear_config() -> None:
    """Remove every stored Linear setting (the API key is cleared separately)."""
    s = _settings()
    for key in (
        "enabled", "team_ids", "poll_minutes",
        "status_priorities", "exclude_labels",
    ):
        s.remove(f"linear/{key}")
