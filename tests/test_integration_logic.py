"""Azure integration: dedup, auto-complete, mapping, and PR parsing (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import urllib.error  # noqa: E402

from controllers.task_controller import TaskController  # noqa: E402
from models.integration import (  # noqa: E402
    AzureConfig,
    PullRequest,
    pr_key,
    pr_to_task_fields,
)
from models.task import Priority  # noqa: E402
from models.task_repository import TaskRepository  # noqa: E402
from services import azure_client  # noqa: E402
from services.azure_client import AzureDevOpsClient, AzureError  # noqa: E402

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
    assert summary == {"created": 2, "skipped": 0, "completed": 0, "reopened": 0}
    assert len(controller.list_tasks()) == 2


def test_resync_same_prs_creates_no_duplicates(controller):
    controller.sync_pull_requests([_pr(1), _pr(2)], ORG)
    summary = controller.sync_pull_requests([_pr(1), _pr(2)], ORG)
    assert summary == {"created": 0, "skipped": 2, "completed": 0, "reopened": 0}
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
    assert summary == {"created": 0, "skipped": 1, "completed": 0, "reopened": 0}
    by_title = {t.title: t for t in controller.list_tasks()}
    assert by_title["Your PR #2: My PR"].completed is False


def test_parse_created_prs_marks_author():
    payload = {
        "value": [
            {
                "pullRequestId": 201,
                "title": "Mine",
                "status": "active",
                "repository": {"id": "repo-guid", "name": "web",
                               "project": {"name": "Store"}},
                "createdBy": {"displayName": "Me"},
            }
        ]
    }
    prs = AzureDevOpsClient._parse_created_prs(payload)
    assert len(prs) == 1
    assert prs[0].pr_id == 201
    assert prs[0].is_author is True
    assert prs[0].is_required is False
    assert prs[0].repository_id == "repo-guid"


# ---- unresolved comment threads ------------------------------------------
def test_count_active_threads_only_counts_unresolved_comment_threads():
    payload = {
        "value": [
            {"id": 1, "status": "active"},                 # unresolved -> counts
            {"id": 2, "status": "fixed"},                  # resolved
            {"id": 3, "status": "closed"},                 # resolved
            {"id": 4},                                     # system thread, no status
            {"id": 5, "status": "active", "isDeleted": True},  # deleted, ignored
            {"id": 6, "status": "active"},                 # unresolved -> counts
        ]
    }
    assert AzureDevOpsClient.count_active_threads(payload) == 2


def test_count_active_threads_empty():
    assert AzureDevOpsClient.count_active_threads({}) == 0
    assert AzureDevOpsClient.count_active_threads({"value": []}) == 0


def test_active_comment_count_zero_without_repository_id():
    # No repository id (older links) -> no API call, count is 0.
    client = AzureDevOpsClient(ORG, pat="tok")
    assert client.active_comment_count("", 5) == 0


# ---- authored-PR unresolved-comment pinning ------------------------------
def _author_pr(pr_id: int, unresolved: int = 0, title: str = "My PR") -> PullRequest:
    return PullRequest(pr_id=pr_id, title=title, is_author=True,
                       unresolved_comment_count=unresolved)


def test_sync_sets_unresolved_flag_for_authored_pr(controller):
    controller.sync_pull_requests(
        [_author_pr(1, unresolved=3)], ORG, source="author"
    )
    task = controller.list_tasks()[0]
    assert task.unresolved_comments == 3


def test_resync_refreshes_flag_on_already_linked_pr(controller):
    controller.sync_pull_requests([_author_pr(1, unresolved=3)], ORG, source="author")
    # Comments get resolved; the PR is already linked (skipped) but the flag
    # must still be refreshed to 0 so the task drops back down.
    summary = controller.sync_pull_requests(
        [_author_pr(1, unresolved=0)], ORG, source="author"
    )
    assert summary == {"created": 0, "skipped": 1, "completed": 0, "reopened": 0}
    assert controller.list_tasks()[0].unresolved_comments == 0


def test_review_pr_never_flagged(controller):
    controller.sync_pull_requests([_pr(1)], ORG, source="review")
    assert controller.list_tasks()[0].unresolved_comments == 0


# ---- review-vote auto-complete / reopen ----------------------------------
def _voted_pr(pr_id: int, vote: int, is_required: bool = True,
              title: str = "Feature") -> PullRequest:
    return PullRequest(pr_id=pr_id, title=title, repository="repo",
                       is_required=is_required, reviewer_vote=vote)


def test_review_completed_property():
    assert _voted_pr(1, 10).review_completed is True   # approved
    assert _voted_pr(1, 5).review_completed is True    # approved w/ suggestions
    assert _voted_pr(1, -10).review_completed is True  # rejected
    assert _voted_pr(1, -5).review_completed is True   # waiting for author
    assert _voted_pr(1, 0).review_completed is False   # no vote / reset


def test_voted_review_pr_autocompletes_on_creation(controller):
    summary = controller.sync_pull_requests([_voted_pr(1, 10)], ORG, source="review")
    assert summary["created"] == 1
    assert summary["completed"] == 1
    assert controller.list_tasks()[0].completed is True


def test_unvoted_review_pr_stays_open(controller):
    controller.sync_pull_requests([_voted_pr(1, 0)], ORG, source="review")
    assert controller.list_tasks()[0].completed is False


def test_voting_later_completes_already_linked_task(controller):
    # First sync: no vote yet -> task stays open.
    controller.sync_pull_requests([_voted_pr(1, 0)], ORG, source="review")
    assert controller.list_tasks()[0].completed is False
    # Second sync: I've now approved -> the already-linked task is completed.
    summary = controller.sync_pull_requests([_voted_pr(1, 10)], ORG, source="review")
    assert summary == {"created": 0, "skipped": 1, "completed": 1, "reopened": 0}
    assert controller.list_tasks()[0].completed is True


def test_vote_reset_reopens_completed_task(controller):
    controller.sync_pull_requests([_voted_pr(1, 10)], ORG, source="review")
    assert controller.list_tasks()[0].completed is True
    # A new commit reset my vote to 0 -> the task reopens for another look.
    summary = controller.sync_pull_requests([_voted_pr(1, 0)], ORG, source="review")
    assert summary == {"created": 0, "skipped": 1, "completed": 0, "reopened": 1}
    assert controller.list_tasks()[0].completed is False


def test_optional_reviewer_vote_also_completes(controller):
    summary = controller.sync_pull_requests(
        [_voted_pr(1, 10, is_required=False)], ORG, source="review"
    )
    assert summary["completed"] == 1
    assert controller.list_tasks()[0].completed is True


def test_author_source_ignores_vote_logic(controller):
    # An authored PR carries no vote; completing/reopening must not apply to it.
    controller.sync_pull_requests([_author_pr(1)], ORG, source="author")
    task = controller.list_tasks()[0]
    controller.toggle_completed(task)  # user completes it manually
    assert controller.list_tasks()[0].completed is True
    summary = controller.sync_pull_requests([_author_pr(1)], ORG, source="author")
    # No spurious reopen — the vote branch is review-source only.
    assert summary["reopened"] == 0
    assert controller.list_tasks()[0].completed is True


def test_parse_prs_extracts_reviewer_vote():
    me = "guid-me"
    payload = {
        "value": [
            {
                "pullRequestId": 301,
                "title": "Approved by me",
                "reviewers": [{"id": me, "isRequired": True, "vote": 10}],
            },
            {
                "pullRequestId": 302,
                "title": "Not yet voted",
                "reviewers": [{"id": me, "isRequired": True}],
            },
        ]
    }
    prs = AzureDevOpsClient._parse_prs(payload, me)
    votes = {p.pr_id: p.reviewer_vote for p in prs}
    assert votes == {301: 10, 302: 0}
    assert prs[0].review_completed is True
    assert prs[1].review_completed is False


# ---- rate-limit handling (no live network) -------------------------------
class _FakeResponse:
    """Minimal stand-in for urlopen's context-manager response."""

    def __init__(self, body: str) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body.encode("utf-8")


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError(
        "https://dev.azure.com/o/_apis/connectionData",
        code,
        "boom",
        headers,
        None,
    )


