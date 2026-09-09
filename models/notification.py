"""Notification entities + gating logic — pure data, no Qt/DB/network.

The app records notifications into a persisted feed (see
``TaskRepository``) and surfaces them two ways: the header bell panel (the full
in-app history) and, for events the user has opted into, an OS desktop toast.

Everything that needs *deciding* — which source a toggle governs, whether a
moment falls inside quiet hours, how to render a relative timestamp — lives here
so it stays headlessly unit-testable. The view only paints and calls the OS
notifier; the controller only persists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Source constants — each drives OS-delivery gating and is intentionally equal to
# the matching ``NotificationConfig`` field name, so ``getattr(cfg, source)``
# reads that toggle directly.
SOURCE_AZURE_REVIEW = "azure_pr_review"
SOURCE_AZURE_VOTE = "azure_pr_vote"
SOURCE_AZURE_COMMENT = "azure_pr_comment"
SOURCE_LINEAR = "linear_issue"
SOURCE_TASK_DUE = "task_due_today"
SOURCE_TASK_OVERDUE = "task_overdue"

# Feed "kind" → icon bucket (mapped to a concrete icon in the view).
KIND_PR = "pr"
KIND_LINEAR = "linear"
KIND_REMINDER = "reminder"
KIND_SYNC = "sync"


@dataclass
class Notification:
    """One persisted feed entry.

    ``dedup_key`` (when set) is unique across the feed: recording a second
    notification with the same key is silently skipped, which is how repeated
    reminders / sync events are collapsed. ``id`` is None until persisted.
    """
    kind: str
    title: str
    body: str = ""
    read: bool = False
    dedup_key: Optional[str] = None
    id: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


@dataclass
class NotificationEvent:
    """A transient description of a just-recorded notification.

    Buffered by the controller (never persisted) so the view can decide whether
    to fire an OS toast for it — ``source`` keys the settings gating. Keeping the
    OS-delivery decision off the persisted row lets the bell show the full history
    regardless of what the user muted.
    """
    source: str
    kind: str
    title: str
    body: str = ""
    dedup_key: Optional[str] = None


@dataclass
class NotificationConfig:
    """User preferences for desktop notifications (persisted in QSettings via
    ``services.notification_settings``). ``enabled`` is the master switch; the
    per-source booleans are named to match the ``SOURCE_*`` constants."""
    enabled: bool = True
    azure_pr_review: bool = True
    azure_pr_vote: bool = True
    azure_pr_comment: bool = True
    linear_issue: bool = True
    task_due_today: bool = True
    task_overdue: bool = True
    sound: bool = True                  # reserved — plyer has no sound arg today
    quiet_start: str = "22:00"          # "" on either bound disables quiet hours
    quiet_end: str = "07:00"

    def source_enabled(self, source: str) -> bool:
        return bool(getattr(self, source, False))

    def in_quiet_hours(self, now: datetime) -> bool:
        """True if ``now`` falls inside the quiet-hours window.

        Handles windows that wrap past midnight (e.g. 22:00–07:00). A blank or
        malformed bound disables quiet hours entirely.
        """
        start = _parse_hhmm(self.quiet_start)
        end = _parse_hhmm(self.quiet_end)
        if start is None or end is None or start == end:
            return False
        minutes = now.hour * 60 + now.minute
        if start < end:
            return start <= minutes < end
        # Wrap-around window: inside if after start OR before end.
        return minutes >= start or minutes < end

    def should_notify(self, source: str, now: datetime) -> bool:
        """Whether an event from ``source`` should fire an OS toast right now."""
        return (
            self.enabled
            and self.source_enabled(source)
            and not self.in_quiet_hours(now)
        )


def _parse_hhmm(value: str) -> Optional[int]:
    """Parse ``"HH:MM"`` into minutes-since-midnight, or None if unparseable."""
    if not value or ":" not in value:
        return None
    try:
        hh, mm = value.split(":", 1)
        h, m = int(hh), int(mm)
    except ValueError:
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h * 60 + m


def relative_time(created_at: str, now: Optional[datetime] = None) -> str:
    """Render an ISO timestamp as a short relative stamp: "now"/"5m"/"2h"/"3d"."""
    now = now or datetime.now()
    try:
        then = datetime.fromisoformat(created_at)
    except ValueError:
        return ""
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 60:
        return "now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    return f"{hours // 24}d"
