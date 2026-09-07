"""Auto-updater pure logic: version compare, asset picking, release parsing.

No network and no Qt — :func:`check_for_update_strict` is exercised by
monkeypatching the single ``urllib.request.urlopen`` call with a fixture payload.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import updater  # noqa: E402
from services.updater import (  # noqa: E402
    UpdateError,
    _pick_asset,
    is_newer,
    parse_release,
    parse_version,
)


# ---- parse_version / is_newer -------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.2.0", (1, 2, 0)),
        ("v1.2.0", (1, 2, 0)),
        ("V1.3", (1, 3)),
        ("1.10.0", (1, 10, 0)),
        ("1.3.0-rc1", (1, 3, 0)),
        ("not-a-version", (0,)),
    ],
)
def test_parse_version(raw, expected):
    assert parse_version(raw) == expected


@pytest.mark.parametrize(
    "latest,current,newer",
    [
        ("1.3.0", "1.2.0", True),
        ("v1.3.0", "1.2.0", True),
        ("1.2.0", "1.2.0", False),
        ("1.2.0", "1.3.0", False),
        # Numeric compare, not lexicographic: 1.10.0 > 1.2.0.
        ("1.10.0", "1.2.0", True),
        ("1.2.0", "1.10.0", False),
    ],
)
def test_is_newer(latest, current, newer):
    assert is_newer(latest, current) is newer


# ---- _pick_asset --------------------------------------------------------------
def test_pick_asset_prefers_exact_name():
    assets = [
        {"name": "notes.txt", "browser_download_url": "u1", "size": 1},
        {"name": "TaskManager.exe", "browser_download_url": "u2", "size": 2},
    ]
    assert _pick_asset(assets) == ("u2", 2)


def test_pick_asset_falls_back_to_any_exe():
    assets = [{"name": "TaskManager-1.3.0.exe", "browser_download_url": "u3", "size": 3}]
    assert _pick_asset(assets) == ("u3", 3)


def test_pick_asset_none_when_no_exe():
    assert _pick_asset([{"name": "readme.md", "browser_download_url": "u"}]) == (None, None)


# ---- parse_release ------------------------------------------------------------
def _release(tag: str) -> dict:
    return {
        "tag_name": tag,
        "body": "## Changes\n- something",
        "draft": False,
        "assets": [
            {"name": "TaskManager.exe", "browser_download_url": "https://x/exe", "size": 42},
        ],
    }


def test_parse_release_returns_info_when_newer():
    info = parse_release(_release("v1.3.0"), "1.2.0")
    assert info is not None
    assert info.version == "1.3.0"
    assert info.download_url == "https://x/exe"
    assert info.size == 42
    assert "Changes" in info.notes


def test_parse_release_none_when_not_newer():
    assert parse_release(_release("v1.2.0"), "1.2.0") is None


def test_parse_release_none_for_draft():
    payload = _release("v9.9.9")
    payload["draft"] = True
    assert parse_release(payload, "1.2.0") is None


def test_parse_release_none_without_exe_asset():
    payload = _release("v1.3.0")
    payload["assets"] = [{"name": "notes.txt", "browser_download_url": "u"}]
    assert parse_release(payload, "1.2.0") is None


# ---- check_for_update_strict (monkeypatched network) --------------------------
class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_check_for_update_strict_found(monkeypatch):
    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse(_release("v1.3.0")),
    )
    info = updater.check_for_update_strict("1.2.0")
    assert info is not None and info.version == "1.3.0"


def test_check_for_update_strict_up_to_date(monkeypatch):
    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse(_release("v1.2.0")),
    )
    assert updater.check_for_update_strict("1.2.0") is None


def test_check_for_update_strict_raises_on_network_error(monkeypatch):
    def boom(*a, **k):
        raise updater.urllib.error.URLError("no network")

    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    with pytest.raises(UpdateError):
        updater.check_for_update_strict("1.2.0")


def test_check_for_update_swallows_errors(monkeypatch):
    def boom(*a, **k):
        raise updater.urllib.error.URLError("no network")

    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    # The silent variant must never raise, even when the network is down.
    assert updater.check_for_update("1.2.0") is None
