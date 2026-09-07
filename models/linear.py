"""Linear (linear.app) integration entities — pure data, no Qt/DB/network.

Mirrors ``models.integration`` (the Azure DevOps integration) so the sync/dedup
logic that consumes these objects stays unit-testable without a display or a
network. Linear issues assigned to the authenticated user, sitting in one of the
user-selected workflow statuses, become tasks at the ticket's own Linear
priority, and issues bearing an excluded label are left out.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from models.task import Priority


@dataclass
class LinearConfig:
    """User-entered Linear settings (the API key is NOT stored here — see
    ``services.credentials``).

    ``status_priorities`` is the heart of the feature: each entry is
    ``{"id": <workflowState id>, "name": <display name>}``. A state listed here
    is one the user wants to create tasks from. (The legacy ``"priority"`` key
    may still be present in configs saved by older versions; it is ignored now
    that task priority comes from the Linear ticket itself.) ``exclude_labels``
    holds label *names*; an issue carrying any of them is skipped.
    """

    enabled: bool = False
    team_ids: List[str] = field(default_factory=list)
    poll_minutes: int = 15
    status_priorities: List[dict] = field(default_factory=list)
    exclude_labels: List[str] = field(default_factory=list)

    def synced_state_ids(self) -> List[str]:
        """Workflow-state ids the user has opted to create tasks from."""
        return [str(s["id"]) for s in self.status_priorities if s.get("id")]

    def is_configured(self) -> bool:
        return bool(self.enabled and self.team_ids)

    def has_active_sources(self) -> bool:
        """True when enabled, a team is chosen, and at least one status is synced."""
        return self.is_configured() and bool(self.synced_state_ids())


@dataclass
class LinearIssue:
    """One Linear issue, projected to the fields the app needs."""

    id: str                              # global UUID; unique dedup anchor
    identifier: str = ""                 # human key, e.g. "ENG-123"
    title: str = ""
    url: str = ""
    linear_priority: int = 0             # Linear's own scale: 0 None,1 Urgent…4 Low
    state_id: str = ""
    state_name: str = ""
    state_type: str = ""                 # backlog | unstarted | started | completed | canceled
    label_names: List[str] = field(default_factory=list)


def linear_key(issue_id: str) -> str:
    """Stable dedup key. Linear issue ids are globally unique; the ``linear:``
    prefix keeps these links isolated from the Azure ``review:``/``author:``
    links that share the ``pr_links`` table."""
    return f"linear:{issue_id}"


def filter_excluded(
    issues: List[LinearIssue], exclude_labels: List[str]
) -> List[LinearIssue]:
    """Drop every issue carrying any of ``exclude_labels`` (by label name).

    Pure and case-sensitive on the exact label names Linear returns — safe to
    unit-test with no network.
    """
    excluded = set(exclude_labels or [])
    if not excluded:
        return list(issues)
    return [i for i in issues if not (set(i.label_names) & excluded)]


def linear_priority_to_app(value: int) -> Priority:
    """Map Linear's priority scale onto the app's :class:`Priority`.

    Linear: ``0`` No priority, ``1`` Urgent, ``2`` High, ``3`` Medium, ``4`` Low
    (the inverse of the app enum). "No priority" (0), or any unexpected value,
    defaults to Low.
    """
    return {
        1: Priority.URGENT,
        2: Priority.HIGH,
        3: Priority.MEDIUM,
        4: Priority.LOW,
    }.get(int(value or 0), Priority.LOW)


def issue_to_task_fields(issue: LinearIssue, priority: Priority) -> dict:
    """Map a Linear issue onto the fields used to create its task.

    ``priority`` is the ticket's own Linear priority mapped to the app scale (see
    :func:`linear_priority_to_app`). ``deadline`` is left unset so synced tickets
    show on every day, matching the PR-task behaviour.
    """
    title = f"{issue.identifier}: {issue.title}" if issue.identifier else issue.title
    lines = [f"Linear issue {issue.identifier}".strip()]
    if issue.state_name:
        lines.append(f"Status: {issue.state_name}")
    # Always surface the full ticket link on its own labelled line so it is easy
    # to copy-paste out of the task description.
    if issue.url:
        lines.append(f"Link: {issue.url}")
    return {
        "title": title,
        "description": "\n".join(line for line in lines if line),
        "priority": priority,
        "category": "Linear",
        "deadline": None,
    }
