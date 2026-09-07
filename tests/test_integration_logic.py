"""Azure integration: dedup, auto-complete, mapping, and PR parsing (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controllers.task_controller import TaskController  # noqa: E402
from models.integration import (  # noqa: E402
    AzureConfig,
    PullRequest,
    pr_key,
    pr_to_task_fields,
)
from models.task import Priority  # noqa: E402
from models.task_repository import TaskRepository  # noqa: E402
from services.azure_client import AzureDevOpsClient  # noqa: E402

ORG = "myorg"


@pytest.fixture()
def controller() -> TaskController:
    repo = TaskRepository(":memory:")
    yield TaskController(repo)
    repo.close()


def _pr(pr_id: int, title: str = "Feature") -> PullRequest:
    return PullRequest(pr_id=pr_id, title=title, repository="repo",
                       project="proj", author="Alice", is_required=True)


# ---- dedup ---------------------------------------------------------------
def test_sync_creates_one_task_per_pr(controller):
    summary = controller.sync_pull_requests([_pr(1), _pr(2)], ORG)
    assert summary == {"created": 2, "skipped": 0, "completed": 0}
    assert len(controller.list_tasks()) == 2


def test_resync_same_prs_creates_no_duplicates(controller):
    controller.sync_pull_requests([_pr(1), _pr(2)], ORG)
    summary = controller.sync_pull_requests([_pr(1), _pr(2)], ORG)
    assert summary == {"created": 0, "skipped": 2, "completed": 0}
    assert len(controller.list_tasks()) == 2


def test_deleted_task_is_not_recreated(controller):
    controller.sync_pull_requests([_pr(1)], ORG)
    task = controller.list_tasks()[0]
    controller.delete_task(task.id)
    summary = controller.sync_pull_requests([_pr(1)], ORG)
    # The link persists, so the PR is skipped rather than re-created.
    assert summary["created"] == 0
    assert summary["skipped"] == 1
    assert controller.list_tasks() == []


# ---- auto-complete on PR disappearance -----------------------------------
def test_absent_pr_autocompletes_its_task(controller):
    controller.sync_pull_requests([_pr(1), _pr(2)], ORG)
    # PR 1 merged/closed; only PR 2 comes back.
    summary = controller.sync_pull_requests([_pr(2)], ORG)
    assert summary["completed"] == 1
    by_title = {t.title: t for t in controller.list_tasks()}
    assert by_title["Review PR #1: Feature"].completed is True
    assert by_title["Review PR #2: Feature"].completed is False


def test_autocomplete_is_idempotent(controller):
    controller.sync_pull_requests([_pr(1)], ORG)
    controller.sync_pull_requests([], ORG)          # completes it
    summary = controller.sync_pull_requests([], ORG)  # nothing left to complete
    assert summary["completed"] == 0


def test_clear_pr_links_forgets_synced_prs(controller):
    controller.sync_pull_requests([_pr(1)], ORG)
    controller.clear_pr_links()
    # The link is gone, so the same PR is created fresh on the next sync.
    summary = controller.sync_pull_requests([_pr(1)], ORG)
    assert summary["created"] == 1
    assert summary["skipped"] == 0


# ---- link persistence + mapping -----------------------------------------
def test_pr_link_round_trip():
    repo = TaskRepository(":memory:")
    try:
        repo.link_pr(pr_key(ORG, 7), 42)
        assert repo.get_pr_link(pr_key(ORG, 7)) == 42
        # Keys are namespaced by source; "review" is the default.
        assert repo.list_pr_links() == {f"review:{ORG}:7": 42}
        repo.delete_pr_link(pr_key(ORG, 7))
        assert repo.get_pr_link(pr_key(ORG, 7)) is None
    finally:
        repo.close()


def test_pr_key_namespaces_by_source():
    assert pr_key(ORG, 7) == "review:myorg:7"
    assert pr_key(ORG, 7, "author") == "author:myorg:7"


def test_pr_to_task_fields_mapping():
    fields = pr_to_task_fields(_pr(9, "Fix bug"))
    assert fields["title"] == "Review PR #9: Fix bug"
    assert fields["priority"] is Priority.HIGH
    assert fields["category"] == "Azure PR"
    assert fields["deadline"] is None


# ---- pure JSON parsing (no HTTP) -----------------------------------------
def test_parse_prs_includes_required_and_optional_reviewer():
    me = "guid-me"
    payload = {
        "value": [
            {
                "pullRequestId": 101,
                "title": "Required one",
                "status": "active",
                "repository": {"name": "web", "project": {"name": "Store"}},
                "createdBy": {"displayName": "Bob"},
                "_links": {"web": {"href": "https://dev.azure.com/o/_git/web/pr/101"}},
                "reviewers": [{"id": me, "isRequired": True}],
            },
            {
                "pullRequestId": 102,
                "title": "Optional one",
                "status": "active",
                "repository": {"name": "web"},
                "reviewers": [{"id": me, "isRequired": False}],
            },
            {
                "pullRequestId": 103,
                "title": "Someone else",
                "reviewers": [{"id": "other", "isRequired": True}],
            },
        ]
    }
    prs = AzureDevOpsClient._parse_prs(payload, me)
    # Both my required and my optional PRs are kept; the one I'm not on is dropped.
    assert [p.pr_id for p in prs] == [101, 102]
    required, optional = prs
    assert required.is_required is True
    assert required.project == "Store"
    assert required.author == "Bob"
    assert required.url.endswith("/pr/101")
    assert optional.is_required is False


def test_optional_reviewer_task_is_medium_priority():
    fields = pr_to_task_fields(
        PullRequest(pr_id=5, title="Docs", repository="r", is_required=False)
    )
    assert fields["priority"] is Priority.MEDIUM
    assert "optional" in fields["description"]


def test_authored_pr_mapping():
    fields = pr_to_task_fields(
        PullRequest(pr_id=12, title="My work", is_author=True)
    )
    assert fields["title"] == "Your PR #12: My work"
    assert fields["priority"] is Priority.MEDIUM  # default author priority
    assert "author" in fields["description"].lower()


def test_configurable_priorities():
    cfg = AzureConfig(
        priority_required=Priority.URGENT,
        priority_optional=Priority.LOW,
        priority_author=Priority.HIGH,
    )
    required = pr_to_task_fields(PullRequest(pr_id=1, title="r", is_required=True), cfg)
    optional = pr_to_task_fields(PullRequest(pr_id=2, title="o", is_required=False), cfg)
    author = pr_to_task_fields(PullRequest(pr_id=3, title="a", is_author=True), cfg)
    assert required["priority"] is Priority.URGENT
    assert optional["priority"] is Priority.LOW
    assert author["priority"] is Priority.HIGH


# ---- source isolation ----------------------------------------------------
def test_sources_do_not_cross_autocomplete(controller):
    # A review PR and an authored PR both become tasks.
    review_pr = PullRequest(pr_id=1, title="Review me", is_required=True)
    author_pr = PullRequest(pr_id=2, title="My PR", is_author=True)
    controller.sync_pull_requests([review_pr], ORG, source="review")
    controller.sync_pull_requests([author_pr], ORG, source="author")
    assert len(controller.list_tasks()) == 2

    # Re-syncing only the review source (author PR absent from THIS list) must not
    # auto-complete the authored PR's task — it belongs to a different source.
    summary = controller.sync_pull_requests([review_pr], ORG, source="review")
    assert summary == {"created": 0, "skipped": 1, "completed": 0}
    by_title = {t.title: t for t in controller.list_tasks()}
    assert by_title["Your PR #2: My PR"].completed is False


def test_parse_created_prs_marks_author():
    payload = {
        "value": [
            {
                "pullRequestId": 201,
                "title": "Mine",
                "status": "active",
                "repository": {"name": "web", "project": {"name": "Store"}},
                "createdBy": {"displayName": "Me"},
            }
        ]
    }
    prs = AzureDevOpsClient._parse_created_prs(payload)
    assert len(prs) == 1
    assert prs[0].pr_id == 201
    assert prs[0].is_author is True
    assert prs[0].is_required is False
