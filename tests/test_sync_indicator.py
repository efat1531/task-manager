"""Qt test for the footer sync ring + hover card (needs pytest-qt)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

pytest.importorskip("pytestqt")

from views import sync_indicator  # noqa: E402
from views.sync_indicator import SyncIndicator  # noqa: E402

ROWS = [("Azure", "13:29", False), ("GitHub", "Syncing…", True)]


@pytest.fixture
def ring(qtbot):
    widget = SyncIndicator()
    qtbot.addWidget(widget)
    # Keep the card away from (0, 0): the offscreen platform's cursor sits there and
    # would count as "mouse on the card", cancelling every close.
    widget.move(500, 500)
    widget.show()
    widget.set_state(ROWS, busy=True, fraction=0.5)
    return widget


def test_close_budget_is_under_500ms():
    assert sync_indicator.GRACE_MS + sync_indicator.HIDE_MS <= 500


def test_hover_opens_card_and_leaving_closes_it_within_500ms(qtbot, ring):
    ring._show_popup()
    qtbot.waitUntil(lambda: ring._popup.isVisible() and ring._progress > 0.99, timeout=2000)
    # (windowOpacity itself isn't testable: the offscreen platform can't set it.)

    start = time.monotonic()
    ring._schedule_close()  # what leaveEvent does
    qtbot.waitUntil(lambda: not ring._popup.isVisible(), timeout=2000)
    assert time.monotonic() - start < 0.6  # 500 ms budget + scheduling slack


def test_returning_to_card_cancels_the_close(qtbot, ring):
    ring._show_popup()
    qtbot.waitUntil(lambda: ring._progress > 0.99, timeout=2000)
    ring._schedule_close()
    ring._cancel_close()  # mouse moved onto the card
    qtbot.wait(600)
    assert ring._popup.isVisible() and ring._progress > 0.99


def test_card_reflects_rows_and_updates_live(qtbot, ring):
    ring.set_state([("Azure", "00:42", False)], busy=False, fraction=0.1)
    texts = {n: t.text() for n, (_, t) in ring._popup._cells.items()}
    assert texts == {"Azure": "00:42"}


def test_no_rows_means_no_card(qtbot):
    widget = SyncIndicator()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_state([], busy=False)
    widget._show_popup()
    assert not widget._popup.isVisible()


def test_spin_runs_only_while_busy(qtbot, ring):
    assert ring._spin.state() == ring._spin.State.Running
    ring.set_state(ROWS, busy=False, fraction=0.5)
    assert ring._spin.state() == ring._spin.State.Stopped
