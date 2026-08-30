"""build_jobs_for_run idempotence test (§16)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner import executor as cr_exec
from compliance.corpus_runner import persistence as crp
from compliance.corpus_runner.scenarios import S1
from compliance.corpus_runner.sha_resolver import ShaResolution


PINNED_FIVE = {
    "SWE-agent/mini-swe-agent": "25941c89cfbc91eb40b3f8756348c91d9977d57e",
    "gptme/gptme":              "c574b83d34f970f816af18183bd77d01b22bd504",
    "HKUDS/nanobot":            "4d204ba077a86dc42225c16f8f90032013ea1969",
    "he-yufeng/CoreCoder":      "a03ef36412e432fc49d972d4007b36ce44ec5d9a",
    "The-Pocket/PocketFlow":    "f74d023f93607b8c3268133339a5e532a949898c",
}


@pytest.fixture
def db_path(tmp_path):
    db = tmp_path / "corpus.db"
    migrations_dir = ROOT / "migrations"
    needed = [
        "001_agent_repositories.sql",
        "002_agent_repositories_reclassified_at.sql",
        "003_agent_repository_audits.sql",
        "004_article_runtime_assessments.sql",
        "005_compliance_runtime_runs.sql",
        "006_corpus_runs.sql",
        "007_corpus_run_repositories.sql",
        "008_evaluation_jobs.sql",
        "009_evaluation_attempts.sql",
        "010_corpus_runner_v1_1_schema.sql",
        "011_corpus_runner_v1_1_evidence_state.sql",
    ]
    import sqlite3
    con = sqlite3.connect(db)
    try:
        for name in needed:
            con.executescript(
                (migrations_dir / name).read_text(encoding="utf-8"),
            )
        con.commit()
    finally:
        con.close()
    return db


@pytest.fixture
def seeded(db_path):
    import sqlite3
    con = sqlite3.connect(db_path)
    try:
        for i, (full_name, sha) in enumerate(PINNED_FIVE.items(), start=1):
            existing = con.execute(
                "SELECT id FROM agent_repositories WHERE full_name = ?",
                (full_name,),
            ).fetchone()
            if existing is not None:
                continue
            gh_id = 96_000_000 + i
            con.execute(
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
        con.commit()
    finally:
        con.close()
    return db_path


def test_build_jobs_for_run_is_idempotent(seeded):
    """Calling `build_jobs_for_run` twice produces the same logical
    job count and never duplicates `evaluation_jobs` rows or
    double-counts `corpus_runs` counters."""
    db = seeded
    rows = crp.list_eligible_repositories(
        limit=5,
        include_full_names=tuple(PINNED_FIVE),
        db_path=db,
    )
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0",
        scenario_id=S1,
        executor="subprocess",
        runtime_version="test",
        max_workers=1,
        max_attempts=1,
        selection_description="idempotence test",
        requested_repo_count=5,
        db_path=db,
        pinned_shas=PINNED_FIVE,
    )
    rid = cr_exec.create_corpus_run(cfg, rows)
    n1 = cr_exec.build_jobs_for_run(rid, S1, db_path=db)
    n2 = cr_exec.build_jobs_for_run(rid, S1, db_path=db)
    n3 = cr_exec.build_jobs_for_run(rid, S1, db_path=db)
    assert n1 == n2 == n3 == 5

    import sqlite3
    con = sqlite3.connect(db)
    try:
        job_count = con.execute(
            "SELECT COUNT(*) FROM evaluation_jobs WHERE corpus_run_id = ?",
            (rid,),
        ).fetchone()[0]
        # completed_jobs on the run row should equal 0 (no execution,
        # only job creation) — not 5 / 10 / 15 (which would indicate
        # counter double-counting).
        completed_jobs = con.execute(
            "SELECT completed_jobs FROM corpus_runs WHERE id = ?",
            (rid,),
        ).fetchone()[0]
    finally:
        con.close()
    assert job_count == 5
    assert completed_jobs == 0
