"""Secure storage for integration secrets via the OS keyring.

Every call is wrapped so a missing/unavailable keyring backend degrades
gracefully (returns None / no-ops) instead of crashing the app. Secrets are
never written to QSettings or the database.

Two secrets are stored, each under its own keyring *account*:
- ``azure_pat`` — the Azure DevOps Personal Access Token.
- ``linear_api_key`` — the Linear personal API key.
"""
from __future__ import annotations

from typing import Optional

_SERVICE = "TaskManager"
_ACCOUNT = "azure_pat"
_LINEAR_ACCOUNT = "linear_api_key"


def _keyring():
    """Import keyring lazily so the app still runs if it isn't installed."""
    try:
        import keyring
        return keyring
    except Exception:  # pragma: no cover - environment without keyring
        return None


def keyring_available() -> bool:
    return _keyring() is not None


# A misconfigured backend (e.g. a broken native crypto binding) can raise a
# ``BaseException`` such as a Rust ``PanicException`` rather than a plain
# ``Exception``; catch broadly so it degrades to "no backend" instead of
# crashing the app, but never swallow a genuine interrupt/exit request.
def _reraise_interrupts(exc: BaseException) -> None:
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        raise exc


# ---- generic helpers -----------------------------------------------------
def _set_secret(account: str, value: str) -> bool:
    """Store a secret. Returns True on success, False if no backend is available."""
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.set_password(_SERVICE, account, value)
        return True
    except BaseException as exc:  # pragma: no cover - backend errors are best-effort
        _reraise_interrupts(exc)
        return False


def _get_secret(account: str) -> Optional[str]:
    kr = _keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(_SERVICE, account)
    except BaseException as exc:  # pragma: no cover
        _reraise_interrupts(exc)
        return None


def _del_secret(account: str) -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password(_SERVICE, account)
    except BaseException as exc:  # pragma: no cover - already absent / no backend
        _reraise_interrupts(exc)


# ---- Azure PAT -----------------------------------------------------------
def save_pat(pat: str) -> bool:
    return _set_secret(_ACCOUNT, pat)


def load_pat() -> Optional[str]:
    return _get_secret(_ACCOUNT)


def delete_pat() -> None:
    _del_secret(_ACCOUNT)


# ---- Linear API key ------------------------------------------------------
def save_linear_key(key: str) -> bool:
    return _set_secret(_LINEAR_ACCOUNT, key)


def load_linear_key() -> Optional[str]:
    return _get_secret(_LINEAR_ACCOUNT)


def delete_linear_key() -> None:
    _del_secret(_LINEAR_ACCOUNT)
