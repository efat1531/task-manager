"""Notification feed + gating logic (in-memory DB, no Qt/network)."""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controllers.task_controller import TaskController  # noqa: E402
from models.integration import PullRequest  # noqa: E402
from models.linear import LinearConfig, LinearIssue  # noqa: E402
from models.notification import (  # noqa: E402
    SOURCE_AZURE_COMMENT,
    SOURCE_AZURE_REVIEW,
    SOURCE_LINEAR,
    SOURCE_TASK_DUE,
    SOURCE_TASK_OVERDUE,
    Notification,
    NotificationConfig,
    relative_time,
)
from models.task_repository import TaskRepository  # noqa: E402

ORG = "myorg"


@pytest.fixture()
def repo() -> TaskRepository:
    r = TaskRepository(":memory:")
    yield r
    r.close()


@pytest.fixture()
def controller(repo) -> TaskController:
    return TaskController(repo)


def _iso(offset_days: int) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


def _linear_config() -> LinearConfig:
    return LinearConfig(
        enabled=True, team_ids=["t1"],
        status_priorities=[{"id": "s1", "name": "In Progress"}],
    )


def _issue(iid: str, title: str = "Do thing") -> LinearIssue:
    return LinearIssue(
        id=iid, identifier="ENG-1", title=title, url="https://linear.app/i/x",
        linear_priority=2, state_id="s1", state_name="In Progress",
        state_type="started", label_names=[],
    )


# ---- repository CRUD ------------------------------------------------------
def test_add_and_list_newest_first(repo):
    repo.add_notification(Notification(kind="reminder", title="First"))
    repo.add_notification(Notification(kind="pr", title="Second"))
    items = repo.list_notifications()
    assert [n.title for n in items] == ["Second", "First"]


def test_unread_count_and_mark_all_read(repo):
    repo.add_notification(Notification(kind="reminder", title="A"))
    repo.add_notification(Notification(kind="reminder", title="B"))
    assert repo.count_unread_notifications() == 2
    repo.mark_all_notifications_read()
    assert repo.count_unread_notifications() == 0
    # The rows survive, only their read flag flips.
    assert all(n.read for n in repo.list_notifications())


def test_dedup_key_skips_repeats(repo):
    first = repo.add_notification(Notification(kind="pr", title="X", dedup_key="k1"))
    dup = repo.add_notification(Notification(kind="pr", title="X again", dedup_key="k1"))
    assert first is not None and first.id is not None
    assert dup is None
    assert len(repo.list_notifications()) == 1


def test_null_dedup_keys_never_collide(repo):
    assert repo.add_notification(Notification(kind="pr", title="A")) is not None
    assert repo.add_notification(Notification(kind="pr", title="B")) is not None
    assert len(repo.list_notifications()) == 2


def test_reset_clears_notifications(repo):
    repo.add_notification(Notification(kind="pr", title="A"))
    repo.reset()
    assert repo.list_notifications() == []


# ---- controller event buffering ------------------------------------------
def test_record_buffers_event_only_on_real_insert(controller):
    controller.record_notification(
        kind="pr", title="A", source=SOURCE_AZURE_REVIEW, dedup_key="k")
    controller.record_notification(
        kind="pr", title="A", source=SOURCE_AZURE_REVIEW, dedup_key="k")  # deduped
    events = controller.drain_notification_events()
    assert len(events) == 1
    assert events[0].source == SOURCE_AZURE_REVIEW
    # Draining clears the buffer.
    assert controller.drain_notification_events() == []


def test_record_without_source_buffers_nothing(controller):
    controller.record_notification(kind="sync", title="Sync done")  # no source
    assert controller.drain_notification_events() == []
    # ...but it is still persisted to the feed.
    assert controller.unread_notification_count() == 1


# ---- reminders: de-dup + daily rollover ----------------------------------
def test_record_reminders_covers_overdue_and_due_today(controller):
    controller.create_task("overdue", deadline=_iso(-1))
    controller.create_task("today", deadline=_iso(0))
    controller.create_task("future", deadline=_iso(3))
    events = controller.record_reminders(today=_iso(0))
    sources = sorted(e.source for e in events)
    assert sources == [SOURCE_TASK_DUE, SOURCE_TASK_OVERDUE]


def test_record_reminders_skips_completed(controller):
    task = controller.create_task("done", deadline=_iso(-1))
    controller.toggle_completed(task)
    assert controller.record_reminders(today=_iso(0)) == []


