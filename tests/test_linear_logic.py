"""Pure-logic tests for the Linear integration (no Qt, no network).

Mirrors ``tests/test_integration_logic.py``: exercises the reconcile/dedup logic
in the controller, the mapping/exclusion helpers, the GraphQL response parser,
and the prefix-scoped link clearing.
"""
from __future__ import annotations

from controllers.task_controller import TaskController
from models.linear import (
    LinearConfig,
    LinearIssue,
    filter_excluded,
    issue_to_task_fields,
    linear_key,
)
from models.task import Priority
from models.task_repository import TaskRepository
from services.linear_client import LinearClient


def _repo() -> TaskRepository:
    return TaskRepository(":memory:")


def _issue(iid, *, ident="ENG-1", title="Do thing", state_id="s1",
           state_name="In Progress", labels=None) -> LinearIssue:
    return LinearIssue(
        id=iid, identifier=ident, title=title, url=f"https://linear.app/i/{iid}",
        state_id=state_id, state_name=state_name, state_type="started",
        label_names=list(labels or []),
    )


def _config(status_priorities=None, exclude_labels=None) -> LinearConfig:
    return LinearConfig(
        enabled=True,
        team_ids=["t1"],
        status_priorities=status_priorities
        or [{"id": "s1", "name": "In Progress", "priority": int(Priority.HIGH)}],
        exclude_labels=exclude_labels or [],
    )


# ---- config helpers ------------------------------------------------------
def test_priority_for_maps_status_and_defaults_to_medium():
    cfg = _config(status_priorities=[
        {"id": "s1", "name": "In Progress", "priority": int(Priority.URGENT)},
        {"id": "s2", "name": "Todo", "priority": int(Priority.LOW)},
    ])
    assert cfg.priority_for("s1") == Priority.URGENT
    assert cfg.priority_for("s2") == Priority.LOW
    assert cfg.priority_for("unknown") == Priority.MEDIUM
    assert set(cfg.synced_state_ids()) == {"s1", "s2"}


def test_has_active_sources_requires_team_and_status():
    assert _config().has_active_sources()
    assert not LinearConfig(enabled=True, team_ids=[], status_priorities=[
        {"id": "s1", "name": "x", "priority": 3}]).has_active_sources()
    assert not LinearConfig(enabled=True, team_ids=["t1"],
                            status_priorities=[]).has_active_sources()
    assert not LinearConfig(enabled=False, team_ids=["t1"], status_priorities=[
        {"id": "s1", "name": "x", "priority": 3}]).has_active_sources()


# ---- mapping + exclusion -------------------------------------------------
def test_issue_to_task_fields():
    fields = issue_to_task_fields(_issue("i1"), Priority.HIGH)
    assert fields["title"] == "ENG-1: Do thing"
    assert fields["priority"] == Priority.HIGH
    assert fields["category"] == "Linear"
    assert fields["deadline"] is None
    assert "https://linear.app/i/i1" in fields["description"]


def test_filter_excluded_drops_issues_carrying_any_excluded_label():
    issues = [
        _issue("a", labels=["frontend"]),
        _issue("b", labels=["blocked", "frontend"]),
        _issue("c", labels=[]),
    ]
    kept = filter_excluded(issues, ["blocked"])
    assert {i.id for i in kept} == {"a", "c"}
    # No exclusions -> everything kept.
    assert len(filter_excluded(issues, [])) == 3


# ---- reconcile -----------------------------------------------------------
def test_sync_creates_tasks_with_mapped_priority_and_links():
    ctrl = TaskController(_repo())
    cfg = _config()
    summary = ctrl.sync_linear_issues([_issue("i1"), _issue("i2", ident="ENG-2")], cfg)
    assert summary == {"created": 2, "skipped": 0, "completed": 0}
    tasks = ctrl.list_tasks()
    assert len(tasks) == 2
    assert all(t.priority == Priority.HIGH for t in tasks)
    assert all(t.category == "Linear" for t in tasks)


def test_sync_is_idempotent_and_never_duplicates():
    ctrl = TaskController(_repo())
    cfg = _config()
    ctrl.sync_linear_issues([_issue("i1")], cfg)
    summary = ctrl.sync_linear_issues([_issue("i1")], cfg)
    assert summary == {"created": 0, "skipped": 1, "completed": 0}
    assert len(ctrl.list_tasks()) == 1


