"""Desktop notification wrapper.

On Windows this uses native WinRT toast notifications (``windows-toasts``), which
land reliably in the Action Center — unlike plyer's legacy tray *balloon tip*,
which Windows 10/11 frequently suppress. On other platforms (and as a Windows
fallback if the WinRT backend can't load) it uses ``plyer``.

Kept deliberately tolerant: notifications are a convenience, never critical, so any
backend failure is swallowed and reported via the boolean return rather than
raising. The WinRT ``show_toast`` is synchronous, so a real delivery failure is
actually caught here and surfaced as ``False`` (plyer, by contrast, dispatches on a
background thread and can't report failure).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

APP_NAME = "Task Manager"

# --- backend selection -------------------------------------------------------
# Prefer native WinRT toasts on Windows; fall back to plyer elsewhere (or if the
# WinRT backend fails to import/initialise).
_toaster = None          # windows_toasts.WindowsToaster instance (Windows)
_wt = None               # the windows_toasts module (for Toast/ToastDisplayImage)
_plyer = None            # plyer.notification (fallback / other platforms)

if sys.platform == "win32":
    try:  # pragma: no cover - platform dependent
        import windows_toasts as _wt

        _toaster = _wt.WindowsToaster(APP_NAME)
    except Exception:  # import guard / unsupported OS version
        _toaster = None
        _wt = None

if _toaster is None:
    try:
        from plyer import notification as _plyer
    except Exception:  # pragma: no cover - import guard
        _plyer = None


def notifications_available() -> bool:
    return _toaster is not None or _plyer is not None


def _icon_path() -> Optional[str]:
    """Best-effort path to the app icon, or None. Handles the frozen exe."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for name in ("assets/icon.png", "assets/icon.ico"):
        candidate = base / name
        if candidate.exists():
            return str(candidate)
    return None


def notify(title: str, message: str, timeout: int = 10) -> bool:
    """Show a desktop notification. Returns True if it was dispatched."""
    if _toaster is not None and _wt is not None:
        try:  # pragma: no cover - platform dependent
            toast = _wt.Toast()
            toast.text_fields = [title, message]
            icon = _icon_path()
            if icon:
                try:
                    toast.AddImage(
                        _wt.ToastDisplayImage.fromPath(
                            icon, position=_wt.ToastImagePosition.AppLogo
                        )
                    )
                except Exception:
                    pass  # a bad icon must never block delivery
            _toaster.show_toast(toast)  # synchronous — raises on real failure
            return True
        except Exception:
            return False
    if _plyer is not None:
        try:
            _plyer.notify(
                title=title, message=message, app_name=APP_NAME, timeout=timeout
            )
            return True
        except Exception:  # pragma: no cover - platform dependent
            return False
    return False
