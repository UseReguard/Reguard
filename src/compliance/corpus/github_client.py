"""Thin wrapper around the GitHub REST API.

Uses the ``gh`` CLI for auth — same pattern as the existing
``scripts/collect_eu_ai_repos.py``. The CLI transparently re-uses the
user's ``gh auth login`` session, so no token juggling is needed.

Two functions are exposed:

- ``search_repositories(query, per_page, page)`` — wraps ``GET search/repositories``
- ``get_repository(full_name)`` — wraps ``GET repos/{owner}/{repo}`` for
  refreshing metadata for a single repository

Both raise ``GitHubAPIError`` on failure so the caller can decide whether
to retry, skip, or stop.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("repo_corpus.github")

# Keep the page count modest. 30 results × 10 pages × ~17 default queries
# ≈ 5,100 rows of search output per full run — already past the
# user-spec target of ~5,000 discovered candidates.
DEFAULT_PER_PAGE = 30
DEFAULT_MAX_PAGES = 10
# Stay under GitHub's unauthenticated limit (10 req/min) by sleeping
# between calls. With a `gh auth` token this can be dropped to ~0.5s.
INTER_PAGE_SLEEP_SECONDS = 2.0


class GitHubAPIError(RuntimeError):
    """Raised when the ``gh`` API call fails or returns malformed JSON."""


@dataclass
class SearchPage:
    total_count: int
    items: list[dict]


def _run_gh(endpoint: str, params: Optional[dict] = None) -> dict:
    # gh's `api` command takes one URL argument. Query-string parameters
    # must therefore be merged into the URL itself; using `-f` would split
    # on whitespace inside values like `topic:ai-agent language:Python`.
    url = endpoint
    if params:
        from urllib.parse import urlencode
        qs = urlencode({k: str(v) for k, v in params.items()})
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"

    cmd = ["gh", "api", url]
    log.debug("gh api %s", url)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise GitHubAPIError(f"timeout calling {endpoint}") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()[:300]
        raise GitHubAPIError(f"gh api {endpoint} failed: {stderr}")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GitHubAPIError(f"gh api {endpoint} returned non-JSON: {proc.stdout[:200]}") from exc


def search_repositories(
    query: str,
    *,
    per_page: int = DEFAULT_PER_PAGE,
    page: int = 1,
    sort: str = "stars",
    order: str = "desc",
) -> SearchPage:
    """Return one page of repository search results."""
    payload = _run_gh(
        "search/repositories",
        params={
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": per_page,
            "page": page,
        },
    )
    return SearchPage(
        total_count=int(payload.get("total_count", 0)),
        items=list(payload.get("items", []) or []),
    )


def iter_search(
    query: str,
    *,
    per_page: int = DEFAULT_PER_PAGE,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> tuple[int, list[dict]]:
    """Iterate every result page for a single query, returning (total, all_items).

    Sleeps between pages to stay under rate limits. Stops early if a page
    comes back partial (i.e. GitHub has nothing left to give us).
    """
    items: list[dict] = []
    total = 0
    for page in range(1, max_pages + 1):
        result = search_repositories(query, per_page=per_page, page=page)
        total = result.total_count
        page_items = result.items
        if not page_items:
            break
        items.extend(page_items)
        if len(page_items) < per_page:
            break
        if page < max_pages:
            time.sleep(INTER_PAGE_SLEEP_SECONDS)
    return total, items


def get_repository(full_name: str) -> Optional[dict]:
    """Fetch a single repository's metadata. Returns None if not found."""
    try:
        return _run_gh(f"repos/{full_name}")
    except GitHubAPIError as exc:
        if "404" in str(exc):
            return None
        raise
