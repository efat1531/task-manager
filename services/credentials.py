"""Secure storage for the Azure Personal Access Token via the OS keyring.

Every call is wrapped so a missing/unavailable keyring backend degrades
gracefully (returns None / no-ops) instead of crashing the app. The token is
never written to QSettings or the database.
"""
from __future__ import annotations

from typing import Optional

_SERVICE = "TaskManager"
_ACCOUNT = "azure_pat"


def _keyring():
    """Import keyring lazily so the app still runs if it isn't installed."""
    try:
        import keyring
        return keyring
    except Exception:  # pragma: no cover - environment without keyring
        return None


def keyring_available() -> bool:
    return _keyring() is not None


def save_pat(pat: str) -> bool:
    """Store the PAT. Returns True on success, False if no backend is available."""
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.set_password(_SERVICE, _ACCOUNT, pat)
        return True
    except Exception:  # pragma: no cover - backend errors are best-effort
        return False


def load_pat() -> Optional[str]:
    kr = _keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(_SERVICE, _ACCOUNT)
    except Exception:  # pragma: no cover
        return None


def delete_pat() -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password(_SERVICE, _ACCOUNT)
    except Exception:  # pragma: no cover - already absent / no backend
        pass