def test_resync_updates_priority_when_status_changes():
    ctrl = TaskController(_repo())
    cfg = _config(status_priorities=[
        {"id": "s1", "name": "In Progress", "priority": int(Priority.HIGH)},
        {"id": "s2", "name": "In Review", "priority": int(Priority.URGENT)},
    ])
    ctrl.sync_linear_issues([_issue("i1", state_id="s1")], cfg)
    assert ctrl.list_tasks()[0].priority == Priority.HIGH
    # Same issue moved to a different (still-selected) status -> re-prioritised.
    ctrl.sync_linear_issues([_issue("i1", state_id="s2", state_name="In Review")], cfg)
    tasks = ctrl.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].priority == Priority.URGENT


def test_sync_completes_task_when_issue_leaves_eligible_set():
    ctrl = TaskController(_repo())
    cfg = _config()
    ctrl.sync_linear_issues([_issue("i1")], cfg)
    # Issue no longer returned (moved to Done / unselected status).
    summary = ctrl.sync_linear_issues([], cfg)
    assert summary["completed"] == 1
    assert ctrl.list_tasks()[0].completed is True


def test_sync_completes_task_when_issue_gains_excluded_label():
    ctrl = TaskController(_repo())
    cfg = _config(exclude_labels=["blocked"])
    ctrl.sync_linear_issues([_issue("i1")], cfg)
    assert ctrl.list_tasks()[0].completed is False
    # Same issue now carries an excluded label -> filtered out -> completed.
    ctrl.sync_linear_issues([_issue("i1", labels=["blocked"])], cfg)
    assert ctrl.list_tasks()[0].completed is True


def test_excluded_issue_never_creates_a_task():
    ctrl = TaskController(_repo())
    cfg = _config(exclude_labels=["blocked"])
    summary = ctrl.sync_linear_issues([_issue("i1", labels=["blocked"])], cfg)
    assert summary == {"created": 0, "skipped": 0, "completed": 0}
    assert ctrl.list_tasks() == []


def test_reconcile_is_scoped_and_leaves_azure_links_untouched():
    repo = _repo()
    ctrl = TaskController(repo)
    # An Azure-style link that must survive Linear reconciliation.
    azure_task = ctrl.create_task("Review PR #9", category="Azure PR")
    repo.link_pr("review:myorg:9", azure_task.id)

    ctrl.sync_linear_issues([_issue("i1")], _config())
    # Syncing Linear with an empty result completes only Linear tasks.
    ctrl.sync_linear_issues([], _config())

    assert repo.get_pr_link("review:myorg:9") == azure_task.id
    assert repo.get(azure_task.id).completed is False


def test_clear_linear_links_keeps_azure_links():
    repo = _repo()
    ctrl = TaskController(repo)
    repo.link_pr("review:myorg:9", 1)
    repo.link_pr("linear:i1", 2)
    ctrl.clear_linear_links()
    links = repo.list_pr_links()
    assert "review:myorg:9" in links
    assert "linear:i1" not in links


# ---- GraphQL parsing -----------------------------------------------------
def test_parse_issues_projects_fields_and_labels():
    block = {
        "nodes": [
            {
                "id": "i1", "identifier": "ENG-1", "title": "Fix bug",
                "url": "https://linear.app/i/i1",
                "state": {"id": "s1", "name": "In Progress", "type": "started"},
                "labels": {"nodes": [{"name": "backend"}, {"name": "urgent"}]},
            }
        ]
    }
    issues = LinearClient._parse_issues(block)
    assert len(issues) == 1
    i = issues[0]
    assert i.id == "i1"
    assert i.identifier == "ENG-1"
    assert i.state_id == "s1"
    assert i.state_type == "started"
    assert i.label_names == ["backend", "urgent"]


def test_parse_issues_tolerates_missing_optional_fields():
    issues = LinearClient._parse_issues({"nodes": [{"id": "i2"}]})
    assert issues[0].id == "i2"
    assert issues[0].label_names == []
    assert issues[0].state_id == ""


def test_linear_key_format():
    assert linear_key("abc") == "linear:abc"
