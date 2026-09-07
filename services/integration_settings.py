"""Persist the Azure integration config in QSettings (same store as the theme).

The PAT is intentionally excluded — it lives only in the OS keyring
(see ``services.credentials``).
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

from models.integration import AzureConfig
from models.task import Priority

_ORG = "TaskManager"
_APP = "TaskManager"


def _settings() -> QSettings:
    return QSettings(_ORG, _APP)


def load_config() -> AzureConfig:
    s = _settings()
    return AzureConfig(
        enabled=s.value("azure/enabled", False, type=bool),
        organization=s.value("azure/org", "", type=str),
        project=s.value("azure/project", "", type=str),
        reviewer_id=s.value("azure/reviewer_id", "", type=str),
        poll_minutes=s.value("azure/poll_minutes", 15, type=int),
        create_for_reviewer=s.value("azure/create_for_reviewer", False, type=bool),
        create_for_author=s.value("azure/create_for_author", False, type=bool),
        priority_required=Priority(
            s.value("azure/priority_required", int(Priority.HIGH), type=int)
        ),
        priority_optional=Priority(
            s.value("azure/priority_optional", int(Priority.MEDIUM), type=int)
        ),
        priority_author=Priority(
            s.value("azure/priority_author", int(Priority.MEDIUM), type=int)
        ),
    )


def save_config(config: AzureConfig) -> None:
    s = _settings()
    s.setValue("azure/enabled", config.enabled)
    s.setValue("azure/org", config.organization)
    s.setValue("azure/project", config.project)
    s.setValue("azure/reviewer_id", config.reviewer_id)
    s.setValue("azure/poll_minutes", config.poll_minutes)
    s.setValue("azure/create_for_reviewer", config.create_for_reviewer)
    s.setValue("azure/create_for_author", config.create_for_author)
    s.setValue("azure/priority_required", int(config.priority_required))
    s.setValue("azure/priority_optional", int(config.priority_optional))
    s.setValue("azure/priority_author", int(config.priority_author))


def clear_config() -> None:
    """Remove every stored Azure setting (the PAT is cleared separately)."""
    s = _settings()
    for key in (
        "enabled", "org", "project", "reviewer_id", "poll_minutes",
        "create_for_reviewer", "create_for_author",
        "priority_required", "priority_optional", "priority_author",
    ):
        s.remove(f"azure/{key}")
