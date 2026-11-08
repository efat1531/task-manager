"""GitHub integration entities — pure data, no Qt/DB/network.

Mirrors :mod:`models.integration` (Azure): UI- and storage-agnostic so the
sync/dedup logic that consumes these objects (in the controller) stays
unit-testable without a display or a network.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from models.task import Priority

#: Prefix shared by every GitHub dedup key in the ``pr_links`` table. The
#: source ("review" | "author") follows, e.g. ``github-review:``. No ``_`` or
#: ``%`` here: the repository clears links with SQL ``LIKE``.
KEY_PREFIX = "github-"

# GitHub account/org logins: alphanumerics and single hyphens (also tolerates the
# "[bot]"-less forms). Validated before being placed in a search qualifier so a
# typo'd or hostile value can't smuggle extra qualifiers into the query.
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


@dataclass
class GitHubConfig:
    """User-entered connection settings (the token is NOT stored here — see
    ``services.credentials``). The authenticated user's login is resolved from the
    token on every sync, so a swapped token can never leave a stale identity."""
    enabled: bool = False
    owner: str = ""                 # optional organization to restrict PRs to (org:); "" = all
    poll_minutes: int = 15
    # Which pull requests become tasks. Both default off — a user opts in per source.
    create_for_reviewer: bool = False   # PRs where your review is requested
    create_for_author: bool = False     # PRs you opened
    priority_review: Priority = Priority.HIGH
    priority_author: Priority = Priority.MEDIUM

    @property
    def owner_slug(self) -> str:
        """Bare owner name, tolerating a pasted ``github.com/<owner>`` URL."""
        owner = self.owner.strip().rstrip("/")
        for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
            if owner.lower().startswith(prefix):
                owner = owner[len(prefix):]
                break
        return owner.split("/")[0]

    @property
    def owner_is_valid(self) -> bool:
        """True when the owner is blank (no filter) or a well-formed login."""
        slug = self.owner_slug
        return not slug or bool(_OWNER_RE.match(slug))

    def is_configured(self) -> bool:
        return bool(self.enabled and self.owner_is_valid)

    @property
    def enabled_sources(self) -> list[str]:
        """The PR sources the user has switched on, as ``"review"`` / ``"author"``."""
        sources: list[str] = []
        if self.create_for_reviewer:
            sources.append("review")
        if self.create_for_author:
            sources.append("author")
        return sources

    def has_active_sources(self) -> bool:
        """True when configured and at least one PR source is enabled."""
        return self.is_configured() and bool(self.enabled_sources)


@dataclass
class GitHubPullRequest:
    """One open GitHub pull request, projected to the fields the app needs."""
    number: int
    title: str
    repository: str = ""            # "owner/name"
    author: str = ""
    url: str = ""
    is_author: bool = False         # did the current user open this PR?
    is_draft: bool = False
    # True when the PR's review decision is CHANGES_REQUESTED. For an authored PR
    # this is "waiting for author": its task is parked at Low with the unresolved
    # pin suppressed (mirrors Azure's -5 vote handling). Always False for review PRs.
    changes_requested: bool = False
    # Count of unresolved review threads. Only fetched for authored PRs; a positive
    # value pins the PR's task to the top as Urgent (see the controller).
    unresolved_comment_count: int = 0

    @property
    def repo_name(self) -> str:
        """Short repository name (without the owner)."""
        return self.repository.split("/", 1)[-1]


def github_key(repository: str, number: int, source: str = "review") -> str:
    """Stable dedup key, e.g. ``github-review:contoso/widgets#42``.

    The ``source`` ("review" | "author") keeps each task source isolated so syncing
    one never auto-completes the other's tasks; the ``github-`` prefix keeps GitHub
    links apart from Azure's (``review:``/``author:``) and Linear's (``linear:``)."""
    return f"{KEY_PREFIX}{source}:{repository}#{number}"


def done_key(source: str, repository: str, number: int) -> str:
    """Marker link recording that a task was *auto*-completed by a sync (its PR left
    the set). Lets a later sync reopen exactly those tasks when the PR returns,
    without overriding a task the user completed by hand. Its prefix
    (``github-done:``) differs from every ``source_prefix`` so reconcile never
    mistakes it for a PR link, yet ``KEY_PREFIX`` clearing still removes it."""
    return f"{KEY_PREFIX}done:{source}:{repository}#{number}"


def source_prefix(source: str) -> str:
    """The ``pr_links`` key prefix owning one GitHub source's links."""
    return f"{KEY_PREFIX}{source}:"


def pr_to_task_fields(pr: GitHubPullRequest, config: "GitHubConfig | None" = None) -> dict:
    """Map a pull request onto the fields used to create its task.

    Priority comes from ``config`` (defaults: review High, authored Medium).
    """
    if config is None:
        config = GitHubConfig()
    repo_part = f"{pr.repo_name} " if pr.repo_name else ""
    if pr.is_author:
        priority = Priority.LOW if pr.changes_requested else config.priority_author
        title = f"Your {repo_part}PR #{pr.number}: {pr.title}"
        role_line = "You are the author"
    else:
        priority = config.priority_review
        title = f"Review {repo_part}PR #{pr.number}: {pr.title}"
        role_line = "Your review was requested"

    lines = [f"Pull request #{pr.number}" + (" (draft)" if pr.is_draft else ""), role_line]
    if pr.repository:
        lines.append(f"Repository: {pr.repository}")
    if pr.author:
        lines.append(f"Author: {pr.author}")
    if pr.url:
        lines.append(f"Link: {pr.url}")
    return {
        "title": title,
        "description": "\n".join(lines),
        "priority": priority,
        "category": "GitHub PR",
        "deadline": None,
    }
