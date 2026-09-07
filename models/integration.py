"""Azure DevOps integration entities — pure data, no Qt/DB/network.

Kept UI- and storage-agnostic so the sync/dedup logic that consumes these
objects (in the controller) stays unit-testable without a display or a network.
"""
from __future__ import annotations

from dataclasses import dataclass

from models.task import Priority


@dataclass
class AzureConfig:
    """User-entered connection settings (the PAT is NOT stored here — see
    ``services.credentials``). ``reviewer_id`` is the authenticated user's GUID,
    auto-detected from the token and cached so sync can filter by it."""
    enabled: bool = False
    organization: str = ""          # "myorg" or "https://dev.azure.com/myorg"
    project: str = ""               # optional; "" means all projects in the org
    reviewer_id: str = ""           # cached identity GUID
    poll_minutes: int = 15
    # Which pull requests become tasks. Both default off — a user opts in per source.
    create_for_reviewer: bool = False   # PRs where you are a reviewer
    create_for_author: bool = False     # PRs you created
    # Priority assigned to each PR task source.
    priority_required: Priority = Priority.HIGH
    priority_optional: Priority = Priority.MEDIUM
    priority_author: Priority = Priority.MEDIUM

    @property
    def org_slug(self) -> str:
        """Bare organization name, stripped of any dev.azure.com URL wrapper."""
        org = self.organization.strip().rstrip("/")
        for prefix in ("https://dev.azure.com/", "http://dev.azure.com/",
                       "https://", "http://"):
            if org.startswith(prefix):
                org = org[len(prefix):]
                break
        # Legacy "myorg.visualstudio.com" form.
        if org.endswith(".visualstudio.com"):
            org = org[: -len(".visualstudio.com")]
        return org.split("/")[0]

    def is_configured(self) -> bool:
        return bool(self.enabled and self.org_slug)

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
class PullRequest:
    """One Azure DevOps pull request, projected to the fields the app needs."""
    pr_id: int
    title: str
    repository: str = ""
    repository_id: str = ""         # GUID; needed to query the PR's comment threads
    project: str = ""
    author: str = ""
    url: str = ""
    status: str = "active"          # active | completed | abandoned
    is_required: bool = False       # is the current user a *required* reviewer?
    is_author: bool = False         # did the current user create this PR?
    # The current user's review vote on this PR, from the Azure reviewer entry:
    # 10 approved, 5 approved-with-suggestions, 0 no vote, -5 waiting, -10 rejected.
    # Only meaningful for review-source PRs; stays 0 for authored ones.
    reviewer_vote: int = 0
    # Count of unresolved (active) comment threads. Only fetched for authored PRs;
    # a positive value pins the PR's task to the top as Urgent (see the controller).
    unresolved_comment_count: int = 0

    @property
    def review_completed(self) -> bool:
        """True once the current user has cast any review vote (approved,
        approved-with-suggestions, waiting, or rejected). Azure resets the vote
        to 0 on a new push when the reset-votes policy is on, which clears this."""
        return self.reviewer_vote != 0


def pr_key(organization: str, pr_id: int, source: str = "review") -> str:
    """Stable dedup key. PR ids are unique within an organization; the ``source``
    prefix ("review" | "author") keeps each task source isolated so syncing one
    never auto-completes the other's tasks."""
    return f"{source}:{organization}:{pr_id}"


def pr_to_task_fields(pr: PullRequest, config: "AzureConfig | None" = None) -> dict:
    """Map a pull request onto the fields used to create its task.

    Priority is taken from ``config`` (falling back to the defaults, i.e. required
    reviews High / optional Medium / authored Medium). The PR role is noted in the
    description.
    """
    if config is None:
        config = AzureConfig()
    # Name the repository in the title (e.g. "Your Contoso PR #123: …")
    # so PRs from different repos are distinguishable at a glance; omitted when
    # the repository is unknown.
    repo_part = f"{pr.repository} " if pr.repository else ""
    if pr.is_author:
        role = "author"
        priority = config.priority_author
        title = f"Your {repo_part}PR #{pr.pr_id}: {pr.title}"
    elif pr.is_required:
        role = "required"
        priority = config.priority_required
        title = f"Review {repo_part}PR #{pr.pr_id}: {pr.title}"
    else:
        role = "optional"
        priority = config.priority_optional
        title = f"Review {repo_part}PR #{pr.pr_id}: {pr.title}"

    role_line = "You are the author" if pr.is_author else f"Your review: {role}"
    lines = [f"Pull request #{pr.pr_id}", role_line]
    if pr.repository:
        repo = f"{pr.project}/{pr.repository}" if pr.project else pr.repository
        lines.append(f"Repository: {repo}")
    if pr.author:
        lines.append(f"Author: {pr.author}")
    # Surface the full PR link on its own labelled line so it is easy to
    # copy-paste out of the task description.
    if pr.url:
        lines.append(f"Link: {pr.url}")
    return {
        "title": title,
        "description": "\n".join(lines),
        "priority": priority,
        "category": "Azure PR",
        "deadline": None,
    }
