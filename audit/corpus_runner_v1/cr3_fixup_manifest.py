"""Regenerate the CR-3 manifest from the authoritative DB rows.

The original gate's pre-resolution `write_manifest()` ran `git ls-remote`
*before* `create_corpus_run`, so its outcome could diverge from the
DB row (e.g. `NousResearch/hermes-agent` timed out the first time
but resolved on the second attempt; `langchain-ai/langchain`
similar). This script makes the DB the single source of truth for
the persisted manifest."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

GATE_DB = REPO_ROOT / "data" / "eu_ai_compliance.db"
MANIFEST_PATH = REPO_ROOT / "audit" / "corpus_runner_v1" / "cr3_50_repo_manifest.json"
SUMMARY_PATH = REPO_ROOT / "audit" / "corpus_runner_v1" / "cr3_50_repo_summary.json"
REPORT_PATH = REPO_ROOT / "audit" / "corpus_runner_v1" / "cr3_50_repo_report.md"

FROZEN_SHAS = {
    "SWE-agent/mini-swe-agent": "25941c89cfbc91eb40b3f8756348c91d9977d57e",
    "gptme/gptme":             "c574b83d34f970f816af18183bd77d01b22bd504",
    "HKUDS/nanobot":           "4d204ba077a86dc42225c16f8f90032013ea1969",
    "he-yufeng/CoreCoder":     "a03ef36412e432fc49d972d4007b36ce44ec5d9a",
    "The-Pocket/PocketFlow":   "f74d023f93607b8c3268133339a5e532a949898c",
}


def main() -> int:
    conn = sqlite3.connect(GATE_DB)
    conn.row_factory = sqlite3.Row
    try:
        rid_row = conn.execute(
            "SELECT MAX(id) AS id FROM corpus_runs"
        ).fetchone()
        rid = int(rid_row["id"])

        rows = conn.execute(
            """
            SELECT crr.position, crr.repository_id, crr.full_name,
                   crr.clone_url, crr.resolved_sha,
                   crr.sha_resolution_class, crr.sha_resolution_message,
                   ar.stars
            FROM corpus_run_repositories crr
            JOIN agent_repositories ar ON ar.id = crr.repository_id
            WHERE crr.corpus_run_id = ?
            ORDER BY crr.position ASC
            """,
            (rid,),
        ).fetchall()

        run_row = conn.execute(
            "SELECT created_at FROM corpus_runs WHERE id = ?", (rid,)
        ).fetchone()
        run_created_at = run_row["created_at"]

        items = []
        for r in rows:
            items.append({
                "position": r["position"],
                "repository_id": r["repository_id"],
                "full_name": r["full_name"],
                "clone_url": r["clone_url"],
                "stars": r["stars"],
                "resolved_sha": r["resolved_sha"],
                "sha_resolution_class": r["sha_resolution_class"],
                "sha_resolution_message": r["sha_resolution_message"],
            })

        payload = {
            "schema_version": "1",
            "selection_rule": (
                "frozen five by spec order + "
                "45 by agent_repositories.STARS DESC, agent_repositories.id ASC "
                "WHERE enabled=1 AND relevance_status='accepted' "
                "AND primary_language='Python' AND archived=0 AND fork=0 "
                "AND full_name NOT IN (frozen five)"
            ),
            "selection_started_at": run_created_at,
            "selection_completed_at": run_created_at,
            "selection_authoritative_source": (
                "corpus_run_repositories (authoritative; regenerated "
                "from DB to eliminate pre-resolution / run-resolution drift)"
            ),
            "frozen_shas": FROZEN_SHAS,
            "items": items,
        }

        MANIFEST_PATH.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"rewrote {MANIFEST_PATH} with {len(items)} items")
        print("manifest SHA classes:",
              {r["sha_resolution_class"] for r in rows})
    finally:
        conn.close()

    # Patch the existing summary JSON's sha_resolution.items list to
    # match the DB (so the report has correct data when regenerated).
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    summary["sha_resolution"]["items"] = items
    summary["sha_resolution"]["selection_authoritative_source"] = (
        payload["selection_authoritative_source"]
    )
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"patched {SUMMARY_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())