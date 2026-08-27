"""Discovery pipeline: search → classify → persist.

The pipeline runs multiple GitHub search queries, dedupes results by
``github_id`` (which is the canonical unique key from GitHub), filters
to ``primary_language == "Python"``, classifies each row with the
heuristic in :mod:`classifier`, and writes new rows to
``agent_repositories``.

Existing rows are never overwritten by ``discover`` — they get refreshed
by :func:`refresh_metadata`. This is deliberate: discovery's job is to
*grow* the corpus, refresh's job is to *update* it.

Both functions return a small ``RunStats`` dataclass so the CLI can
print a one-line summary at the end.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from compliance.db import session_scope
from compliance.models import AgentRepository
from compliance.corpus import classifier as cls
from compliance.corpus.github_client import iter_search, get_repository, GitHubAPIError
from compliance.corpus.queries import all_queries, parse_user_query

log = logging.getLogger("repo_corpus.pipeline")


@dataclass
class RunStats:
    queries_run: int = 0
    fetched: int = 0                # items returned by GitHub
    after_lang_filter: int = 0      # items that had Python as primary lang
    after_dedup: int = 0            # items not already in the DB
    inserted: int = 0
    classified: dict[str, int] = field(default_factory=lambda: {
        cls.STATUS_ACCEPTED: 0,
        cls.STATUS_CANDIDATE: 0,
        cls.STATUS_REJECTED: 0,
        cls.STATUS_UNKNOWN: 0,
    })

    def merge(self, other: "RunStats") -> None:
        self.queries_run += other.queries_run
        self.fetched += other.fetched
        self.after_lang_filter += other.after_lang_filter
        self.after_dedup += other.after_dedup
        self.inserted += other.inserted
        for k, v in other.classified.items():
            self.classified[k] = self.classified.get(k, 0) + v


@dataclass
class ReclassifyStats:
    """Per-status deltas from a reclassify run. ``status_changes`` counts
    rows whose ``relevance_status`` field value changed; ``category_changes``
    counts rows whose ``agent_category`` changed."""
    scanned: int = 0
    updated: int = 0               # rows where at least one field changed
    status_changes: int = 0
    category_changes: int = 0
    before: dict[str, int] = field(default_factory=dict)
    after:  dict[str, int] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _is_python(repo: dict) -> bool:
    return (repo.get("language") or "").strip() == "Python"


def _repo_to_row(repo: dict, *, discovery_query: str, classification: cls.Classification) -> dict:
    """Map a GitHub repo dict + classification into a dict matching AgentRepository columns."""
    license_spdx = None
    lic = repo.get("license") or {}
    if isinstance(lic, dict):
        license_spdx = lic.get("spdx_id")

    return dict(
        github_id=int(repo["id"]),
        full_name=repo["full_name"],
        owner=(repo.get("owner") or {}).get("login") or repo["full_name"].split("/")[0],
        name=repo.get("name") or repo["full_name"].split("/")[-1],
        html_url=repo.get("html_url") or f"https://github.com/{repo['full_name']}",
        clone_url=repo.get("clone_url"),
        description=repo.get("description"),
        primary_language=repo.get("language"),
        topics_json=json.dumps(repo.get("topics") or []),
        license_spdx=license_spdx,
        stars=int(repo.get("stargazers_count") or 0),
        forks=int(repo.get("forks_count") or 0),
        github_created_at=_parse_iso(repo.get("created_at")),
        github_updated_at=_parse_iso(repo.get("updated_at")),
        github_pushed_at=_parse_iso(repo.get("pushed_at")),
        archived=bool(repo.get("archived")),
        fork=bool(repo.get("fork")),
        agent_category=classification.agent_category,
        relevance_status=classification.relevance_status,
        relevance_confidence=classification.confidence,
        relevance_reason=classification.reason,
        discovery_query=discovery_query,
        discovered_at=datetime.now(timezone.utc).replace(tzinfo=None),
        last_metadata_refresh=datetime.now(timezone.utc).replace(tzinfo=None),
        enabled=(classification.relevance_status != cls.STATUS_REJECTED),
    )


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # GitHub sends "...Z" or "...+00:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _existing_ids(session, ids: Iterable[int]) -> set[int]:
    ids = list(ids)
    if not ids:
        return set()
    rows = session.execute(
        select(AgentRepository.github_id).where(AgentRepository.github_id.in_(ids))
    ).all()
    return {r[0] for r in rows}


# ──────────────────────────────────────────────────────────────────────
# Public entry points
# ──────────────────────────────────────────────────────────────────────
def discover(
    *,
    queries: Optional[list[str]] = None,
    min_stars: int = 0,
    max_total: Optional[int] = None,
) -> RunStats:
    """Run every query, dedupe, classify, insert.

    Args:
        queries:     override the default query list. Each string is sent
                     to GitHub search as-is.
        min_stars:   drop items below this star count before classification.
        max_total:   cap on rows inserted in this run (excluding rejects
                     which still get inserted as audit trail).
    """
    raw_queries = queries if queries is not None else all_queries()
    stats = RunStats()

    new_rows: list[tuple[dict, str, cls.Classification]] = []
    # Pre-collect everything we want to insert so we can do one DB check.
    seen_github_ids: set[int] = set()

    for query in raw_queries:
        if max_total is not None and len(new_rows) >= max_total:
            break
        log.info("query: %s", query)
        try:
            _total, items = iter_search(query)
        except GitHubAPIError as exc:
            log.warning("  skip query (github api error): %s", exc)
            continue
        stats.queries_run += 1
        stats.fetched += len(items)
        log.info("  fetched %d items", len(items))

        for repo in items:
            if max_total is not None and len(new_rows) >= max_total:
                break
            gh_id = repo.get("id")
            if gh_id is None or gh_id in seen_github_ids:
                continue
            if not _is_python(repo):
                continue
            stats.after_lang_filter += 1
            if min_stars > 0 and int(repo.get("stargazers_count") or 0) < min_stars:
                continue
            seen_github_ids.add(gh_id)
            classification = cls.classify(repo)
            stats.classified[classification.relevance_status] = \
                stats.classified.get(classification.relevance_status, 0) + 1
            new_rows.append((repo, query, classification))

    # Dedupe against the DB.
    with session_scope() as session:
        existing = _existing_ids(session, (r[0]["id"] for r in new_rows))
    stats.after_dedup = len(new_rows) - len(existing & seen_github_ids)
    to_insert = [(r, q, c) for (r, q, c) in new_rows if r["id"] not in existing]
    log.info("inserting %d new rows (skipped %d already-known)", len(to_insert), len(new_rows) - len(to_insert))

    for repo, query, classification in to_insert:
        try:
            with session_scope() as session:
                row = AgentRepository(**_repo_to_row(repo, discovery_query=query, classification=classification))
                session.add(row)
            stats.inserted += 1
        except IntegrityError as exc:
            # Lost a race against another writer; not an error.
            log.debug("insert skipped due to unique constraint: %s", exc.orig)
        except Exception as exc:
            log.warning("insert failed for %s: %s", repo.get("full_name"), exc)

    return stats


def refresh_metadata(*, full_name: Optional[str] = None, limit: int = 100) -> RunStats:
    """Refresh metadata for one or many stored repositories.

    If ``full_name`` is given, only that repository is refreshed.
    Otherwise the ``limit`` oldest-refreshed rows are pulled.
    """
    stats = RunStats()

    with session_scope() as session:
        if full_name:
            stmt = select(AgentRepository).where(AgentRepository.full_name == full_name)
        else:
            stmt = (
                select(AgentRepository)
                .order_by(AgentRepository.last_metadata_refresh.asc().nulls_first())
                .limit(limit)
            )
        rows = session.execute(stmt).scalars().all()
        target_ids = [(r.id, r.full_name) for r in rows]

    for row_id, fname in target_ids:
        try:
            data = get_repository(fname)
        except GitHubAPIError as exc:
            log.warning("refresh %s failed: %s", fname, exc)
            continue
        if data is None:
            log.info("refresh %s: repo no longer exists on GitHub", fname)
            continue
        # Preserve the discovery-time classification; only metadata changes.
        with session_scope() as session:
            row = session.get(AgentRepository, row_id)
            if row is None:
                continue
            row.description = data.get("description")
            row.primary_language = data.get("language")
            row.topics_json = json.dumps(data.get("topics") or [])
            lic = data.get("license") or {}
            row.license_spdx = lic.get("spdx_id") if isinstance(lic, dict) else None
            row.stars = int(data.get("stargazers_count") or 0)
            row.forks = int(data.get("forks_count") or 0)
            row.github_created_at = _parse_iso(data.get("created_at"))
            row.github_updated_at = _parse_iso(data.get("updated_at"))
            row.github_pushed_at  = _parse_iso(data.get("pushed_at"))
            row.archived = bool(data.get("archived"))
            row.last_metadata_refresh = datetime.now(timezone.utc).replace(tzinfo=None)
            stats.inserted += 1

    log.info("refreshed %d repositories", stats.inserted)
    return stats


def list_repositories(
    *,
    limit: int = 50,
    category: Optional[str] = None,
    status: Optional[str] = None,
    min_stars: int = 0,
) -> list[dict]:
    """Return repositories matching the filters as plain dicts.

    Returning dicts (instead of detached ORM instances) keeps the caller
    safe from ``DetachedInstanceError`` once the session closes — the
    session_scope() context manager in :mod:`src.db` commits on exit and
    expires all attributes.
    """
    with session_scope() as session:
        stmt = select(AgentRepository)
        if category:
            stmt = stmt.where(AgentRepository.agent_category == category)
        if status:
            stmt = stmt.where(AgentRepository.relevance_status == status)
        if min_stars > 0:
            stmt = stmt.where(AgentRepository.stars >= min_stars)
        stmt = stmt.order_by(AgentRepository.discovered_at.desc()).limit(limit)
        rows = session.execute(stmt).scalars().all()
        # Materialise every column into a dict inside the session so we
        # don't trigger lazy loads after the session is gone.
        return [
            {col.name: getattr(r, col.name) for col in AgentRepository.__table__.c}
            for r in rows
        ]


def reclassify(
    *,
    only_status: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> ReclassifyStats:
    """Re-run the classifier on every row (or a filtered subset) and
    update ``relevance_status``, ``agent_category``, ``relevance_reason``,
    ``relevance_confidence``, and stamp ``reclassified_at``.

    Preserves ``discovery_query``, ``discovered_at``, and the
    ``last_metadata_refresh`` timestamp (use :func:`refresh_metadata` for
    those). The ``enabled`` flag is recomputed from the new status.

    Args:
        only_status: if set, only reclassify rows whose current
                     ``relevance_status`` matches. Useful for re-running
                     just ``candidate`` rows after a heuristic tweak.
        limit:       cap on number of rows to scan.
        dry_run:     when True, never write back; still returns a
                     ReclassifyStats describing what would change.
    """
    from collections import Counter

    stats = ReclassifyStats()
    before_counter: Counter[str] = Counter()
    after_counter:  Counter[str] = Counter()

    # Fetch the candidate rows in a single read.
    with session_scope() as session:
        stmt = select(AgentRepository)
        if only_status:
            stmt = stmt.where(AgentRepository.relevance_status == only_status)
        stmt = stmt.order_by(AgentRepository.id.asc())
        if limit:
            stmt = stmt.limit(limit)
        rows = session.execute(stmt).scalars().all()
        # Snapshot the fields we need into dicts so we can write back
        # without keeping a session open for the whole run.
        snapshots = [
            {
                "id":               r.id,
                "name":             r.name,
                "full_name":        r.full_name,
                "description":      r.description or "",
                "topics":           json.loads(r.topics_json or "[]"),
                "language":         r.primary_language,
                "stars":            r.stars,
                "fork":             r.fork,
                "archived":         r.archived,
                "pushed_at":        r.github_pushed_at.isoformat() if r.github_pushed_at else None,
                "old_status":       r.relevance_status,
                "old_category":     r.agent_category,
            }
            for r in rows
        ]

    stats.scanned = len(snapshots)
    log.info("reclassify: scanning %d rows%s", stats.scanned,
             " (dry-run)" if dry_run else "")

    # Classify each row in pure-Python (no DB, no API).
    new_results: list[dict] = []
    for s in snapshots:
        repo_dict = {
            "name":             s["name"],
            "full_name":        s["full_name"],
            "description":      s["description"],
            "topics":           s["topics"],
            "language":         s["language"],
            "stargazers_count": s["stars"],
            "fork":             s["fork"],
            "archived":         s["archived"],
            "pushed_at":        s["pushed_at"],
        }
        c = cls.classify(repo_dict)
        new_results.append({
            "id":             s["id"],
            "old_status":     s["old_status"],
            "old_category":   s["old_category"],
            "new_status":     c.relevance_status,
            "new_category":   c.agent_category,
            "reason":         c.reason,
            "confidence":     c.confidence,
            "enabled":        (c.relevance_status != cls.STATUS_REJECTED),
        })
        before_counter[s["old_status"]] += 1
        after_counter[c.relevance_status]  += 1

    stats.before = dict(before_counter)
    stats.after  = dict(after_counter)

    if dry_run:
        log.info("reclassify: dry-run, no writes performed")
        return stats

    # Write back. One transaction per row to keep things simple; the
    # corpus is small.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for r in new_results:
        with session_scope() as session:
            row = session.get(AgentRepository, r["id"])
            if row is None:
                continue
            status_changed   = row.relevance_status != r["new_status"]
            category_changed = row.agent_category   != r["new_category"]
            if status_changed or category_changed or row.relevance_reason != r["reason"]:
                row.relevance_status     = r["new_status"]
                row.agent_category       = r["new_category"]
                row.relevance_reason     = r["reason"]
                row.relevance_confidence = r["confidence"]
                row.enabled              = r["enabled"]
                row.reclassified_at      = now
                stats.updated += 1
                if status_changed:
                    stats.status_changes += 1
                if category_changed:
                    stats.category_changes += 1

    log.info("reclassify: updated %d rows (status=%d category=%d changes)",
             stats.updated, stats.status_changes, stats.category_changes)
    return stats
