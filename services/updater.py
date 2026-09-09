"""Self-update support: check GitHub Releases, download the new exe, self-replace.

Uses only the standard library (``urllib``) so the app needs no HTTP dependency,
mirroring :mod:`services.azure_client`. The version comparison and release-JSON
parsing are pure functions kept separate from the network so they can be
unit-tested with fixture payloads and no live connection.

The actual install is Windows/frozen only. A running one-file PyInstaller exe
cannot overwrite itself, so :func:`download_and_apply` downloads the new exe to a
temp folder, then hands off to a small ``update.bat``. The helper waits for this
process to exit, then swaps by **renaming** the current exe aside and moving the
new one into its place (Windows allows renaming a running exe even when it refuses
to overwrite it — the one-file bootloader keeps the file briefly locked), and only
relaunches once the new exe is actually in place.
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
    download_url: str     # browser_download_url of the portable TaskManager.exe asset
    size: Optional[int]   # portable asset size in bytes, when the API reported it


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
    assets = payload.get("assets") or []
    url, size = _pick_asset(assets)
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

    It waits for our PID to disappear, then swaps by **renaming** the current exe
    aside (``.old``) and moving the new exe into its place — a running one-file exe
    can be renamed even while the bootloader still holds it locked, whereas
    overwriting it in place fails. Only after a successful swap does it relaunch the
    new exe; if the swap can't happen it restores/keeps the original and relaunches
    that, so the user is never left without a working app. ``%~f0`` is the script's
    own path.
    """
    bat = directory / "update.bat"
    old_exe = f"{target_exe}.old"
    script = f"""@echo off
setlocal enableextensions enabledelayedexpansion
rem Wait for the running app (PID {pid}) to exit before touching the exe.
:waitloop
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >nul
    goto waitloop
)
rem Rename the current exe aside. The one-file bootloader may hold it locked for a
rem moment after the child exits, so retry a bounded number of times.
set /a tries=0
:renameloop
move /Y "{target_exe}" "{old_exe}" >nul 2>&1
if not errorlevel 1 goto place
set /a tries+=1
if !tries! GEQ 15 goto fallback
ping -n 2 127.0.0.1 >nul
goto renameloop
:place
rem Put the new exe where the old one was. If that fails, restore the original.
move /Y "{new_exe}" "{target_exe}" >nul 2>&1
if errorlevel 1 goto restore
start "" "{target_exe}"
rem Best-effort cleanup of the renamed-aside exe once its process releases it.
set /a dtries=0
:delold
del "{old_exe}" >nul 2>&1
if not exist "{old_exe}" goto done
set /a dtries+=1
if !dtries! GEQ 10 goto done
ping -n 2 127.0.0.1 >nul
goto delold
:restore
move /Y "{old_exe}" "{target_exe}" >nul 2>&1
:fallback
start "" "{target_exe}"
:done
del "%~f0"
"""
    bat.write_text(script, encoding="utf-8")
    return bat


def _spawn_detached(bat: Path) -> None:
    """Run ``bat`` in a detached, window-less ``cmd`` that outlives this process."""
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


def download_and_apply(info: UpdateInfo,
                       progress_cb: Optional[Callable[[int], None]] = None,
                       current_exe: Optional[str] = None) -> None:
    """Download the update and launch the helper that installs it.

    Windows/frozen only. Downloads the new portable exe and swaps it in place. On
    success the helper process is spawned and this function returns — the caller
    must then quit the app so the exe is unlocked and the install can proceed.
    Raises :class:`UpdateError` otherwise.
    """
    if not can_self_install():
        raise UpdateError("In-app install is only available in the packaged Windows app.")

    directory = _update_dir()

    # Download the new exe and swap it in place.
    target = Path(current_exe or sys.executable)
    new_exe = directory / "TaskManager-new.exe"
    _download(info.download_url, new_exe, info.size, progress_cb)
    bat = _write_helper_bat(directory, new_exe, target, os.getpid())
    _spawn_detached(bat)