def test_record_reminders_is_idempotent_within_a_day(controller):
    controller.create_task("overdue", deadline=_iso(-1))
    assert len(controller.record_reminders(today="2026-09-09")) == 1
    assert controller.record_reminders(today="2026-09-09") == []


def test_record_reminders_refires_next_day(controller):
    controller.create_task("overdue", deadline=_iso(-1))
    controller.record_reminders(today="2026-09-09")
    assert len(controller.record_reminders(today="2026-09-10")) == 1


# ---- sync emits events; summary dicts unchanged --------------------------
def test_review_pr_creation_emits_event_once(controller):
    pr = PullRequest(pr_id=1, title="Feature", is_required=True)
    summary = controller.sync_pull_requests([pr], ORG, source="review")
    assert summary == {"created": 1, "skipped": 0, "completed": 0, "reopened": 0}
    events = controller.drain_notification_events()
    assert [e.source for e in events] == [SOURCE_AZURE_REVIEW]
    # Re-syncing the same PR emits nothing new.
    controller.sync_pull_requests([pr], ORG, source="review")
    assert controller.drain_notification_events() == []


def test_authored_pr_comment_emits_event(controller):
    pr = PullRequest(pr_id=2, title="Mine", is_author=True, unresolved_comment_count=0)
    controller.sync_pull_requests([pr], ORG, source="author")
    controller.drain_notification_events()  # discard the initial reconcile
    pr.unresolved_comment_count = 3  # a new comment thread appears
    controller.sync_pull_requests([pr], ORG, source="author")
    events = controller.drain_notification_events()
    assert [e.source for e in events] == [SOURCE_AZURE_COMMENT]


def test_linear_issue_creation_emits_event(controller):
    summary = controller.sync_linear_issues([_issue("i1")], _linear_config())
    assert summary == {"created": 1, "skipped": 0, "completed": 0, "reopened": 0}
    assert [e.source for e in controller.drain_notification_events()] == [SOURCE_LINEAR]


# ---- NotificationConfig gating -------------------------------------------
def test_source_enabled_maps_to_field():
    cfg = NotificationConfig(task_due_today=False)
    assert cfg.source_enabled(SOURCE_TASK_OVERDUE) is True
    assert cfg.source_enabled(SOURCE_TASK_DUE) is False
    assert cfg.source_enabled("nonexistent") is False


def test_quiet_hours_wraparound():
    cfg = NotificationConfig(quiet_start="22:00", quiet_end="07:00")
    assert cfg.in_quiet_hours(datetime(2026, 9, 9, 23, 0)) is True   # after start
    assert cfg.in_quiet_hours(datetime(2026, 9, 9, 3, 0)) is True    # before end
    assert cfg.in_quiet_hours(datetime(2026, 9, 9, 8, 0)) is False   # daytime


def test_quiet_hours_same_day_window():
    cfg = NotificationConfig(quiet_start="09:00", quiet_end="17:00")
    assert cfg.in_quiet_hours(datetime(2026, 9, 9, 12, 0)) is True
    assert cfg.in_quiet_hours(datetime(2026, 9, 9, 20, 0)) is False


def test_quiet_hours_disabled_when_blank_or_equal():
    assert NotificationConfig(quiet_start="", quiet_end="07:00").in_quiet_hours(
        datetime(2026, 9, 9, 23, 0)) is False
    assert NotificationConfig(quiet_start="08:00", quiet_end="08:00").in_quiet_hours(
        datetime(2026, 9, 9, 8, 0)) is False


def test_should_notify_gates():
    now = datetime(2026, 9, 9, 12, 0)  # outside default quiet hours
    assert NotificationConfig().should_notify(SOURCE_TASK_DUE, now) is True
    assert NotificationConfig(enabled=False).should_notify(SOURCE_TASK_DUE, now) is False
    assert NotificationConfig(task_due_today=False).should_notify(
        SOURCE_TASK_DUE, now) is False
    night = datetime(2026, 9, 9, 23, 30)
    assert NotificationConfig().should_notify(SOURCE_TASK_DUE, night) is False


# ---- relative_time --------------------------------------------------------
def test_relative_time_buckets():
    now = datetime(2026, 9, 9, 12, 0, 0)
    assert relative_time((now - timedelta(seconds=10)).isoformat(), now) == "now"
    assert relative_time((now - timedelta(minutes=5)).isoformat(), now) == "5m"
    assert relative_time((now - timedelta(hours=2)).isoformat(), now) == "2h"
    assert relative_time((now - timedelta(days=3)).isoformat(), now) == "3d"
    assert relative_time("not-a-date", now) == ""
