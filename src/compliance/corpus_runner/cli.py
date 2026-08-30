"""Corpus Runner v1 CLI.

This is a thin CLI surface over `corpus_runner.executor`. It exists
to:

  1. Make the corpus runner invokable from shell scripts / GHA jobs,
  2. Centralise default policy decisions (max_workers default,
     max_attempts default, scenario default, executor default),
  3. Emit machine-readable progress.

It is NOT a replacement for the executor. Tests should drive the
executor directly; the CLI is just a transport.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from compliance.pipeline import RUNTIME_VERSION
from compliance.corpus_runner import executor as cr_exec
from compliance.corpus_runner import persistence as crp
from compliance.corpus_runner.scenarios import S1
from compliance.pipeline.persistence import default_db_path


# Conservative defaults — explicitly NOT the v1.4.0 freeze's
# 4–8 worker heuristic. The default is 1 because we have no
# empirical concurrency characterisation of pip / git / container
# cold-start on the corpus scale yet.
DEFAULT_MAX_WORKERS = 1
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_SCENARIO = S1
DEFAULT_EXECUTOR = "subprocess"
DEFAULT_ORDERING = "stars_desc"
DEFAULT_LIMIT = 5

KNOWN_FIVE = (
    "SWE-agent/mini-swe-agent",
    "corecodecore/corecoder",
    "nanobot-ai/nanobot",
    "gptme/gptme",
    "The-Pocket/PocketFlow",
)


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m compliance.corpus_runner run",
        description="Corpus Runner v1 (Article 12(1) v1.4.0 only).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Create + execute a corpus run.")
    run.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                     help="How many eligible repos to include.")
    run.add_argument("--ordering", choices=("stars_desc", "pushed_desc", "name_asc"),
                     default=DEFAULT_ORDERING)
    run.add_argument("--include", action="append", default=[],
                     help="Full name to force-include at the front. "
                          "Repeat the flag, or pass a comma-separated list, "
                          "or both. Example: --include owner/repo1 "
                          "--include owner/repo2,owner/repo3")
    run.add_argument("--scenario", default=DEFAULT_SCENARIO)
    run.add_argument("--executor", default=DEFAULT_EXECUTOR,
                     choices=("subprocess", "container"))
    run.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    run.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    run.add_argument("--db", type=Path, default=None,
                     help="Override default DB path.")
    run.add_argument("--summary-json", type=Path, default=None,
                     help="Write the final summary JSON to this path.")
    run.add_argument("--selection-description", default="manual cli run",
                     help="Free-form description stored in corpus_runs.selection_description.")
    run.add_argument("--manifest", type=Path, default=None,
                     help="Path to a JSON file mapping full_name → "
                          "40-hex SHA. Repositories listed here bypass "
                          "git ls-remote HEAD resolution and use the "
                          "supplied SHA verbatim. Repositories not "
                          "listed fall back to live HEAD resolution. "
                          "Used by CR-1 to pin the historical baseline.")

    res = sub.add_parser("resume", help="Resume a previously created run.")
    res.add_argument("--corpus-run-id", type=int, required=True)
    res.add_argument("--executor", default=DEFAULT_EXECUTOR,
                     choices=("subprocess", "container"))
    res.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    res.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    res.add_argument("--db", type=Path, default=None)
    res.add_argument("--summary-json", type=Path, default=None)

    show = sub.add_parser("show", help="Print the final summary for a run.")
    show.add_argument("--corpus-run-id", type=int, required=True)
    show.add_argument("--db", type=Path, default=None)
    show.add_argument("--summary-json", type=Path, default=None,
                      help="Also write the JSON summary to this path.")

    # v1.1.1 — cache GC subcommand.
    cache = sub.add_parser(
        "cache", help="Cache management.",
        description=(
            "Source cache management. The cache is class-B (disposable "
            "performance infrastructure); eviction never affects "
            "compliance verdicts."
        ),
    )
    cache_sub = cache.add_subparsers(dest="cache_cmd", required=True)
    cache_gc = cache_sub.add_parser("gc", help="Evict cache entries.")
    cache_gc.add_argument("--max-bytes", type=int, default=None,
                          help="Maximum total cache size in bytes.")
    cache_gc.add_argument("--max-age-days", type=int, default=None,
                          help="Maximum age (days) since last_used_at.")
    cache_gc.add_argument("--cache-root", type=Path, default=None,
                          help="Override the source-cache root path.")
    cache_gc.add_argument("--dry-run", action="store_true",
                          help="Compute the eviction plan without removing entries.")
    cache_gc.add_argument("--json", action="store_true",
                          help="Emit the plan as JSON.")

    # v1.1.1 — workspace janitor subcommand.
    ws = sub.add_parser(
        "workspace", help="Workspace management.",
        description=(
            "Workspace janitor. Removes abandoned or stale per-attempt "
            "workspaces. Never touches active workspaces (live jobs "
            "still hold a lock) and never touches durable evidence / "
            "result records."
        ),
    )
    ws_sub = ws.add_subparsers(dest="workspace_cmd", required=True)
    ws_gc = ws_sub.add_parser("gc", help="Remove stale workspaces.")
    ws_gc.add_argument("--max-age-minutes", type=int, default=60,
                       help="Workspaces older than this with no live "
                            "attempt are considered stale.")
    ws_gc.add_argument("--workspace-root", type=Path, default=None)
    ws_gc.add_argument("--db", type=Path, default=None)
    ws_gc.add_argument("--dry-run", action="store_true")
    ws_gc.add_argument("--json", action="store_true")

    return p


def _resolve_db_path(arg: Path | None) -> Path:
    return arg if arg is not None else default_db_path()


def _on_progress_log(progress: cr_exec.CorpusRunProgress) -> None:
    sys.stderr.write(progress.snapshot_line() + "\n")
    sys.stderr.flush()


def _parse_include(raw: list[str]) -> tuple[str, ...]:
    """Flatten a list of include tokens, splitting any
    comma-separated entries. Empty tokens are dropped."""
    out: list[str] = []
    for token in raw:
        for piece in token.split(","):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return tuple(out)


def _load_pinned_shas(path: Path | None) -> dict[str, str]:
    """Load a JSON manifest {full_name: sha}. Returns an empty
    dict when path is None. Validates each SHA as 40 lowercase
    hex; raises ValueError on malformed input."""
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"--manifest JSON must be an object mapping full_name → sha; "
            f"got {type(raw).__name__}"
        )
    return dict(raw)


def cmd_run(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    includes = _parse_include(args.include)
    pinned = _load_pinned_shas(args.manifest)
    rows = crp.list_eligible_repositories(
        limit=args.limit, ordering=args.ordering,
        include_full_names=includes,
        db_path=db,
    )
    if not rows:
        print("no eligible repositories selected", file=sys.stderr)
        return 2

    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0",
        scenario_id=args.scenario,
        executor=args.executor,
        runtime_version=RUNTIME_VERSION,
        max_workers=max(1, args.max_workers),
        max_attempts=max(1, args.max_attempts),
        selection_description=args.selection_description,
        requested_repo_count=len(rows),
        db_path=db,
        pinned_shas=pinned,
    )

    rid = cr_exec.create_corpus_run(cfg, rows)
    cr_exec.build_jobs_for_run(rid, args.scenario, db_path=db)
    result = cr_exec.run_corpus_run(
        rid, executor=args.executor, db_path=db,
        on_progress=_on_progress_log,
    )
    if args.summary_json is not None:
        cr_exec.write_summary_json(rid, args.summary_json, db_path=db)

    # CLI exit code = the highest-severity bucket present.
    # ERROR > UNSUPPORTED > UNKNOWN > FAIL > PASS = 0.
    # Anything with error_count > 0 is exit 1.
    if result.progress.error_count > 0:
        return 1
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    cr = crp.load_corpus_run(args.corpus_run_id, db_path=db)
    if cr is None:
        print(f"corpus_run_id {args.corpus_run_id} not found", file=sys.stderr)
        return 2
    # If the run is already terminal, refuse silently.
    if cr.status == "completed":
        print(f"corpus_run_id {args.corpus_run_id} already completed",
              file=sys.stderr)
        return 0
    # Re-resume: rebuild jobs from pending; do NOT re-snapshot.
    cr_exec.build_jobs_for_run(args.corpus_run_id, cr.scenario_id, db_path=db)
    result = cr_exec.run_corpus_run(
        args.corpus_run_id, executor=args.executor, db_path=db,
        on_progress=_on_progress_log,
    )
    if args.summary_json is not None:
        cr_exec.write_summary_json(args.corpus_run_id, args.summary_json,
                                    db_path=db)
    return 1 if result.progress.error_count > 0 else 0


def cmd_cache_gc(args: argparse.Namespace) -> int:
    """Run the source cache GC under the per-cache-key lock."""
    from compliance.corpus_runner.cache.source_cache import SourceCache
    from compliance.corpus_runner.materializer import (
        RepositoryMaterializer, gc_with_lock,
    )

    if args.cache_root is not None:
        sc = SourceCache(cache_root=args.cache_root)
    else:
        sc = SourceCache()
    rm = RepositoryMaterializer(source_cache=sc)
    plan = gc_with_lock(
        rm,
        max_bytes=args.max_bytes,
        max_age_days=args.max_age_days,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        verb = "would evict" if args.dry_run else "evicted"
        print(
            f"entries considered: {plan['entries_considered']}\n"
            f"entries protected: {plan['entries_protected']}\n"
            f"entries {verb}: {plan['entries_evicted']}\n"
            f"bytes reclaimable: {plan['bytes_reclaimable']}\n"
            f"bytes reclaimed: {plan['bytes_reclaimed']}\n"
            f"dry_run: {plan['dry_run']}"
        )
    return 0


def cmd_workspace_gc(args: argparse.Namespace) -> int:
    """Remove stale per-attempt workspaces."""
    from compliance.corpus_runner.workspace.manager import (
        WorkspaceManager, _default_workspace_root,
    )
    import time
    from compliance.corpus_runner import persistence as crp

    db = _resolve_db_path(args.db)
    wm = WorkspaceManager(workspace_root=args.workspace_root)
    root = wm.workspace_root or _default_workspace_root()
    if not root.exists():
        print(json.dumps({"removed": [], "dry_run": args.dry_run}))
        return 0

    # Live-attempt SHAs: a workspace is NOT stale if its suffix
    # corresponds to an in-flight (started, not completed) attempt.
    live_attempt_ids: set[int] = set()
    con = __import__("sqlite3").connect(db)
    try:
        for r in con.execute(
            "SELECT evaluation_job_id FROM evaluation_attempts "
            "WHERE started_at IS NOT NULL AND completed_at IS NULL"
        ).fetchall():
            live_attempt_ids.add(int(r[0]))
    finally:
        con.close()

    cutoff = time.time() - args.max_age_minutes * 60
    plan: list[dict] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        # Suffix layout: <ts>_<attempt_id>_<rand>
        try:
            parts = entry.name.split("_")
            if len(parts) < 3:
                continue
            attempt_id = int(parts[1])
        except (ValueError, IndexError):
            continue
        if attempt_id in live_attempt_ids:
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime > cutoff:
            continue
        plan.append({
            "path": str(entry),
            "attempt_id": attempt_id,
            "mtime": mtime,
            "age_seconds": time.time() - mtime,
        })
        if not args.dry_run:
            import shutil as _sh
            _sh.rmtree(entry, ignore_errors=True)
    out = {
        "considered_root": str(root),
        "removed": plan,
        "dry_run": args.dry_run,
    }
    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        verb = "would remove" if args.dry_run else "removed"
        print(
            f"workspace_root: {root}\n"
            f"workspaces {verb}: {len(plan)}"
        )
        for p in plan:
            print(f"  - {p['path']} (attempt_id={p['attempt_id']}, "
                  f"age={p['age_seconds']:.0f}s)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    cr = crp.load_corpus_run(args.corpus_run_id, db_path=db)
    if cr is None:
        print(f"corpus_run_id {args.corpus_run_id} not found", file=sys.stderr)
        return 2
    payload = {
        "corpus_run_id": cr.id,
        "status": cr.status,
        "requirement_id": cr.requirement_id,
        "requirement_version": cr.requirement_version,
        "scenario_id": cr.scenario_id,
        "executor": cr.executor,
        "runtime_version": cr.runtime_version,
        "max_workers": cr.max_workers,
        "max_attempts": cr.max_attempts,
        "requested_repo_count": cr.requested_repo_count,
        "total_jobs": cr.total_jobs,
        "completed_jobs": cr.completed_jobs,
        "pass_count": cr.pass_count,
        "fail_count": cr.fail_count,
        "unknown_count": cr.unknown_count,
        "unsupported_count": cr.unsupported_count,
        "error_count": cr.error_count,
        "skipped_count": cr.skipped_count,
        "started_at": cr.started_at,
        "completed_at": cr.completed_at,
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    print(text)
    if args.summary_json is not None:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(text, encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = _build_argparser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "resume":
        return cmd_resume(args)
    if args.cmd == "show":
        return cmd_show(args)
    if args.cmd == "cache":
        if args.cache_cmd == "gc":
            return cmd_cache_gc(args)
    if args.cmd == "workspace":
        if args.workspace_cmd == "gc":
            return cmd_workspace_gc(args)
    parser.error(f"unknown cmd: {args.cmd}")
    return 2  # unreachable


if __name__ == "__main__":
    sys.exit(main())
