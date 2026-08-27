#!/usr/bin/env python3
"""Entry point used by GitHub Actions and by hand-runs.

Two modes:

  clone mode (default):
      python scripts/compliance-check.py --repo OWNER/NAME --sha SHA [--output FILE]

  path mode:
      python scripts/compliance-check.py \
          --repo-path DIR --repo OWNER/NAME --sha SHA [--output FILE]

Path mode is what `actions/checkout` produces (the workspace is
    populated at the requested SHA). The CLI does NOT clone in
    path mode. The CLI does NOT replace the SHA.

Exit codes
----------
  0  PASS
  1  FAIL
  2  UNKNOWN
  3  UNSUPPORTED
  4  ERROR

UNKNOWN and UNSUPPORTED are NEVER collapsed into FAIL.

The CLI also writes the structured result to `--output` (default:
none). When `--output` is given, an `evidence.json` sibling file
is always written next to it.

When the run completes (regardless of pass/fail), the CLI writes
a one-line JSON object to stdout for easy capture.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# allow running directly from a checkout
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from compliance.pipeline.driver import run_one, run_path_mode
from compliance.pipeline.types import Evidence, RepositoryTarget, Result, RunRecord, RunStatus


# Exit-code contract. NEVER collapse UNKNOWN / UNSUPPORTED into FAIL.
EXIT_CODE: dict[RunStatus, int] = {
    RunStatus.PASS: 0,
    RunStatus.FAIL: 1,
    RunStatus.UNKNOWN: 2,
    RunStatus.UNSUPPORTED: 3,
    RunStatus.ERROR: 4,
}


def _synth_record(args, status: RunStatus, reason: str) -> RunRecord:
    """Build a minimal RunRecord when the engine refused to start.

    Used for UNSUPPORTED (no adapter) and ERROR (provenance
    mismatch). Adapter / requirement / runtime versions are
    populated where known so the JSON payload is still useful.
    """
    from datetime import UTC, datetime

    return RunRecord(
        repository=RepositoryTarget(
            repository_id=-1,
            full_name=args.repo,
            sha=args.sha,
            branch="main",
        ),
        requirement_id=args.requirement,
        requirement_version="",
        runtime_version="",
        adapter_name="",
        adapter_version="",
        scenario_id="",
        status=status,
        reason=reason,
        result=Result(
            schema_version="2",
            status=status,
            reason=reason,
            checks=(),
            summary={},
        ),
        evidence=Evidence(
            schema_version="2",
            events=(),
            agent_class="",
            agent_version="",
            extra={"reason": reason, "origin": "UNSPECIFIED"},
        ),
        started_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        completed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        duration_seconds=0.0,
    )


def _unsupported_record(args, *, reason: str) -> RunRecord:
    return _synth_record(args, RunStatus.UNSUPPORTED, reason)


def _error_record(args, *, reason: str) -> RunRecord:
    return _synth_record(args, RunStatus.ERROR, reason)


def _write_result(output_path: Path, record, evidence_path: Path | None) -> Path:
    """Write the structured result JSON to output_path.

    The output is a single JSON object containing the public
    surface of the RunRecord plus provenance metadata. Schema is
    pinned at "1" for the result file.
    """
    payload = {
        "schema_version": "1",
        "repository": record.repository.full_name,
        "sha": record.repository.sha,
        "requirement_id": record.requirement_id,
        "requirement_version": record.requirement_version,
        "scenario_id": record.scenario_id,
        "status": record.status.value,
        "reason": record.reason,
        "duration_seconds": round(record.duration_seconds, 3),
        "event_count": len(record.evidence.events),
        "adapter_name": record.adapter_name,
        "adapter_version": record.adapter_version,
        "runtime_version": record.runtime_version,
        "evidence_origins": sorted({
            (ev.get("origin") or "UNSPECIFIED")
            for ev in record.evidence.events
        }),
        "checks": record.result.checks,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return output_path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--repo",
        required=True,
        help="owner/name (e.g. SWE-agent/mini-swe-agent)",
    )
    p.add_argument(
        "--sha",
        required=True,
        help="exact commit SHA; not replaced by path mode",
    )
    p.add_argument(
        "--repo-path",
        help="use this checked-out directory instead of cloning. "
             "Required in GitHub Actions path mode. The HEAD of "
             "this directory must match --sha.",
    )
    p.add_argument(
        "--requirement",
        default="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        help="requirement_id (only 12(1) is implemented today)",
    )
    p.add_argument(
        "--output",
        help="write the structured result JSON to this path",
    )
    p.add_argument(
        "--persist",
        action="store_true",
        help="also insert a row into compliance_runtime_runs "
             "(default in clone mode; off in path mode unless requested)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    evidence_dir: Path | None = None
    if args.output:
        evidence_dir = Path(args.output).resolve().parent / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

    if args.repo_path:
        try:
            record, evidence_path = run_path_mode(
                repository_path=Path(args.repo_path),
                repository_full_name=args.repo,
                repo_sha=args.sha,
                requirement_id=args.requirement,
                evidence_output_dir=evidence_dir,
                persist=args.persist,
            )
        except KeyError as exc:
            # No adapter registered -> UNSUPPORTED, exit 3.
            record = _unsupported_record(args, reason=f"unsupported repository: {exc}")
            evidence_path = None
        except RuntimeError as exc:
            # SHA mismatch or similar provenance error -> ERROR, exit 4.
            record = _error_record(args, reason=f"provenance check failed: {exc}")
            evidence_path = None
    else:
        # Clone mode (legacy local corpus path).
        try:
            record = run_one(
                full_name=args.repo,
                sha=args.sha,
                requirement_id=args.requirement,
            )
            evidence_path = None
        except KeyError as exc:
            record = _unsupported_record(args, reason=f"unsupported repository: {exc}")
            evidence_path = None

    if args.output:
        _write_result(Path(args.output), record, evidence_path)

    # stdout: single-line JSON for capture by CI / scripts.
    print(json.dumps({
        "repository": record.repository.full_name,
        "sha": record.repository.sha,
        "requirement_id": record.requirement_id,
        "requirement_version": record.requirement_version,
        "scenario_id": record.scenario_id,
        "status": record.status.value,
        "reason": record.reason,
        "duration_seconds": round(record.duration_seconds, 3),
        "event_count": len(record.evidence.events),
        "adapter_name": record.adapter_name,
        "adapter_version": record.adapter_version,
        "runtime_version": record.runtime_version,
        "evidence_origins": sorted({
            (ev.get("origin") or "UNSPECIFIED")
            for ev in record.evidence.events
        }),
    }, ensure_ascii=False, sort_keys=True))

    return EXIT_CODE[record.status]


if __name__ == "__main__":
    raise SystemExit(main())