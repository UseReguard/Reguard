"""`reguard check` — run a deterministic compliance check.

Resolution order:
    1. explicit --config
    2. repository-local reguard.yml
    3. built-in integration manifest
    4. legacy RepoAdapter fallback (frozen-five only)
    5. UNSUPPORTED

Exit codes:
    0  PASS
    1  FAIL
    2  UNKNOWN
    3  UNSUPPORTED
    4  ERROR

UNKNOWN and UNSUPPORTED are NEVER collapsed into FAIL.

The `--fail-on` argument is CI policy only; it cannot change the
status the engine reports. It controls when the CLI exits
non-zero.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from ..integrations import IntegrationResolver
from ..integrations.families import register as register_families
from ..integrations.recipe import RecipeConfig
from ..integrations.observer import ObserverContext
from ..integrations.config import load_reguard_yml
from ..pipeline.types import (
    Evidence,
    EvidenceOrigin,
    Result,
    RunRecord,
    RunStatus,
    EVIDENCE_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
)


# Exit-code contract. NEVER collapse UNKNOWN / UNSUPPORTED into FAIL.
EXIT_CODE: dict[RunStatus, int] = {
    RunStatus.PASS: 0,
    RunStatus.FAIL: 1,
    RunStatus.UNKNOWN: 2,
    RunStatus.UNSUPPORTED: 3,
    RunStatus.ERROR: 4,
}


def _ensure_requirements_registered() -> None:
    import importlib
    importlib.import_module("compliance.requirements.ai_act.article_12_1")


def cmd_check(args: argparse.Namespace) -> int:
    register_families()
    _ensure_requirements_registered()

    repo_path = Path(args.repo_path).resolve()
    if not repo_path.exists():
        print(f"reguard check: repo-path does not exist: {repo_path}", file=sys.stderr)
        return 4

    full_name = args.repo or _git_remote_full_name(repo_path) or "<local>"
    explicit = Path(args.config).resolve() if args.config else None

    resolver = IntegrationResolver()
    outcome = resolver.resolve(
        full_name=full_name,
        repo_path=repo_path,
        explicit_config=explicit,
    )

    started_at = _now_iso()
    t0 = time.monotonic()

    status: RunStatus = RunStatus.UNSUPPORTED
    reason: str = ""
    checks: tuple = ()
    events: tuple = ()
    extra: dict = {}
    record = None

    if outcome.integration is None:
        status = RunStatus.UNSUPPORTED
        reason = outcome.unsupported_reason or "no compatible integration"
        extra = {"missing_capability": "NO_EXECUTION_RECIPE"}
        record = _build_unsupported_record(
            full_name=full_name,
            status=status,
            reason=reason,
            extra=extra,
            started_at=started_at,
            duration_s=time.monotonic() - t0,
        )
    else:
        itg = outcome.integration
        try:
            from ..integrations.integration import validate_env
            validate_env(itg.recipe_config, dict(os.environ))
        except Exception as exc:
            status = RunStatus.ERROR
            reason = f"env validation failed: {exc}"
            checks = ()
            events = ()
            extra = {"error_class": "IntegrationConfigError"}
            record = _build_unsupported_record(
                full_name=full_name,
                status=status,
                reason=reason,
                extra=extra,
                started_at=started_at,
                duration_s=time.monotonic() - t0,
            )
        else:
            try:
                record, status, checks, events, extra = _run_integration(
                    integration=itg,
                    requirement_id=args.requirement,
                    started_at=started_at,
                    duration_s=time.monotonic() - t0,
                )
            except Exception as exc:
                status = RunStatus.ERROR
                reason = f"integration execution failed: {exc}"
                checks = ()
                events = ()
                extra = {"error_class": type(exc).__name__}

                record = _build_unsupported_record(
                    full_name=full_name,
                    status=status,
                    reason=reason,
                    extra=extra,
                    started_at=started_at,
                    duration_s=time.monotonic() - t0,
                )

    _emit_human_output(
        full_name=full_name,
        status=status,
        reason=reason,
        checks=checks,
        event_count=len(events),
        extra=extra,
        record=record,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = record.repository.repository_id or _stable_id(full_name)
    artefacts = _write_artefacts(
        output_dir=output_dir,
        run_id=str(run_id),
        record=record,
        events=events,
        checks=checks,
    )

    print()
    print(f"Artefacts: {artefacts['result_json']}")

    fail_on = {
        s.strip().upper() for s in args.fail_on.split(",") if s.strip()
    }
    if status.value in fail_on:
        return EXIT_CODE[status]
    return 0


def _run_integration(
    *,
    integration,
    requirement_id: str,
    started_at: str,
    duration_s: float,
):
    from ..requirements.base import get_requirement

    try:
        requirement = get_requirement(requirement_id)
    except KeyError:
        status = RunStatus.ERROR
        reason = f"unknown requirement_id {requirement_id!r}"
        checks = ()
        events: tuple[dict, ...] = ()
        extra = {"error_class": "UnknownRequirement"}
        record = _build_unsupported_record(
            full_name=integration.full_name,
            status=status,
            reason=reason,
            extra=extra,
            started_at=started_at,
            duration_s=duration_s,
        )
        return record, status, checks, events, extra

    from ..pipeline.types import Scenario
    scenario = Scenario(
        scenario_id="compliance.article12_1.simple",
        user_prompt="Say hello and exit.",
        expected_tool_calls=(),
        max_steps=2,
    )

    resolution = integration.recipe.resolve(integration.recipe_config)
    run_output = integration.recipe.run(resolution, scenario)

    ctx = ObserverContext(handle=run_output, config=integration.recipe_config)
    for obs in integration.observers:
        obs.prepare(ctx)
    for obs in integration.observers:
        obs.observe(ctx)
    for obs in integration.observers:
        list(obs.finalize(ctx))

    observations = []
    for obs in integration.observers:
        observations.extend(obs.observe(ctx))

    norm_result = integration.normalizer.normalize(
        observations,
        recipe_id=integration.recipe.recipe_id,
        recipe_version=integration.recipe.recipe_version,
    )

    events = norm_result.canonical_events
    evidence = Evidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        events=events,
        agent_class=f"reguard:recipe:{integration.recipe.recipe_id}",
        agent_version=integration.recipe.recipe_version,
        extra={
            "recording_category": norm_result.recording_category(),
            "framework_persists_durably": norm_result.framework_persists_durably,
            "framework_artifact_paths": list(norm_result.framework_artifact_paths),
            "harness_artifact_paths": list(norm_result.harness_artifact_paths),
            "family_id": "langgraph-state",
            "origin": "UNSPECIFIED",
        },
    )

    check_results = list(requirement.assert_evidence(evidence))
    status = _derive_status(check_results)
    reason = _derive_reason(status, check_results)
    checks = tuple(
        {
            "name": cr.name,
            "passed": cr.passed,
            "detail": cr.detail,
        }
        for cr in check_results
    )
    extra = dict(evidence.extra)
    extra["requirement_id"] = requirement_id
    extra["requirement_version"] = requirement.version
    extra["recipe_id"] = integration.recipe.recipe_id
    extra["recipe_version"] = integration.recipe.recipe_version
    extra["observer_ids"] = [
        f"{o.observer_id}@{o.observer_version}" for o in integration.observers
    ]
    extra["normalizer_id"] = (
        f"{integration.normalizer.normalizer_id}@"
        f"{integration.normalizer.normalizer_version}"
    )

    record = RunRecord(
        repository=_repo_target(integration.full_name),
        requirement_id=requirement_id,
        requirement_version=requirement.version,
        runtime_version=f"reguard-core/{__import__('compliance').__version__}",
        adapter_name=f"recipe:{integration.recipe.recipe_id}",
        adapter_version=integration.recipe.recipe_version,
        scenario_id=scenario.scenario_id,
        status=status,
        reason=reason,
        result=Result(
            schema_version=RESULT_SCHEMA_VERSION,
            status=status,
            reason=reason,
            checks=checks,
            summary={
                "recipe_id": integration.recipe.recipe_id,
                "recipe_version": integration.recipe.recipe_version,
                "family_id": "langgraph-state",
            },
        ),
        evidence=evidence,
        started_at=started_at,
        completed_at=_now_iso(),
        duration_seconds=duration_s,
        runtime_image_reference=os.environ.get("REGUARD_RUNTIME_IMAGE", ""),
        runtime_image_digest=os.environ.get("REGUARD_RUNTIME_IMAGE_DIGEST", ""),
    )

    return record, status, checks, events, extra


def _derive_status(check_results):
    if all(cr.passed for cr in check_results):
        return RunStatus.PASS
    for cr in check_results:
        if cr.passed is False:
            return RunStatus.FAIL
    return RunStatus.UNKNOWN


def _derive_reason(status, check_results):
    if status == RunStatus.PASS:
        return "all requirement checks passed"
    if status == RunStatus.FAIL:
        failed = [cr.name for cr in check_results if not cr.passed]
        return f"failed checks: {', '.join(failed)}"
    return "requirement checks produced no decisive verdict"


def _build_unsupported_record(
    *,
    full_name: str,
    status: RunStatus,
    reason: str,
    extra: dict,
    started_at: str,
    duration_s: float,
) -> RunRecord:
    from .. import __version__ as _reguard_version
    return RunRecord(
        repository=_repo_target(full_name),
        requirement_id=extra.get("requirement_id", "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING"),
        requirement_version=extra.get("requirement_version", ""),
        runtime_version=f"reguard-core/{_reguard_version}",
        adapter_name="recipe:",
        adapter_version="",
        scenario_id="",
        status=status,
        reason=reason,
        result=Result(
            schema_version=RESULT_SCHEMA_VERSION,
            status=status,
            reason=reason,
            checks=(),
            summary=extra,
        ),
        evidence=Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=(),
            agent_class="",
            agent_version="",
            extra=extra,
        ),
        started_at=started_at,
        completed_at=_now_iso(),
        duration_seconds=duration_s,
        runtime_image_reference=os.environ.get("REGUARD_RUNTIME_IMAGE", ""),
        runtime_image_digest=os.environ.get("REGUARD_RUNTIME_IMAGE_DIGEST", ""),
    )


def _repo_target(full_name: str):
    from ..pipeline.types import RepositoryTarget
    return RepositoryTarget(
        repository_id=_stable_id(full_name),
        full_name=full_name,
        sha="",
        branch="",
    )


def _stable_id(s: str) -> int:
    import hashlib
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit_human_output(
    *,
    full_name: str,
    status: RunStatus,
    reason: str,
    checks,
    event_count: int,
    extra: dict,
    record,
):
    print()
    print("Reguard Core")
    print()
    print(f"Repository")
    print(f"  {full_name}")
    rid = record.requirement_id
    rver = record.requirement_version or "n/a"
    print()
    print("Technical control")
    print(f"  {rid}")
    print(f"  Contract version {rver}")
    print()
    print(f"Result")
    print(f"  {status.value}")
    if checks:
        print()
        print("Checks")
        for cr in checks:
            mark = "✓" if cr["passed"] else "✗"
            print(f"  {mark} {cr['name']}")
            if not cr["passed"]:
                print(f"      {cr['detail']}")
    print()
    print("Evidence")
    print(f"  {event_count} events")
    if extra.get("framework_artifact_paths"):
        print(f"  {len(extra['framework_artifact_paths'])} framework artifact(s)")
    print()
    if status == RunStatus.UNSUPPORTED:
        print(f"Missing capability")
        cap = extra.get("missing_capability") or "NO_EXECUTION_RECIPE"
        print(f"  {cap}")
        print()
        print("Next step")
        print("  Add reguard.yml or use a supported integration.")
    elif status == RunStatus.PASS:
        if reason:
            print()
            print("Reason")
            print(f"  {reason}")
    elif status == RunStatus.FAIL:
        print("Reason")
        print(f"  {reason}")
    elif status == RunStatus.ERROR:
        print("Reason")
        print(f"  {reason}")


def _write_artefacts(*, output_dir, run_id, record, events, checks):
    import json
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    result_payload = {
        "schema_version": "1",
        "reguard_version": __import__("compliance").__version__,
        "repository": record.repository.full_name,
        "repo_sha": record.repository.sha,
        "requirement_id": record.requirement_id,
        "requirement_version": record.requirement_version,
        "scenario_id": record.scenario_id,
        "integration": {
            "recipe": record.result.summary.get("recipe_id"),
            "observer_versions": record.evidence.extra.get("observer_ids"),
            "normalizer_version": record.evidence.extra.get("normalizer_id"),
        },
        "runtime_image": {
            "reference": record.runtime_image_reference,
            "digest": record.runtime_image_digest,
        },
        "status": record.status.value,
        "reason": record.reason,
        "checks": list(checks),
        "missing_capability": record.evidence.extra.get("missing_capability"),
        "missing_facts": [],
        "error_class": record.evidence.extra.get("error_class"),
        "evidence_refs": [
            str(run_dir / "evidence.json"),
        ],
        "created_at": record.started_at,
    }

    evidence_payload = {
        "schema_version": record.evidence.schema_version,
        "events": list(events),
        "agent_class": record.evidence.agent_class,
        "agent_version": record.evidence.agent_version,
        "extra": dict(record.evidence.extra),
    }

    result_path = run_dir / "result.json"
    evidence_path = run_dir / "evidence.json"
    summary_path = run_dir / "summary.md"

    result_path.write_text(
        json.dumps(result_payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    evidence_path.write_text(
        json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    summary_path.write_text(_render_summary_md(record, checks), encoding="utf-8")

    return {
        "result_json": str(result_path),
        "evidence_json": str(evidence_path),
        "summary_md": str(summary_path),
    }


def _render_summary_md(record, checks) -> str:
    lines = []
    lines.append("# Reguard Core — Run summary")
    lines.append("")
    lines.append(f"- Repository: `{record.repository.full_name}`")
    lines.append(f"- SHA: `{record.repository.sha or '<unspecified>'}`")
    lines.append(f"- Requirement: `{record.requirement_id}` "
                 f"(contract {record.requirement_version})")
    lines.append(f"- Recipe: `{record.result.summary.get('recipe_id')}`")
    lines.append(f"- Result: **{record.status.value}**")
    lines.append("")
    if checks:
        lines.append("## Checks")
        lines.append("")
        for cr in checks:
            mark = "✅" if cr["passed"] else "❌"
            lines.append(f"- {mark} **{cr['name']}** — {cr['detail']}")
        lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append("This is a deterministic technical-control result.")
    lines.append("It does not establish overall EU AI Act compliance.")
    return "\n".join(lines) + "\n"


def _git_remote_full_name(repo_path: Path) -> str | None:
    try:
        import subprocess
        result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    if not url:
        return None
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@github.com:"):
        return url.split(":", 1)[1]
    if "github.com/" in url:
        return url.split("github.com/", 1)[1]
    return None
