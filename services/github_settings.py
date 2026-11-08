"""Persist the GitHub integration config in QSettings (same store as the theme).

The token is intentionally excluded — it lives only in the OS keyring
(see ``services.credentials``).
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

from models.github import GitHubConfig
from models.task import Priority

_ORG = "TaskManager"
_APP = "TaskManager"

_KEYS = (
    "enabled", "owner", "poll_minutes",
    "create_for_reviewer", "create_for_author",
    "priority_review", "priority_author",
)


def _settings() -> QSettings:
    return QSettings(_ORG, _APP)


def _priority(s: QSettings, key: str, default: Priority) -> Priority:
    """Read a stored priority, tolerating a corrupt/out-of-range value."""
    try:
        return Priority(s.value(key, int(default), type=int))
    except ValueError:
        return default


def load_config() -> GitHubConfig:
    s = _settings()
    d = GitHubConfig()
    return GitHubConfig(
        enabled=s.value("github/enabled", d.enabled, type=bool),
        owner=s.value("github/owner", d.owner, type=str),
        poll_minutes=s.value("github/poll_minutes", d.poll_minutes, type=int),
        create_for_reviewer=s.value(
            "github/create_for_reviewer", d.create_for_reviewer, type=bool
        ),
        create_for_author=s.value(
            "github/create_for_author", d.create_for_author, type=bool
        ),
        priority_review=_priority(s, "github/priority_review", d.priority_review),
        priority_author=_priority(s, "github/priority_author", d.priority_author),
    )


def save_config(config: GitHubConfig) -> None:
    s = _settings()
    s.setValue("github/enabled", config.enabled)
    s.setValue("github/owner", config.owner)
    s.setValue("github/poll_minutes", config.poll_minutes)
    s.setValue("github/create_for_reviewer", config.create_for_reviewer)
    s.setValue("github/create_for_author", config.create_for_author)
    s.setValue("github/priority_review", int(config.priority_review))
    s.setValue("github/priority_author", int(config.priority_author))


def clear_config() -> None:
    """Remove every stored GitHub setting (the token is cleared separately)."""
    s = _settings()
    for key in _KEYS:
        s.remove(f"github/{key}")
