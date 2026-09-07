"""Self-update support: check GitHub Releases, download the new exe, self-replace.

Uses only the standard library (``urllib``) so the app needs no HTTP dependency,
mirroring :mod:`services.azure_client`. The version comparison and release-JSON
parsing are pure functions kept separate from the network so they can be
unit-tested with fixture payloads and no live connection.

The actual install is Windows/frozen only: a running one-file PyInstaller exe
cannot overwrite itself, so :func:`download_and_apply` downloads the new exe to a
temp folder, then hands off to a small ``update.bat`` that waits for this process
to exit, swaps the exe in place, and relaunches it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from version import APP_VERSION, GITHUB_REPO

_ASSET_NAME = "TaskManager.exe"
_TIMEOUT = 20  # seconds; keeps a hung network from blocking the worker forever
_USER_AGENT = f"TaskManager/{APP_VERSION} (+https://github.com/{GITHUB_REPO})"


class UpdateError(Exception):
    """Any failure checking for or applying an update."""


@dataclass(frozen=True)
class UpdateInfo:
    """A release that is newer than the running app."""

    version: str          # e.g. "1.3.0" (leading "v" stripped)
    notes: str            # the release body (Markdown)
    download_url: str     # browser_download_url of the TaskManager.exe asset
    size: Optional[int]   # asset size in bytes, when the API reported it


# ---- version comparison (pure) ------------------------------------------------
def parse_version(raw: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple of integers.

    Tolerant of a leading ``v`` and of pre-release/build suffixes (``1.3.0-rc1``
    -> ``(1, 3, 0)``): only the leading dotted-integer run is considered. A
    string with no leading number parses to ``(0,)`` so it never looks newer.
    """
    cleaned = raw.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits == "":
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    """True when ``latest`` is a strictly greater version than ``current``."""
    return parse_version(latest) > parse_version(current)


# ---- release JSON parsing (pure) ----------------------------------------------
def _pick_asset(assets: list[dict]) -> tuple[Optional[str], Optional[int]]:
    """Return ``(download_url, size)`` for the ``TaskManager.exe`` release asset.

    Falls back to the first asset whose name ends in ``.exe`` so a renamed build
    still updates. Returns ``(None, None)`` when no exe asset is present.
    """
    for asset in assets:
        if asset.get("name") == _ASSET_NAME:
            return asset.get("browser_download_url"), asset.get("size")
    for asset in assets:
        name = asset.get("name") or ""
        if name.lower().endswith(".exe"):
            return asset.get("browser_download_url"), asset.get("size")
    return None, None


def parse_release(payload: dict, current_version: str) -> Optional[UpdateInfo]:
    """Turn a GitHub ``releases/latest`` payload into :class:`UpdateInfo`.

    Returns ``None`` when the release is a draft, not newer than
    ``current_version``, or has no downloadable exe asset. Pure: no network.
    """
    if payload.get("draft"):
        return None
    tag = payload.get("tag_name") or payload.get("name") or ""
    if not tag or not is_newer(tag, current_version):
        return None
    url, size = _pick_asset(payload.get("assets") or [])
    if not url:
        return None
    return UpdateInfo(
        version=tag.lstrip("vV"),
        notes=payload.get("body") or "",
        download_url=url,
        size=size,
    )


# ---- network ------------------------------------------------------------------
def _api_url() -> str:
    return f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def check_for_update(current_version: str = APP_VERSION) -> Optional[UpdateInfo]:
    """Query GitHub for the latest release and return it only when it's newer.

    Any network, HTTP, or parse failure is swallowed and returns ``None`` — a
    failed update check must never disrupt startup or the manual-check flow
    (which distinguishes "up to date" from "check failed" via
    :func:`check_for_update_strict`).
    """
    try:
        return check_for_update_strict(current_version)
    except UpdateError:
        return None


def check_for_update_strict(current_version: str = APP_VERSION) -> Optional[UpdateInfo]:
    """Like :func:`check_for_update` but raises :class:`UpdateError` on failure.

    Lets the manual "Check for updates" flow tell the user a check failed,
    instead of silently claiming they are up to date.
    """
    request = urllib.request.Request(
        _api_url(),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,  # GitHub rejects requests without one
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"GitHub returned HTTP {exc.code} checking for updates.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"Could not reach GitHub: {exc}") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub returned an unreadable response.") from exc
    return parse_release(payload, current_version)


# ---- install ------------------------------------------------------------------
def can_self_install() -> bool:
    """True only when a running frozen Windows exe can replace itself in place."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def _update_dir() -> Path:
    """Writable scratch dir for the downloaded exe and helper script."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    directory = Path(base) / "TaskManager" / "update"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _download(url: str, dest: Path, expected_size: Optional[int],
              progress_cb: Optional[Callable[[int], None]]) -> None:
    """Stream ``url`` to ``dest``, reporting integer percent via ``progress_cb``."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as resp:
            total = expected_size or int(resp.headers.get("Content-Length") or 0)
            read = 0
            last_pct = -1
            with open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    read += len(chunk)
                    if progress_cb and total:
                        pct = min(100, int(read * 100 / total))
                        if pct != last_pct:
                            last_pct = pct
                            progress_cb(pct)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"Download failed: {exc}") from exc

    if expected_size and dest.stat().st_size != expected_size:
        raise UpdateError("Downloaded file is incomplete; please try again.")


def _write_helper_bat(directory: Path, new_exe: Path, target_exe: Path,
                      pid: int) -> Path:
    """Write the batch script that swaps the exe once this process exits.

    It waits for our PID to disappear, replaces the old exe, relaunches it, and
    finally deletes itself. ``%~f0`` is the script's own path.
    """
    bat = directory / "update.bat"
    script = f"""@echo off
setlocal
rem Wait for the running app (PID {pid}) to exit so the exe is unlocked.
:waitloop
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >nul
    goto waitloop
)
move /Y "{new_exe}" "{target_exe}" >nul
start "" "{target_exe}"
del "%~f0"
"""
    bat.write_text(script, encoding="utf-8")
    return bat


def download_and_apply(info: UpdateInfo,
                       progress_cb: Optional[Callable[[int], None]] = None,
                       current_exe: Optional[str] = None) -> None:
    """Download the new exe and launch the helper that replaces this one.

    Windows/frozen only. On success the helper process is spawned detached and
    this function returns — the caller must then quit the app so the exe is
    unlocked and the swap can proceed. Raises :class:`UpdateError` otherwise.
    """
    if not can_self_install():
        raise UpdateError("In-app install is only available in the packaged Windows app.")

    target = Path(current_exe or sys.executable)
    directory = _update_dir()
    new_exe = directory / "TaskManager-new.exe"

    _download(info.download_url, new_exe, info.size, progress_cb)

    bat = _write_helper_bat(directory, new_exe, target, os.getpid())

    # DETACHED_PROCESS | CREATE_NO_WINDOW: outlive us with no console flash.
    creation_flags = 0x00000008 | 0x08000000
    try:
        subprocess.Popen(
            ["cmd", "/c", str(bat)],
            creationflags=creation_flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError(f"Could not start the updater: {exc}") from exc
