"""End-to-end run orchestration.

Two entry points:

    run_one(...)           # clone-mode: clones the repo from
                           # GitHub at the given SHA into a tempdir,
                           # then runs the probe. This is the local
                           # corpus mode.

    run_path_mode(...)     # path-mode: the caller has already
                           # checked out the repository at the given
                           # SHA (e.g. GitHub Actions actions/checkout
                           # populated $GITHUB_WORKSPACE). We use the
                           # checkout as-is and DO NOT clone.

Both code paths feed the same `_run_pipeline` helper, which runs
the probe, collects evidence, runs the requirement test, and
persists the result.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import RUNTIME_VERSION
from .orchestrator import ProbeOutputs, collect_evidence, run_probe
from .persistence import default_db_path, insert_run
from .types import (
    Evidence,
    RepositoryTarget,
    Result,
    RunRecord,
    RunStatus,
    Scenario,
)

from compliance.adapters import get_adapter
from compliance.requirements.ai_act.article_12_1 import (  # noqa: F401  triggers registration
    Article121AutomaticLoggingTest,
)
from compliance.requirements.base import REQUIREMENT_REGISTRY, get_requirement


@dataclass(frozen=True)
class RepoRow:
    repository_id: int
    full_name: str
    default_branch: str = "main"


# Default scenario for Article 12(1). Used by every adapter so the
# stimulus is identical across repos.
DEFAULT_SCENARIO_12_1 = Scenario(
    scenario_id="compliance.synthetic.hello",
    user_prompt="Say hello and exit.",
    expected_tool_calls=(),
    max_steps=2,
)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lookup_repo(db_path: Path, full_name: str) -> RepoRow:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT id, full_name
            FROM agent_repositories
            WHERE full_name = ?
            """,
            (full_name,),
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"repository {full_name!r} not in DB")
        return RepoRow(
            repository_id=int(row[0]),
            full_name=row[1],
        )
    finally:
        conn.close()


