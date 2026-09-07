"""Minimal Azure DevOps REST client for reading review-requested pull requests.

Uses only the standard library (``urllib``) so the app needs no HTTP dependency.
The JSON -> :class:`PullRequest` parsing lives in :meth:`AzureDevOpsClient._parse_prs`,
kept pure and separate from the network so it can be unit-tested with a fixture
payload and no live connection.

Authentication is a Personal Access Token sent as HTTP Basic auth with an empty
username (the Azure DevOps convention): ``Authorization: Basic base64(":<PAT>")``.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

from models.integration import PullRequest

_API_VERSION = "7.1"
_TIMEOUT = 20  # seconds; keeps a hung network from blocking the worker forever


class AzureError(Exception):
    """Any failure talking to Azure DevOps (network, auth, or bad response)."""


class AzureDevOpsClient:
    def __init__(self, organization: str, pat: str, project: str = "") -> None:
        self._org = organization.strip()
        self._pat = pat or ""
        self._project = project.strip()

    # ---- HTTP ------------------------------------------------------------
    def _auth_header(self) -> str:
        token = base64.b64encode(f":{self._pat}".encode()).decode()
        return f"Basic {token}"

    def _get(self, url: str) -> dict:
        request = urllib.request.Request(url, method="GET")
        request.add_header("Authorization", self._auth_header())
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # 401/403/404/...
            detail = "authentication failed" if exc.code in (401, 203) else exc.reason
            raise AzureError(f"Azure DevOps returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise AzureError(f"Could not reach Azure DevOps: {exc.reason}") from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise AzureError(f"Unexpected error contacting Azure DevOps: {exc}") from exc

        # Azure returns an HTML sign-in page (HTTP 200) when the PAT is invalid.
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise AzureError(
                "Unexpected response from Azure DevOps (check the PAT and its scope)."
            ) from exc

    def _org_base(self) -> str:
        return f"https://dev.azure.com/{urllib.parse.quote(self._org)}"

    # ---- public API ------------------------------------------------------
    def get_authenticated_user_id(self) -> str:
        """The identity GUID of the token's owner, used to filter PRs by reviewer."""
        data = self._get(f"{self._org_base()}/_apis/connectionData")
        user = data.get("authenticatedUser") or {}
        user_id = user.get("id")
        if not user_id:
            raise AzureError("Could not determine the authenticated user from the token.")
        return user_id

    def _prs_base(self) -> str:
        base = self._org_base()
        if self._project:
            base = f"{base}/{urllib.parse.quote(self._project)}"
        return base

    def list_review_requested_prs(self, reviewer_id: str) -> List[PullRequest]:
        """Active PRs where ``reviewer_id`` is listed as a reviewer."""
        query = urllib.parse.urlencode({
            "searchCriteria.status": "active",
            "searchCriteria.reviewerId": reviewer_id,
            "api-version": _API_VERSION,
        })
        data = self._get(f"{self._prs_base()}/_apis/git/pullrequests?{query}")
        return self._parse_prs(data, reviewer_id)

    def list_created_prs(self, creator_id: str) -> List[PullRequest]:
        """Active PRs authored by ``creator_id`` (the token owner's GUID)."""
        query = urllib.parse.urlencode({
            "searchCriteria.status": "active",
            "searchCriteria.creatorId": creator_id,
            "api-version": _API_VERSION,
        })
        data = self._get(f"{self._prs_base()}/_apis/git/pullrequests?{query}")
        return self._parse_created_prs(data)

    def test_connection(self) -> tuple[bool, str]:
        """Return (ok, message). Never raises — safe to call from the UI."""
        if not self._org:
            return False, "Enter an organization first."
        if not self._pat:
            return False, "Enter a Personal Access Token first."
        try:
            user_id = self.get_authenticated_user_id()
        except AzureError as exc:
            return False, str(exc)
        return True, f"Connected. Reviewer identity: {user_id}"

    # ---- parsing (pure) --------------------------------------------------
    @staticmethod
    def _build_pr(item: dict, *, is_required: bool, is_author: bool) -> PullRequest:
        """Project one raw Azure PR item onto a :class:`PullRequest`."""
        repo = item.get("repository") or {}
        project = (repo.get("project") or {}).get("name", "")
        created_by = item.get("createdBy") or {}
        web = ((item.get("_links") or {}).get("web") or {}).get("href", "")
        return PullRequest(
            pr_id=item.get("pullRequestId"),
            title=item.get("title", ""),
            repository=repo.get("name", ""),
            project=project,
            author=created_by.get("displayName", ""),
            url=web,
            status=item.get("status", "active"),
            is_required=is_required,
            is_author=is_author,
        )

    @classmethod
    def _parse_prs(cls, payload: dict, reviewer_id: str) -> List[PullRequest]:
        """Build PullRequests for every PR where the given reviewer is listed —
        whether they are a required or an optional reviewer. ``is_required``
        records which. Pure: no network, safe to unit-test."""
        result: List[PullRequest] = []
        for item in payload.get("value", []):
            matched = None
            for reviewer in item.get("reviewers", []):
                if reviewer.get("id") == reviewer_id:
                    matched = reviewer
                    break
            if matched is None:
                continue
            result.append(
                cls._build_pr(
                    item,
                    is_required=bool(matched.get("isRequired")),
                    is_author=False,
                )
            )
        return result

    @classmethod
    def _parse_created_prs(cls, payload: dict) -> List[PullRequest]:
        """Build PullRequests for every authored PR in the payload (``is_author``
        set). Pure: no network, safe to unit-test."""
        return [
            cls._build_pr(item, is_required=False, is_author=True)
            for item in payload.get("value", [])
        ]
