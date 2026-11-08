"""GitHub integration: dedup, auto-complete, mapping, parsing, and client plumbing
(no Qt, no network). Mirrors ``test_integration_logic.py`` / ``test_linear_logic.py``.

All identifiers are fictional (Contoso / fake numbers).
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controllers.task_controller import TaskController  # noqa: E402
from models.github import (  # noqa: E402
    GitHubConfig,
    GitHubPullRequest,
    github_key,
    pr_to_task_fields,
)
from models.integration import PullRequest  # noqa: E402
from models.task import Priority  # noqa: E402
from models.task_repository import TaskRepository  # noqa: E402
from services import github_client  # noqa: E402
from services.github_client import GitHubClient, GitHubError  # noqa: E402

REPO = "contoso/widgets"


@pytest.fixture()
def controller() -> TaskController:
    return TaskController(TaskRepository(":memory:"))


def _pr(number: int, *, author: bool = False, repo: str = REPO, title: str = "Feature",
        unresolved: int = 0, changes: bool = False, draft: bool = False) -> GitHubPullRequest:
    return GitHubPullRequest(
        number=number, title=title, repository=repo, author="alice",
        url=f"https://github.com/{repo}/pull/{number}",
        is_author=author, is_draft=draft, changes_requested=changes,
        unresolved_comment_count=unresolved,
    )


# ---- config ----------------------------------------------------------------
def test_owner_slug_strips_url_and_path():
    assert GitHubConfig(owner="https://github.com/contoso/").owner_slug == "contoso"
    assert GitHubConfig(owner="github.com/contoso/widgets").owner_slug == "contoso"
    assert GitHubConfig(owner=" contoso ").owner_slug == "contoso"


def test_owner_validation_rejects_qualifier_injection():
    assert GitHubConfig(owner="").owner_is_valid
    assert GitHubConfig(owner="contoso-eng").owner_is_valid
    assert not GitHubConfig(owner="contoso repo:secret").owner_is_valid
    assert not GitHubConfig(owner="-bad").owner_is_valid


def test_active_sources():
    cfg = GitHubConfig(enabled=True)
    assert not cfg.has_active_sources()
    cfg.create_for_author = True
    assert cfg.enabled_sources == ["author"] and cfg.has_active_sources()
    cfg.create_for_reviewer = True
    assert cfg.enabled_sources == ["review", "author"]
    cfg.enabled = False
    assert not cfg.has_active_sources()
    assert not GitHubConfig(enabled=True, create_for_author=True,
                            owner="bad owner").has_active_sources()


# ---- key / mapping ---------------------------------------------------------
def test_key_namespaced_by_source_and_never_collides_with_azure_or_linear():
    review = github_key(REPO, 7, "review")
    assert review == "github-review:contoso/widgets#7"
    assert review != github_key(REPO, 7, "author")
    assert not review.startswith(("review:", "author:", "linear:"))


def test_review_mapping_and_priority_config():
    fields = pr_to_task_fields(_pr(12, title="Add thing"))
    assert fields["title"] == "Review widgets PR #12: Add thing"
    assert fields["priority"] == Priority.HIGH
    assert fields["category"] == "GitHub PR"
    assert "Link: https://github.com/contoso/widgets/pull/12" in fields["description"]
    cfg = GitHubConfig(priority_review=Priority.LOW)
    assert pr_to_task_fields(_pr(12), cfg)["priority"] == Priority.LOW


def test_author_mapping_and_waiting_is_low():
    fields = pr_to_task_fields(_pr(3, author=True))
    assert fields["title"].startswith("Your widgets PR #3")
    assert fields["priority"] == Priority.MEDIUM
    assert pr_to_task_fields(_pr(3, author=True, changes=True))["priority"] == Priority.LOW


def test_draft_noted_in_description():
    assert "(draft)" in pr_to_task_fields(_pr(5, draft=True))["description"]


# ---- review sync -----------------------------------------------------------
def test_sync_creates_one_task_per_pr_and_is_idempotent(controller):
    first = controller.sync_github_prs([_pr(1), _pr(2)], "review")
    assert first["created"] == 2
    again = controller.sync_github_prs([_pr(1), _pr(2)], "review")
    assert again["created"] == 0 and again["skipped"] == 2
    assert len(controller.list_tasks()) == 2


def test_same_number_in_different_repos_are_distinct(controller):
    controller.sync_github_prs([_pr(1), _pr(1, repo="contoso/gadgets")], "review")
    assert len(controller.list_tasks()) == 2


def test_deleted_task_is_not_recreated(controller):
    controller.sync_github_prs([_pr(1)], "review")
    controller._repo.delete(controller.list_tasks()[0].id)
    summary = controller.sync_github_prs([_pr(1)], "review")
    assert summary["created"] == 0
    assert controller.list_tasks() == []


def test_absent_pr_autocompletes_and_is_idempotent(controller):
    controller.sync_github_prs([_pr(1), _pr(2)], "review")
    s = controller.sync_github_prs([_pr(1)], "review")
    assert s["completed"] == 1
    assert controller.sync_github_prs([_pr(1)], "review")["completed"] == 0


def test_rerequested_review_reopens_task(controller):
    controller.sync_github_prs([_pr(1)], "review")
    controller.sync_github_prs([], "review")
    assert controller.list_tasks()[0].completed
    s = controller.sync_github_prs([_pr(1)], "review")
    assert s["reopened"] == 1
    assert not controller.list_tasks()[0].completed


def test_review_creation_records_notification_once(controller):
    controller.sync_github_prs([_pr(1)], "review")
    controller.sync_github_prs([_pr(1)], "review")
    events = controller.drain_notification_events()
    assert [e.source for e in events] == ["github_pr_review"]


# ---- author sync -----------------------------------------------------------
def test_authored_unresolved_threads_pin_task(controller):
    controller.sync_github_prs([_pr(1, author=True, unresolved=2)], "author")
    assert controller.list_tasks()[0].unresolved_comments == 2
    controller.sync_github_prs([_pr(1, author=True, unresolved=0)], "author")
    assert controller.list_tasks()[0].unresolved_comments == 0


def test_new_comment_notifies_only_on_increase(controller):
    controller.sync_github_prs([_pr(1, author=True)], "author")
    controller.drain_notification_events()
    controller.sync_github_prs([_pr(1, author=True, unresolved=1)], "author")
    controller.sync_github_prs([_pr(1, author=True, unresolved=1)], "author")
    events = controller.drain_notification_events()
    assert [e.source for e in events] == ["github_pr_comment"]


def test_changes_requested_parks_pr_and_restores(controller):
    controller.sync_github_prs([_pr(1, author=True, unresolved=3)], "author")
    controller.drain_notification_events()
    controller.sync_github_prs([_pr(1, author=True, unresolved=3, changes=True)], "author")
    task = controller.list_tasks()[0]
    assert task.priority == Priority.LOW and task.unresolved_comments == 0
    assert [e.source for e in controller.drain_notification_events()] == [
        "github_pr_changes"
    ]
    controller.sync_github_prs([_pr(1, author=True, unresolved=1)], "author")
    task = controller.list_tasks()[0]
    assert task.priority == Priority.MEDIUM and task.unresolved_comments == 1


def test_manual_completion_of_review_task_is_not_reopened(controller):
    controller.sync_github_prs([_pr(1)], "review")
    controller._repo.set_completed(controller.list_tasks()[0].id, True)
    for _ in range(2):  # PR still in the review-requested set on every poll
        s = controller.sync_github_prs([_pr(1)], "review")
        assert s["reopened"] == 0
    assert controller.list_tasks()[0].completed


def test_autocompleted_author_task_reopens_when_pr_returns(controller):
    controller.sync_github_prs([_pr(1, author=True)], "author")
    controller.sync_github_prs([], "author")
    assert controller.list_tasks()[0].completed
    s = controller.sync_github_prs([_pr(1, author=True, unresolved=2)], "author")
    task = controller.list_tasks()[0]
    assert s["reopened"] == 1 and not task.completed and task.unresolved_comments == 2
    # the marker is consumed: a later manual completion sticks
    controller._repo.set_completed(task.id, True)
    assert controller.sync_github_prs([_pr(1, author=True)], "author")["reopened"] == 0


def test_author_task_is_not_reopened_after_manual_completion(controller):
    controller.sync_github_prs([_pr(1, author=True)], "author")
    task = controller.list_tasks()[0]
    controller._repo.set_completed(task.id, True)
    s = controller.sync_github_prs([_pr(1, author=True)], "author")
    assert s["reopened"] == 0 and controller.list_tasks()[0].completed


def test_sources_do_not_cross_autocomplete(controller):
    controller.sync_github_prs([_pr(1)], "review")
    controller.sync_github_prs([_pr(2, author=True)], "author")
    controller.sync_github_prs([], "review")
    done = {t.title: t.completed for t in controller.list_tasks()}
    assert done["Review widgets PR #1: Feature"] is True
    assert done["Your widgets PR #2: Feature"] is False


# ---- link isolation --------------------------------------------------------
def test_clear_links_is_scoped_per_integration(controller):
    controller.sync_github_prs([_pr(1)], "review")
    azure = PullRequest(pr_id=9, title="Az", repository="r", is_required=True)
    controller.sync_pull_requests([azure], "contoso", source="review")
    controller._repo.link_pr("linear:abc", controller.list_tasks()[0].id)

    controller.clear_github_links()
    keys = set(controller._repo.list_pr_links())
    assert keys == {"review:contoso:9", "linear:abc"}

    controller.sync_github_prs([_pr(1)], "review")
    controller.clear_pr_links()  # Azure removal must leave GitHub + Linear intact
    keys = set(controller._repo.list_pr_links())
    assert keys == {"github-review:contoso/widgets#1", "linear:abc"}


def test_clear_pr_links_accepts_multiple_prefixes_and_wildcard_chars():
    repo = TaskRepository(":memory:")
    for key in ("a:1", "b:2", "c%:3", "cx:4"):
        repo.link_pr(key, 1)
    repo.clear_pr_links(prefix=("a:", "c%:"))
    assert set(repo.list_pr_links()) == {"b:2", "cx:4"}  # '%' is literal, not LIKE


# ---- parsing ---------------------------------------------------------------
def _search_payload(*nodes):
    return {"nodes": list(nodes), "pageInfo": {"hasNextPage": False}}


def _node(number, **extra):
    node = {
        "number": number, "title": "T", "url": f"https://github.com/{REPO}/pull/{number}",
        "isDraft": False, "reviewDecision": None,
        "repository": {"nameWithOwner": REPO}, "author": {"login": "alice"},
    }
    node.update(extra)
    return node


def test_parse_review_prs_ignores_threads_and_decision():
    prs = GitHubClient._parse_prs(
        _search_payload(_node(1, reviewDecision="CHANGES_REQUESTED")), is_author=False
    )
    assert len(prs) == 1
    assert prs[0].repository == REPO and not prs[0].is_author
    assert prs[0].changes_requested is False


def test_parse_authored_counts_unresolved_and_changes():
    threads = {"nodes": [{"isResolved": False}, {"isResolved": True}, {"isResolved": False}]}
    prs = GitHubClient._parse_prs(
        _search_payload(_node(4, reviewDecision="CHANGES_REQUESTED", reviewThreads=threads)),
        is_author=True,
    )
    assert prs[0].unresolved_comment_count == 2
    assert prs[0].changes_requested and prs[0].is_author


def test_parse_skips_non_pr_nodes_and_tolerates_null_author():
    prs = GitHubClient._parse_prs(
        _search_payload({}, None, _node(2, author=None)), is_author=False
    )
    assert [p.number for p in prs] == [2] and prs[0].author == ""


# ---- client plumbing -------------------------------------------------------
class _Resp:
    def __init__(self, body: str) -> None:
        self._body = body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("u", code, "reason", headers or {}, io.BytesIO(b""))


def test_post_sends_bearer_and_user_agent(monkeypatch):
    seen = {}

    def fake(request, timeout):
        seen["auth"] = request.get_header("Authorization")
        seen["ua"] = request.get_header("User-agent")
        return _Resp(json.dumps({"data": {"viewer": {"login": "alice"}}}))

    monkeypatch.setattr(github_client.urllib.request, "urlopen", fake)
    assert GitHubClient("tok").get_viewer_login() == "alice"
    assert seen == {"auth": "Bearer tok", "ua": "TaskManager"}


def test_plain_403_is_auth_error_without_retry(monkeypatch):
    calls = []

    def fake(request, timeout):
        calls.append(1)
        raise _http_error(403)

    monkeypatch.setattr(github_client.urllib.request, "urlopen", fake)
    monkeypatch.setattr(github_client.time, "sleep", lambda s: None)
    with pytest.raises(GitHubError, match="authentication failed"):
        GitHubClient("tok").get_viewer_login()
    assert len(calls) == 1


def test_rate_limit_retries_then_succeeds(monkeypatch):
    seq = [_http_error(429, {"Retry-After": "2"}),
           _Resp(json.dumps({"data": {"viewer": {"login": "alice"}}}))]
    sleeps = []

    def fake(request, timeout):
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(github_client.urllib.request, "urlopen", fake)
    monkeypatch.setattr(github_client.time, "sleep", sleeps.append)
    assert GitHubClient("tok").get_viewer_login() == "alice"
    assert sleeps == [2]


def test_graphql_errors_raise(monkeypatch):
    monkeypatch.setattr(
        github_client.urllib.request, "urlopen",
        lambda r, timeout: _Resp(json.dumps({"errors": [{"message": "Bad query"}]})),
    )
    with pytest.raises(GitHubError, match="Bad query"):
        GitHubClient("tok").get_viewer_login()


def test_search_paginates_and_builds_qualifiers(monkeypatch):
    queries = []
    pages = [
        {"data": {"search": {"nodes": [_node(1)],
                             "pageInfo": {"hasNextPage": True, "endCursor": "c1"}}}},
        {"data": {"search": {"nodes": [_node(2)],
                             "pageInfo": {"hasNextPage": False, "endCursor": None}}}},
    ]

    def fake(request, timeout):
        queries.append(json.loads(request.data)["variables"])
        return _Resp(json.dumps(pages.pop(0)))

    monkeypatch.setattr(github_client.urllib.request, "urlopen", fake)
    prs = GitHubClient("tok").list_review_requested_prs("alice", "contoso")
    assert [p.number for p in prs] == [1, 2]
    assert queries[0]["after"] is None and queries[1]["after"] == "c1"
    q = queries[0]["q"]
    assert "review-requested:alice" in q and "-author:alice" in q and "org:contoso" in q


def test_search_truncation_raises_instead_of_returning_partial_set(monkeypatch):
    page = {"data": {"search": {"nodes": [_node(1)],
                                "pageInfo": {"hasNextPage": True, "endCursor": "c"}}}}
    monkeypatch.setattr(
        github_client.urllib.request, "urlopen",
        lambda r, timeout: _Resp(json.dumps(page)),
    )
    with pytest.raises(GitHubError, match="narrow the sync"):
        GitHubClient("tok").list_created_prs("alice")


def test_primary_rate_limit_is_reported_as_rate_limit(monkeypatch):
    def forbidden(request, timeout):
        raise _http_error(403, {"X-RateLimit-Remaining": "0"})

    monkeypatch.setattr(github_client.urllib.request, "urlopen", forbidden)
    with pytest.raises(GitHubError, match="rate limiting"):
        GitHubClient("tok").get_viewer_login()
    monkeypatch.setattr(
        github_client.urllib.request, "urlopen",
        lambda r, timeout: _Resp(json.dumps(
            {"errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}
        )),
    )
    with pytest.raises(GitHubError, match="rate limiting"):
        GitHubClient("tok").get_viewer_login()


def test_test_connection_messages(monkeypatch):
    assert GitHubClient("").test_connection() == (False, "Enter a GitHub access token first.")
    monkeypatch.setattr(
        github_client.urllib.request, "urlopen",
        lambda r, timeout: _Resp(json.dumps({"data": {"viewer": {"login": "alice"}}})),
    )
    assert GitHubClient("tok").test_connection() == (True, "Connected as alice.")
