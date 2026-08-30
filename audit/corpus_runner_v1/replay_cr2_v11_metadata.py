"""Replay verification: prove the v1.1 metadata layer populates
correctly without requiring container execution.

Uses the 5 frozen repos under the subprocess executor (faster) and
asserts:

  1. compliance distribution matches CR-2's frozen 5 (PASS=2, FAIL=3),
  2. every job has a `requirement_evaluations` row,
  3. every job has execution_recipe_id = 'legacy-adapter-direct',
  4. UNSUPPORTED jobs have missing_capability =
     'compatible_execution_recipe' (when an adapter is missing).

The 15 additional repos would each short-circuit to UNSUPPORTED on the
adapter-missing sentinel in any executor. To keep the replay fast and
deterministic we exercise both paths in one run: the 5 frozen
repos under the real subprocess executor; 5 additional manifest
entries (synthetically marked UNSUPPORTED) under a stub adapter path.

The replay does NOT introduce any adapter changes — it uses the
existing ADAPTER_MISSING_SENTINEL path that has been part of v1 since
CR-1. The new v1.1 metadata columns are now populated as a side effect.
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
from compliance.pipeline.persistence import default_db_path


PINNED = json.loads(
    (ROOT / "audit" / "corpus_runner_v1" / "cr2_manifest.json").read_text(
        encoding="utf-8",
    )
)


def _seed_repos(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    name_to_id: dict[str, int] = {}
    try:
        for full_name in PINNED:
            existing = con.execute(
                "SELECT id FROM agent_repositories WHERE full_name = ?",
                (full_name,),
            ).fetchone()
            if existing is not None:
                name_to_id[full_name] = int(existing[0])
                continue
            gh_id = 97_000_000 + (
                int.from_bytes(full_name.encode("utf-8")[:4], "big") % 900_000
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


def main() -> int:
    db_path = Path(os.environ.get("REGUARD_DB_PATH",
                                  str(ROOT / "data" / "eu_ai_compliance.db")))
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

    name_to_id = _seed_repos(db_path)
    rows = []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        for full_name, repo_id in name_to_id.items():
            row = con.execute(
                "SELECT * FROM agent_repositories WHERE id = ?",
                (repo_id,),
            ).fetchone()
            rows.append(row)
    finally:
        con.close()

    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0",
        scenario_id="compliance.article12_1.simple",
        executor="subprocess",  # subprocess for speed
        runtime_version="1.1.0",
        max_workers=1,
        max_attempts=2,
        selection_description="CR-2 v1.1 replay (full 20, subprocess)",
        requested_repo_count=len(PINNED),
        db_path=db_path,
        pinned_shas=PINNED,
    )
    rid = cr_exec.create_corpus_run(cfg, rows)
    cr_exec.build_jobs_for_run(rid, cfg.scenario_id, db_path=db_path)
    cr_exec.run_corpus_run(rid, executor="subprocess", db_path=db_path)
    final = crp.load_corpus_run(rid, db_path=db_path)
    assert final is not None
    print(
        f"replay_run_id={rid} "
        f"PASS={final.pass_count} FAIL={final.fail_count} "
        f"UNKNOWN={final.unknown_count} UNSUPPORTED={final.unsupported_count} "
        f"ERROR={final.error_count} SKIPPED={final.skipped_count}"
    )

    # Verify v1.1 metadata populated.
    con = sqlite3.connect(db_path)
    try:
        re_count = con.execute(
            "SELECT COUNT(*) FROM requirement_evaluations "
            "WHERE evaluation_job_id IN "
            "(SELECT id FROM evaluation_jobs WHERE corpus_run_id = ?)",
            (rid,),
        ).fetchone()[0]
        recipe_count = con.execute(
            "SELECT COUNT(*) FROM evaluation_jobs WHERE corpus_run_id = ? "
            "AND execution_recipe_id = 'legacy-adapter-direct'",
            (rid,),
        ).fetchone()[0]
        unsupported_with_cap = con.execute(
            "SELECT COUNT(*) FROM evaluation_jobs WHERE corpus_run_id = ? "
            "AND missing_capability = 'compatible_execution_recipe'",
            (rid,),
        ).fetchone()[0]
        job_count = con.execute(
            "SELECT COUNT(*) FROM evaluation_jobs WHERE corpus_run_id = ?",
            (rid,),
        ).fetchone()[0]
    finally:
        con.close()
    print(
        f"jobs={job_count} requirement_evaluations={re_count} "
        f"recipe_id_populated={recipe_count} "
        f"unsupported_with_missing_capability={unsupported_with_cap}"
    )

    # Compare to CR-2 expected distribution.
    expected = {"PASS": 2, "FAIL": 3, "UNSUPPORTED": 15}
    actual = {
        "PASS": final.pass_count,
        "FAIL": final.fail_count,
        "UNSUPPORTED": final.unsupported_count,
    }
    assert actual == expected, f"distribution drift: {actual} != {expected}"
    assert re_count == job_count, \
        f"requirement_evaluations missing: {re_count}/{job_count}"
    assert recipe_count == job_count, \
        f"execution_recipe_id missing: {recipe_count}/{job_count}"
    assert unsupported_with_cap == expected["UNSUPPORTED"], \
        f"missing_capability count wrong: {unsupported_with_cap}"
    print("REPLAY OK — distribution + v1.1 metadata verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
