"""Minimal GitHub GraphQL client for reading review-requested and authored PRs.

Uses only the standard library (``urllib``) so the app needs no HTTP dependency,
mirroring :mod:`services.azure_client` / :mod:`services.linear_client`. The JSON ->
:class:`GitHubPullRequest` parsing lives in a pure static method, kept separate from
the network so it can be unit-tested with a fixture payload and no live connection.

Authentication is a personal access token sent as ``Authorization: Bearer <token>``.
GraphQL is used (not REST search) because unresolved review threads and the review
decision are only available there, and one query returns everything per source.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import List, Optional

from models.github import GitHubConfig, GitHubPullRequest

_ENDPOINT = "https://api.github.com/graphql"
_TIMEOUT = 20  # seconds; keeps a hung network from blocking the worker forever
_USER_AGENT = "TaskManager"  # GitHub rejects requests without a User-Agent

# Rate-limit handling mirrors the other clients: retry a bounded number of times,
# honouring Retry-After, clamped so the worker thread can't stall for long. GitHub
# signals its secondary (abuse) limit with HTTP 403/429 plus ``Retry-After``.
_MAX_ATTEMPTS = 3
_DEFAULT_RETRY_WAIT = 5
_MAX_RETRY_WAIT = 30

# Pagination: bounded so a huge result set can't spin the worker.
_PAGE_SIZE = 50
_MAX_PAGES = 10  # up to 500 PRs per source

_PR_FIELDS = (
    "number title url isDraft reviewDecision "
    "repository { nameWithOwner } author { login }"
)
_THREAD_FIELDS = " reviewThreads(first: 100) { nodes { isResolved } }"


class GitHubError(Exception):
    """Any failure talking to GitHub (network, auth, or bad response)."""


def token_is_valid(token: str) -> bool:
    """True for a non-empty token with no whitespace or control characters. Anything
    else can't be a real token and would make ``http.client`` raise an error whose
    text echoes the Authorization header (i.e. the token)."""
    return bool(token) and token.isascii() and token.isprintable() and not any(
        c.isspace() for c in token
    )


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._token = token or ""

    # ---- HTTP ------------------------------------------------------------
    @staticmethod
    def _retry_after_seconds(exc: urllib.error.HTTPError) -> Optional[int]:
        """Seconds to wait before retrying, or None when the response carries no
        ``Retry-After`` (a plain 403 is then an auth/permission failure, not a
        rate limit)."""
        raw = exc.headers.get("Retry-After") if exc.headers else None
        if raw is None:
            # Secondary limits sometimes send only the reset time (epoch seconds).
            reset = exc.headers.get("X-RateLimit-Reset") if exc.headers else None
            try:
                return max(1, min(int(str(reset).strip()) - int(time.time()), _MAX_RETRY_WAIT))
            except (TypeError, ValueError):
                return None
        try:
            wait = int(str(raw).strip())
        except (TypeError, ValueError):
            wait = _DEFAULT_RETRY_WAIT
        return max(1, min(wait, _MAX_RETRY_WAIT))

    def _post(self, query: str, variables: Optional[dict] = None) -> dict:
        if not token_is_valid(self._token):
            raise GitHubError(
                "The access token is empty or contains spaces/control characters — "
                "paste it again."
            )
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(_ENDPOINT, data=body, method="POST")
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", _USER_AGENT)
        for attempt in range(_MAX_ATTEMPTS):
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                    raw = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:  # 401/403/429/...
                if exc.code == 403 and (
                    exc.headers.get("X-RateLimit-Remaining") if exc.headers else None
                ) == "0":
                    raise GitHubError(self._RATE_LIMIT_MESSAGE) from exc
                if exc.code >= 500:  # transient GraphQL/search timeouts (502/503/504)
                    if attempt < _MAX_ATTEMPTS - 1:
                        time.sleep(_DEFAULT_RETRY_WAIT)
                        continue
                    raise GitHubError(
                        f"GitHub returned HTTP {exc.code}: {exc.reason}"
                    ) from exc
                wait = self._retry_after_seconds(exc) if exc.code in (403, 429) else None
                if wait is not None or exc.code == 429:
                    if attempt < _MAX_ATTEMPTS - 1:
                        time.sleep(wait or _DEFAULT_RETRY_WAIT)
                        continue
                    raise GitHubError(self._RATE_LIMIT_MESSAGE) from exc
                detail = (
                    "authentication failed (check the token and its scopes)"
                    if exc.code in (401, 403) else exc.reason
                )
                raise GitHubError(f"GitHub returned HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                raise GitHubError(f"Could not reach GitHub: {exc.reason}") from exc
            except Exception as exc:  # pragma: no cover - defensive
                # Name the type only: the text of some errors echoes request headers.
                raise GitHubError(
                    f"Unexpected error contacting GitHub ({type(exc).__name__})."
                ) from exc

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise GitHubError(
                    "Unexpected response from GitHub (check the token)."
                ) from exc
            if payload.get("errors"):
                raise GitHubError(self._format_errors(payload["errors"]))
            return payload.get("data") or {}
        # Unreachable: the loop either returns or raises on every path.
        raise GitHubError("GitHub request failed after retries.")

    _RATE_LIMIT_MESSAGE = (
        "GitHub is rate limiting requests. "
        "Try again shortly or increase the poll interval."
    )

    @classmethod
    def _format_errors(cls, errors: list) -> str:
        if any(isinstance(e, dict) and e.get("type") == "RATE_LIMITED" for e in errors):
            return cls._RATE_LIMIT_MESSAGE
        messages = [str(e.get("message", "")) for e in errors if isinstance(e, dict)]
        joined = "; ".join(m for m in messages if m)
        return f"GitHub API error: {joined}" if joined else "GitHub API error."

    # ---- public API ------------------------------------------------------
    def get_viewer_login(self) -> str:
        """The login of the token's owner, used to build the PR search qualifiers."""
        data = self._post("{ viewer { login } }")
        login = (data.get("viewer") or {}).get("login")
        if not login:
            raise GitHubError("Could not determine the authenticated user from the token.")
        return login

    def list_review_requested_prs(self, login: str, owner: str = "") -> List[GitHubPullRequest]:
        """Open PRs where ``login``'s review is requested (own PRs excluded)."""
        query = f"is:pr is:open archived:false review-requested:{login} -author:{login}"
        return self._search(self._with_owner(query, owner), is_author=False)

    def list_created_prs(self, login: str, owner: str = "") -> List[GitHubPullRequest]:
        """Open PRs authored by ``login``, with their unresolved review-thread counts."""
        query = f"is:pr is:open archived:false author:{login}"
        return self._search(self._with_owner(query, owner), is_author=True)

    @staticmethod
    def _with_owner(query: str, owner: str) -> str:
        # Defence in depth: the view/model validate this too, but a stray space or
        # qualifier here would silently change what the search matches.
        if owner and not GitHubConfig(owner=owner).owner_is_valid:
            raise GitHubError("The organization name is invalid.")
        return f"{query} org:{owner}" if owner else query

    def test_connection(self) -> tuple[bool, str]:
        """Return (ok, message). Never raises — safe to call from the UI."""
        if not self._token:
            return False, "Enter a GitHub access token first."
        try:
            login = self.get_viewer_login()
        except GitHubError as exc:
            return False, str(exc)
        return True, f"Connected as {login}."

    def _search(self, search_query: str, *, is_author: bool) -> List[GitHubPullRequest]:
        fields = _PR_FIELDS + (_THREAD_FIELDS if is_author else "")
        query = (
            "query($q: String!, $n: Int!, $after: String) {"
            " search(query: $q, type: ISSUE, first: $n, after: $after) {"
            " pageInfo { hasNextPage endCursor }"
            f" nodes {{ ... on PullRequest {{ {fields} }} }} }} }}"
        )
        result: List[GitHubPullRequest] = []
        cursor: Optional[str] = None
        for page_no in range(_MAX_PAGES):
            data = self._post(
                query, {"q": search_query, "n": _PAGE_SIZE, "after": cursor}
            )
            search = data.get("search") or {}
            result.extend(self._parse_prs(search, is_author=is_author))
            page = search.get("pageInfo") or {}
            if not page.get("hasNextPage") or not page.get("endCursor"):
                break
            if page_no == _MAX_PAGES - 1:
                # A truncated list would look like "these PRs closed" to the sync
                # and mass-complete their tasks, so fail loudly instead.
                raise GitHubError(
                    f"More than {_MAX_PAGES * _PAGE_SIZE} matching pull requests — "
                    "narrow the sync with the Organization filter."
                )
            cursor = page["endCursor"]
        return result

    # ---- parsing (pure) --------------------------------------------------
    @staticmethod
    def _parse_prs(search: dict, *, is_author: bool) -> List[GitHubPullRequest]:
        """Build PRs from a ``search`` payload. Non-PR nodes (empty ``{}`` from the
        inline fragment) are skipped. Pure: no network, safe to unit-test."""
        result: List[GitHubPullRequest] = []
        for node in search.get("nodes") or []:
            if not node or node.get("number") is None:
                continue
            unresolved = 0
            if is_author:
                threads = ((node.get("reviewThreads") or {}).get("nodes")) or []
                unresolved = sum(1 for t in threads if not t.get("isResolved"))
            result.append(
                GitHubPullRequest(
                    number=node["number"],
                    title=node.get("title", ""),
                    repository=(node.get("repository") or {}).get("nameWithOwner", ""),
                    author=(node.get("author") or {}).get("login", ""),
                    url=node.get("url", ""),
                    is_author=is_author,
                    is_draft=bool(node.get("isDraft")),
                    changes_requested=(
                        is_author and node.get("reviewDecision") == "CHANGES_REQUESTED"
                    ),
                    unresolved_comment_count=unresolved,
                )
            )
        return result
