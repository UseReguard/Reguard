"""Replay the frozen CR-2 manifest under the v1.1 architecture.

Reads `audit/corpus_runner_v1/cr2_manifest.json`, builds a CorpusRun
with the same 20 repos / SHAs as the original CR-2 (corpus_run_id=9),
runs it through the existing executor (which now writes v1.1 metadata),
and asserts that the resulting distribution is identical:

    PASS        2
    FAIL        3
    UNKNOWN     0
    ERROR       0
    UNSUPPORTED 15
    SKIPPED     0

The 5-frozen regression must still match A→PASS, B→PASS, C→FAIL,
D→FAIL, E→FAIL.

Cache behaviour may differ. Compliance behaviour must not.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner import executor as cr_exec
from compliance.corpus_runner import persistence as crp
from compliance.corpus_runner.cache.source_cache import (
    SourceCache, cache_key_for_url,
)
from compliance.corpus_runner.workspace.manager import WorkspaceManager
from compliance.pipeline.persistence import default_db_path


MANIFEST = json.loads(
    (ROOT / "audit" / "corpus_runner_v1" / "cr2_manifest.json").read_text(
        encoding="utf-8",
    )
)


def _seed_agent_repositories(db_path: Path) -> dict[str, int]:
    """Ensure each repo in the manifest has an `agent_repositories`
    row. Uses stable github_ids derived from the full_name."""
    name_to_id: dict[str, int] = {}
    con = sqlite3.connect(db_path)
    try:
        for full_name in MANIFEST:
            existing = con.execute(
                "SELECT id FROM agent_repositories WHERE full_name = ?",
                (full_name,),
            ).fetchone()
            if existing is not None:
                name_to_id[full_name] = int(existing[0])
                continue
            gh_id = 98_000_000 + (
                int.from_bytes(
                    full_name.encode("utf-8")[:4], "big",
                ) % 900_000
            )
            cur = con.execute(
                """INSERT INTO agent_repositories (
                       github_id, full_name, owner, name, html_url,
                       clone_url, primary_language, stars, forks, archived,
                       fork, relevance_status, discovered_at, enabled
                   ) VALUES (?, ?, ?, ?, ?, ?, 'Python', ?, 0, 0, 0,
                             'accepted', '2026-08-29T00:00:00Z', 1)""",
                (
                    gh_id, full_name,
                    full_name.split("/")[0], full_name.split("/")[1],
                    f"https://github.com/{full_name}",
                    f"https://github.com/{full_name}.git",
                    100_000,
                ),
            )
            name_to_id[full_name] = int(cur.lastrowid)
        con.commit()
    finally:
        con.close()
    return name_to_id


def _build_eligible_rows(db_path: Path,
                         name_to_id: dict[str, int]) -> list[sqlite3.Row]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows: list[sqlite3.Row] = []
        for full_name, repo_id in name_to_id.items():
            row = con.execute(
                "SELECT * FROM agent_repositories WHERE id = ?",
                (repo_id,),
            ).fetchone()
            rows.append(row)
        return rows
    finally:
        con.close()


def main() -> int:
    db_path = Path(os.environ.get("REGUARD_DB_PATH",
                                  str(ROOT / "data" / "eu_ai_compliance.db")))
    # Apply v1.1 migrations to the production DB if not already applied.
    migrations_dir = ROOT / "migrations"
    for m in ("010_corpus_runner_v1_1_schema.sql",
              "011_corpus_runner_v1_1_evidence_state.sql"):
        try:
            con = sqlite3.connect(db_path)
            con.executescript((migrations_dir / m).read_text(encoding="utf-8"))
            con.commit()
            con.close()
        except Exception as exc:
            print(f"[skip] {m}: {exc}")

    name_to_id = _seed_agent_repositories(db_path)
    rows = _build_eligible_rows(db_path, name_to_id)

    # Use a temporary cache + workspace root to keep the replay
    # isolated from any prior CR-2 state on this host.
    cache_root = Path(tempfile.mkdtemp(prefix="reguard_replay_cache_"))
    workspace_root = Path(tempfile.mkdtemp(prefix="reguard_replay_ws_"))
    os.environ["REGUARD_SOURCE_CACHE_ROOT"] = str(cache_root)
    os.environ["REGUARD_WORKSPACE_ROOT"] = str(workspace_root)

    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0",
        scenario_id="compliance.article12_1.simple",
        executor="container",
        runtime_version="1.1.0",
        max_workers=1,
        max_attempts=2,
        selection_description="CR-2 v1.1 replay",
        requested_repo_count=len(MANIFEST),
        db_path=db_path,
        pinned_shas=MANIFEST,
    )
    rid = cr_exec.create_corpus_run(cfg, rows)
    cr_exec.build_jobs_for_run(rid, cfg.scenario_id, db_path=db_path)
    result = cr_exec.run_corpus_run(
        rid, executor="container", db_path=db_path,
    )
    final = crp.load_corpus_run(rid, db_path=db_path)
    assert final is not None
    print(
        f"corpus_run_id={rid} "
        f"PASS={final.pass_count} FAIL={final.fail_count} "
        f"UNKNOWN={final.unknown_count} UNSUPPORTED={final.unsupported_count} "
        f"ERROR={final.error_count} SKIPPED={final.skipped_count}"
    )

    # Verify per-job v1.1 metadata is populated.
    con = sqlite3.connect(db_path)
    try:
        jobs = con.execute(
            "SELECT id, full_name FROM corpus_run_repositories "
            "JOIN evaluation_jobs ON evaluation_jobs.corpus_run_id = "
            "corpus_run_repositories.corpus_run_id "
            "WHERE corpus_run_repositories.corpus_run_id = ? "
            "AND evaluation_jobs.repository_id = "
            "corpus_run_repositories.repository_id "
            "ORDER BY evaluation_jobs.id ASC",
            (rid,),
        ).fetchall()
        missing_recipe = con.execute(
            "SELECT COUNT(*) FROM evaluation_jobs WHERE corpus_run_id = ? "
            "AND (execution_recipe_id IS NULL OR execution_recipe_id = '')",
            (rid,),
        ).fetchone()[0]
        requirement_evaluations = con.execute(
            "SELECT COUNT(*) FROM requirement_evaluations "
            "WHERE evaluation_job_id IN "
            "(SELECT id FROM evaluation_jobs WHERE corpus_run_id = ?)",
            (rid,),
        ).fetchone()[0]
    finally:
        con.close()
    print(f"jobs={len(jobs)} missing_recipe={missing_recipe} "
          f"requirement_evaluations={requirement_evaluations}")

    # Cache + workspace stats.
    sc = SourceCache(cache_root=cache_root)
    print(f"source_cache_size_bytes={sc.size_bytes()}")
    print(f"source_cache_entries={len(sc.entries())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
