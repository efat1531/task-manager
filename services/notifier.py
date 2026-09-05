"""Desktop notification wrapper around plyer.

Kept deliberately tolerant: notifications are a convenience, never critical,
so any backend failure (missing platform support, no notifier daemon, etc.)
is swallowed and reported via the boolean return rather than raising.
"""
from __future__ import annotations

try:  # plyer is optional at runtime; degrade gracefully if unavailable.
    from plyer import notification as _plyer
except Exception:  # pragma: no cover - import guard
    _plyer = None

APP_NAME = "Task Manager"


def notifications_available() -> bool:
    return _plyer is not None


def notify(title: str, message: str, timeout: int = 10) -> bool:
    """Show a desktop notification. Returns True if it was dispatched."""
    if _plyer is None:
        return False
    try:
        _plyer.notify(title=title, message=message, app_name=APP_NAME, timeout=timeout)
        return True
    except Exception:  # pragma: no cover - platform dependent
        return False