def test_get_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps: list[int] = []

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, retry_after="1")
        return _FakeResponse('{"ok": true}')

    monkeypatch.setattr(azure_client.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(azure_client.time, "sleep", lambda s: sleeps.append(s))

    client = AzureDevOpsClient(ORG, pat="tok")
    assert client._get("https://dev.azure.com/o/_apis/connectionData") == {"ok": True}
    assert calls["n"] == 2  # one retry
    assert sleeps == [1]  # honoured the Retry-After header


def test_get_raises_after_exhausting_retries(monkeypatch):
    calls = {"n": 0}

    def always_429(request, timeout=None):
        calls["n"] += 1
        raise _http_error(429, retry_after="1")

    monkeypatch.setattr(azure_client.urllib.request, "urlopen", always_429)
    monkeypatch.setattr(azure_client.time, "sleep", lambda s: None)

    client = AzureDevOpsClient(ORG, pat="tok")
    with pytest.raises(AzureError, match="rate limiting"):
        client._get("https://dev.azure.com/o/_apis/connectionData")
    assert calls["n"] == azure_client._MAX_ATTEMPTS  # no more than the cap


def test_retry_after_falls_back_when_header_missing():
    assert AzureDevOpsClient._retry_after_seconds(_http_error(429)) == \
        azure_client._DEFAULT_RETRY_WAIT


def test_retry_after_is_clamped_to_ceiling():
    huge = AzureDevOpsClient._retry_after_seconds(_http_error(429, retry_after="99999"))
    assert huge == azure_client._MAX_RETRY_WAIT


def test_get_reports_403_as_authentication_failure(monkeypatch):
    def forbidden(request, timeout=None):
        raise _http_error(403)

    monkeypatch.setattr(azure_client.urllib.request, "urlopen", forbidden)

    client = AzureDevOpsClient(ORG, pat="tok")
    with pytest.raises(AzureError, match="authentication failed"):
        client._get("https://dev.azure.com/o/_apis/connectionData")
