"""Persist the Azure integration config in QSettings (same store as the theme).

The PAT is intentionally excluded — it lives only in the OS keyring
(see ``services.credentials``).
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

from models.integration import AzureConfig

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
    )


def save_config(config: AzureConfig) -> None:
    s = _settings()
    s.setValue("azure/enabled", config.enabled)
    s.setValue("azure/org", config.organization)
    s.setValue("azure/project", config.project)
    s.setValue("azure/reviewer_id", config.reviewer_id)
    s.setValue("azure/poll_minutes", config.poll_minutes)
