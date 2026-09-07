"""Minimal Linear (linear.app) GraphQL client.

Uses only the standard library (``urllib``) so the app needs no HTTP dependency,
mirroring :mod:`services.azure_client`. The JSON -> dataclass parsing lives in
pure static methods, kept separate from the network so they can be unit-tested
with a fixture payload and no live connection.

Authentication is a Linear personal API key sent verbatim in the
``Authorization`` header (Linear does not use a ``Bearer`` prefix for personal
keys).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import List, Optional

from models.linear import LinearIssue

_ENDPOINT = "https://api.linear.app/graphql"
_TIMEOUT = 20  # seconds; keeps a hung network from blocking the worker forever

# Rate-limit handling mirrors the Azure client: retry a 429 a bounded number of
# times, honouring Retry-After, clamped so the worker thread can't stall for long.
_MAX_ATTEMPTS = 3
_DEFAULT_RETRY_WAIT = 5
_MAX_RETRY_WAIT = 30

_ISSUE_FIELDS = (
    "id identifier title url "
    "state { id name type } "
    "labels { nodes { name } }"
)


class LinearError(Exception):
    """Any failure talking to Linear (network, auth, or bad response)."""


class LinearClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key or ""

    # ---- HTTP ------------------------------------------------------------
    @staticmethod
    def _retry_after_seconds(exc: urllib.error.HTTPError) -> int:
        raw = exc.headers.get("Retry-After") if exc.headers else None
        try:
            wait = int(str(raw).strip())
        except (TypeError, ValueError):
            wait = _DEFAULT_RETRY_WAIT
        return max(1, min(wait, _MAX_RETRY_WAIT))

    def _post(self, query: str, variables: Optional[dict] = None) -> dict:
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(_ENDPOINT, data=body, method="POST")
        request.add_header("Authorization", self._api_key)
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        for attempt in range(_MAX_ATTEMPTS):
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                    raw = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:  # 400/401/429/...
                if exc.code == 429:
                    if attempt < _MAX_ATTEMPTS - 1:
                        time.sleep(self._retry_after_seconds(exc))
                        continue
                    raise LinearError(
                        "Linear is rate limiting requests (HTTP 429). "
                        "Try again shortly or increase the poll interval."
                    ) from exc
                detail = "authentication failed" if exc.code in (401, 403) else exc.reason
                raise LinearError(f"Linear returned HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                raise LinearError(f"Could not reach Linear: {exc.reason}") from exc
            except Exception as exc:  # pragma: no cover - defensive
                raise LinearError(f"Unexpected error contacting Linear: {exc}") from exc

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LinearError(
                    "Unexpected response from Linear (check the API key)."
                ) from exc
            if payload.get("errors"):
                raise LinearError(self._format_errors(payload["errors"]))
            return payload.get("data") or {}
        # Unreachable: the loop either returns or raises on every path.
        raise LinearError("Linear request failed after retries.")

    @staticmethod
    def _format_errors(errors: list) -> str:
        messages = [str(e.get("message", "")) for e in errors if isinstance(e, dict)]
        joined = "; ".join(m for m in messages if m)
        return f"Linear API error: {joined}" if joined else "Linear API error."

    # ---- public API ------------------------------------------------------
    def test_connection(self) -> tuple[bool, str]:
        """Return (ok, message). Never raises — safe to call from the UI."""
        if not self._api_key:
            return False, "Enter a Linear API key first."
        try:
            data = self._post("{ viewer { id name } }")
        except LinearError as exc:
            return False, str(exc)
        viewer = data.get("viewer") or {}
        name = viewer.get("name") or viewer.get("id") or "unknown"
        return True, f"Connected as {name}."

    def list_teams(self) -> List[dict]:
        """Every team the key can see, as ``{id, key, name}`` dicts."""
        data = self._post("{ teams(first: 250) { nodes { id key name } } }")
        return list(((data.get("teams") or {}).get("nodes")) or [])

    def list_workflow_states(self, team_ids: List[str]) -> List[dict]:
        """Workflow states for the given teams, as ``{id, name, type}`` dicts."""
        if not team_ids:
            return []
        query = (
            "query($teams:[ID!]){ workflowStates(first:250,"
            " filter:{team:{id:{in:$teams}}}) { nodes { id name type } } }"
        )
        data = self._post(query, {"teams": list(team_ids)})
        return list(((data.get("workflowStates") or {}).get("nodes")) or [])

    def list_labels(self, team_ids: List[str]) -> List[str]:
        """Distinct label names available across the given teams."""
        if not team_ids:
            return []
        query = (
            "query($teams:[ID!]){ issueLabels(first:250,"
            " filter:{team:{id:{in:$teams}}}) { nodes { name } } }"
        )
        data = self._post(query, {"teams": list(team_ids)})
        nodes = ((data.get("issueLabels") or {}).get("nodes")) or []
        return sorted({n.get("name", "") for n in nodes if n.get("name")})

    def list_assigned_issues(
        self, team_ids: List[str], state_ids: List[str]
    ) -> List[LinearIssue]:
        """Issues assigned to the authenticated user in the given teams/states.

        Pages through the whole result set (Linear caps ``first`` at 250).
        """
        if not team_ids or not state_ids:
            return []
        query = (
            "query($teams:[ID!],$states:[ID!],$after:String){"
            " issues(first:250, after:$after, filter:{"
            " assignee:{isMe:{eq:true}},"
            " team:{id:{in:$teams}},"
            " state:{id:{in:$states}} }) {"
            f" nodes {{ {_ISSUE_FIELDS} }}"
            " pageInfo { hasNextPage endCursor } } }"
        )
        issues: List[LinearIssue] = []
        after: Optional[str] = None
        # Bound the pagination loop defensively so a misbehaving API can't spin.
        for _ in range(50):
            data = self._post(
                query, {"teams": list(team_ids), "states": list(state_ids), "after": after}
            )
            block = data.get("issues") or {}
            issues.extend(self._parse_issues(block))
            page = block.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            after = page.get("endCursor")
            if not after:
                break
        return issues

    # ---- parsing (pure) --------------------------------------------------
    @staticmethod
    def _parse_issues(block: dict) -> List[LinearIssue]:
        """Project an ``issues`` GraphQL block onto :class:`LinearIssue` objects.
        Pure: no network, safe to unit-test with a fixture payload."""
        result: List[LinearIssue] = []
        for node in block.get("nodes", []) or []:
            state = node.get("state") or {}
            labels = ((node.get("labels") or {}).get("nodes")) or []
            result.append(
                LinearIssue(
                    id=node.get("id", ""),
                    identifier=node.get("identifier", ""),
                    title=node.get("title", ""),
                    url=node.get("url", ""),
                    state_id=state.get("id", ""),
                    state_name=state.get("name", ""),
                    state_type=state.get("type", ""),
                    label_names=[l.get("name", "") for l in labels if l.get("name")],
                )
            )
        return result