def _clone_to_tempdir(full_name: str, sha: str) -> Path:
    url = f"https://github.com/{full_name}.git"
    tmp = Path(tempfile.mkdtemp(prefix=f"cp_probe_{full_name.replace('/', '_')}_"))
    subprocess.run(
        ["git", "clone", "--no-checkout", url, str(tmp)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    subprocess.run(
        ["git", "-C", str(tmp), "checkout", sha],
        check=True,
        capture_output=True,
        timeout=60,
    )
    # remove .git so the probe cannot reach back to origin.
    subprocess.run(["rm", "-rf", ".git"], cwd=str(tmp), check=False)
    return tmp


def _verify_checkout_sha(repo_path: Path, expected_sha: str) -> None:
    """Refuse to run if the checkout is not at the requested SHA.

    Path-mode callers may have checked out something different from
    what was requested (e.g. an unrelated commit). We do not silently
    proceed.
    """
    try:
        actual = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(
            f"cannot determine HEAD of {repo_path}: {exc}"
        ) from exc

    if actual != expected_sha:
        raise RuntimeError(
            f"checkout HEAD {actual!r} does not match requested SHA "
            f"{expected_sha!r}; refusing to run with mismatched provenance"
        )


def _stub_probe_outputs_from_error(exc: Exception) -> ProbeOutputs:
    return ProbeOutputs(
        work_dir=Path("/nonexistent"),
        trajectory_path=Path("/nonexistent"),
        stdout_log="",
        stderr_log=f"run_probe raised: {exc!r}",
        returncode=-1,
    )


def _write_evidence_bundle(evidence_path: Path, evidence: Evidence) -> None:
    """Persist the raw evidence bundle to disk as a JSON artifact."""
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(evidence.to_json(), encoding="utf-8")


def _run_pipeline(
    *,
    target: RepositoryTarget,
    requirement_id: str,
    repo_checkout: Path,
    evidence_output_dir: Path | None,
    work_root_parent: Path | None,
    persist: bool,
) -> tuple[RunRecord, Path | None]:
    """Core execution: probe + assert + (optional) persist.

    Used by both run_one (clone mode) and run_path_mode. Always
    returns a fully populated RunRecord and the path to the
    evidence JSON file on disk (or None if evidence_output_dir
    was not provided).
    """
    db_path = default_db_path() if persist else None
    adapter = get_adapter(target.full_name)
    requirement = get_requirement(requirement_id)

    started_at = _now_iso()
    t0 = time.monotonic()

    if work_root_parent is None:
        work_root_parent = Path(tempfile.mkdtemp(prefix="cp_work_"))
    work_root = Path(work_root_parent) / "probe"
    work_root.mkdir(parents=True, exist_ok=True)

    evidence_path: Path | None = None
    if evidence_output_dir is not None:
        evidence_path = (
            Path(evidence_output_dir) / f"evidence_{target.full_name.replace('/', '_')}.json"
        )

    try:
        try:
            probe_outputs = run_probe(
                adapter=adapter,
                scenario=DEFAULT_SCENARIO_12_1,
                repo_checkout=Path(repo_checkout),
                work_root=work_root,
            )
        except Exception as exc:  # noqa: BLE001
            evidence = collect_evidence(
                adapter=adapter,
                scenario=DEFAULT_SCENARIO_12_1,
                outputs=_stub_probe_outputs_from_error(exc),
            )
        else:
            evidence = collect_evidence(
                adapter=adapter,
                scenario=DEFAULT_SCENARIO_12_1,
                outputs=probe_outputs,
            )

        if evidence_path is not None:
            _write_evidence_bundle(evidence_path, evidence)

        result = requirement.evaluate(evidence)
    finally:
        # probe work dir is always cleaned up; only the evidence
        # file in evidence_output_dir is preserved.
        shutil.rmtree(work_root, ignore_errors=True)

    completed_at = _now_iso()
    duration = time.monotonic() - t0

    record = RunRecord(
        repository=target,
        requirement_id=requirement.id,
        requirement_version=requirement.version,
        runtime_version=RUNTIME_VERSION,
        adapter_name=adapter.name,
        adapter_version=adapter.version,
        scenario_id=DEFAULT_SCENARIO_12_1.scenario_id,
        status=result.status,
        reason=result.reason,
        result=result,
        evidence=evidence,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
    )

    if persist and db_path is not None:
        try:
            insert_run(db_path, record)
        except sqlite3.IntegrityError:
            record = _attach_dedup_reason(record)

    return record, evidence_path


def run_one(
    *,
    full_name: str,
    sha: str,
    requirement_id: str = "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
    keep_repo: bool = False,
) -> RunRecord:
    """Clone-mode run.

    Clones the repository at `sha` into a temporary directory,
    runs the probe, asserts, and persists.

    `keep_repo=True` skips the tempdir cleanup; useful for debugging.
    """
    db_path = default_db_path()
    repo_row = _lookup_repo(db_path, full_name)

    target = RepositoryTarget(
        repository_id=repo_row.repository_id,
        full_name=full_name,
        sha=sha,
        branch=repo_row.default_branch,
    )

    repo_checkout = _clone_to_tempdir(full_name, sha)
    try:
        record, _ = _run_pipeline(
            target=target,
            requirement_id=requirement_id,
            repo_checkout=repo_checkout,
            evidence_output_dir=None,
            work_root_parent=None,
            persist=True,
        )
        return record
    finally:
        if not keep_repo:
            shutil.rmtree(repo_checkout, ignore_errors=True)


def run_path_mode(
    *,
    repository_path: Path,
    repository_full_name: str,
    repo_sha: str,
    requirement_id: str = "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
    evidence_output_dir: Path | None = None,
    persist: bool = False,
) -> tuple[RunRecord, Path | None]:
    """Path-mode run.

    The caller has already checked out the repository at the given
    path. We do NOT clone. We do NOT replace the SHA. We verify
    that the checkout HEAD equals `repo_sha` and refuse otherwise.

    Returns the RunRecord plus the path to the on-disk evidence
    file (or None if evidence_output_dir was not provided).
    """
    path = Path(repository_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"repository_path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"repository_path is not a directory: {path}")

    _verify_checkout_sha(path, repo_sha)

    # In path mode we do not require the repo to be in the local
    # SQLite DB. The orchestrator's pipeline is repo-name keyed by
    # the adapter registry, which is repository-agnostic.
    if persist:
        try:
            repo_row = _lookup_repo(default_db_path(), repository_full_name)
            repository_id = repo_row.repository_id
            branch = repo_row.default_branch
        except KeyError:
            repository_id = -1
            branch = "main"
    else:
        repository_id = -1
        branch = "main"

    target = RepositoryTarget(
        repository_id=repository_id,
        full_name=repository_full_name,
        sha=repo_sha,
        branch=branch,
    )

    return _run_pipeline(
        target=target,
        requirement_id=requirement_id,
        repo_checkout=path,
        evidence_output_dir=evidence_output_dir,
        work_root_parent=None,
        persist=persist,
    )


def _attach_dedup_reason(record: RunRecord) -> RunRecord:
    """If the dedup index fires, return an ERROR record explaining why."""
    new_status = RunStatus.ERROR
    new_reason = (
        "duplicate (repository_id, requirement, sha, scenario, adapter) "
        "triple — already recorded; refusing to overwrite"
    )
    new_result = Result(
        schema_version=record.result.schema_version,
        status=new_status,
        reason=new_reason,
        checks=record.result.checks,
        summary={**record.result.summary, "dedup": True},
    )
    return RunRecord(
        repository=record.repository,
        requirement_id=record.requirement_id,
        requirement_version=record.requirement_version,
        runtime_version=record.runtime_version,
        adapter_name=record.adapter_name,
        adapter_version=record.adapter_version,
        scenario_id=record.scenario_id,
        status=new_status,
        reason=new_reason,
        result=new_result,
        evidence=record.evidence,
        started_at=record.started_at,
        completed_at=record.completed_at,
        duration_seconds=record.duration_seconds,
    )


def list_registered_requirements() -> list[str]:
    return sorted(REQUIREMENT_REGISTRY.keys())