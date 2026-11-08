"""Qt wiring test for the GitHub tab (needs pytest-qt, like the title-cell test).

The logic tests can't see signal/slot mistakes -- e.g. connecting the two-argument
``tested(bool, str)`` signal straight to ``QLabel.setText`` raised a TypeError inside
the slot and left the status stuck on "Testing…". This drives the real worker thread
with the network stubbed out.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

pytest.importorskip("pytestqt")

from views import github_tab  # noqa: E402


@pytest.fixture
def tab(qtbot, monkeypatch):
    # Never touch the real keyring or saved settings.
    monkeypatch.setattr(github_tab.credentials, "load_github_token", lambda: None)
    monkeypatch.setattr(
        github_tab.github_settings, "load_config", lambda: github_tab.GitHubConfig()
    )
    widget = github_tab.GitHubIntegrationTab()
    qtbot.addWidget(widget)
    return widget


def _run_test_connection(qtbot, tab, monkeypatch, result):
    monkeypatch.setattr(
        github_tab.GitHubClient, "test_connection", lambda self: result
    )
    tab._token.setText("tok")
    with qtbot.waitSignal(tab.busy_changed, timeout=5000, check_params_cb=lambda b, _: not b):
        tab._test_btn.click()


def test_test_connection_reports_success_text(qtbot, tab, monkeypatch):
    _run_test_connection(qtbot, tab, monkeypatch, (True, "Connected as alice."))
    assert tab._status.text() == "Connected as alice."
    assert tab._test_btn.isEnabled()  # worker cleaned up


def test_test_connection_reports_failure_text(qtbot, tab, monkeypatch):
    _run_test_connection(qtbot, tab, monkeypatch, (False, "authentication failed"))
    assert tab._status.text() == "authentication failed"
