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


@dataclass
class PullRequest:
    """One Azure DevOps pull request, projected to the fields the app needs."""
    pr_id: int
    title: str
    repository: str = ""
    project: str = ""
    author: str = ""
    url: str = ""
    status: str = "active"          # active | completed | abandoned
    is_required: bool = False       # is the current user a *required* reviewer?


def pr_key(organization: str, pr_id: int) -> str:
    """Stable dedup key. PR ids are unique within an organization."""
    return f"{organization}:{pr_id}"


def pr_to_task_fields(pr: PullRequest) -> dict:
    """Map a pull request onto the fields used to create its task.

    Required reviews are High priority; optional reviews are Medium. The reviewer
    role is also noted in the description.
    """
    role = "required" if pr.is_required else "optional"
    lines = [f"Pull request #{pr.pr_id}", f"Your review: {role}"]
    if pr.repository:
        repo = f"{pr.project}/{pr.repository}" if pr.project else pr.repository
        lines.append(f"Repository: {repo}")
    if pr.author:
        lines.append(f"Author: {pr.author}")
    if pr.url:
        lines.append(pr.url)
    return {
        "title": f"Review PR #{pr.pr_id}: {pr.title}",
        "description": "\n".join(lines),
        "priority": Priority.HIGH if pr.is_required else Priority.MEDIUM,
        "category": "Azure PR",
        "deadline": None,
    }
