"""Requirement test base class.

A RequirementTest turns an Evidence object into a deterministic Result.
It is the single source of truth for the compliance decision.

To add a new legal requirement:
    1. subclass RequirementTest,
    2. fill in `id`, `version`, and `assert_evidence`,
    3. register it in REQUIREMENT_REGISTRY below.

Nothing else in the pipeline needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Iterable

from compliance.pipeline.types import (
    RESULT_SCHEMA_VERSION,
    Evidence,
    Result,
    RunStatus,
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


class RequirementTest(ABC):
    """Base class for a single legal-requirement compliance check."""

    id: str = "UNSET"
    version: str = "0.0.0"

    @abstractmethod
    def assert_evidence(self, evidence: Evidence) -> Iterable[CheckResult]:
        """Return one or more CheckResults. The aggregate status is
        computed from these (see evaluate)."""

    def evaluate(self, evidence: Evidence) -> Result:
        """Run all checks and reduce them into a single Result.

        The reduction rule is intentionally simple and deterministic:

            probe did not run cleanly -> ERROR
            any schema mismatch       -> ERROR
            no events at all           -> UNKNOWN
                (unless the adapter positively marked the empty bundle
                with ``observation_quality="observed_absence"``; then
                the requirement is given the bundle so it can decide)
            all checks PASSED          -> PASS
            some checks failed         -> FAIL
            adapter said n/a           -> UNSUPPORTED  (handled in adapter layer)

        The probe-cleanly check distinguishes engine failures from
        compliance failures: a probe that crashed, never wrote a
        trajectory, or tripped the adapter parser is a setup problem,
        not evidence that the system under test violated the
        requirement. Those map to ERROR, never FAIL.

        ``observation_quality`` is a generic, requirement-agnostic
        adapter-set field on ``evidence.extra``:

            "observed_absence" — the adapter positively observed that
                the framework produced no recording on this run. The
                absence is itself a runtime fact, not a harness guess.
                An empty events bundle with this marker is dispatched
                to ``assert_evidence`` so the requirement can decide
                what absence means for its verdict. No synthetic
                event is appended.

            absent, ``"indeterminate"``, or any other value — the
                adapter could not establish what the framework did.
                An empty events bundle maps to UNKNOWN, matching
                pre-existing behaviour.

        This contract is generic: no requirement-specific logic is
        encoded here. Any requirement that wants to interpret
        observed absence may do so; any requirement that does not
        check ``observation_quality`` simply ignores it.
        """
        if evidence.schema_version != RESULT_SCHEMA_VERSION:
            return Result(
                schema_version=RESULT_SCHEMA_VERSION,
                status=RunStatus.ERROR,
                reason=(
                    f"evidence schema_version {evidence.schema_version!r} "
                    f"does not match expected {RESULT_SCHEMA_VERSION!r}"
                ),
                checks=(),
                summary={"evidence_schema_version": evidence.schema_version},
            )

        probe_status = evidence.extra.get("probe_status")
        if probe_status is not None and probe_status != "ok":
            return Result(
                schema_version=RESULT_SCHEMA_VERSION,
                status=RunStatus.ERROR,
                reason=(
                    f"probe did not run cleanly: {probe_status!r}; "
                    f"{evidence.extra.get('reason', '')}"
                ).strip(),
                checks=(),
                summary={
                    "probe_status": probe_status,
                    "probe_returncode": evidence.extra.get("probe_returncode"),
                    "event_count": len(evidence.events),
                },
            )

        if not evidence.events:
            # Generic dispatch on observation_quality. The base class
            # does not encode any requirement-specific rule here; it
            # only respects the adapter's positive observation. If
            # the adapter positively observed the framework produced
            # no recording ("observed_absence"), the empty bundle is
            # delivered to assert_evidence so the requirement may
            # interpret it. Anything else — including the field
            # being absent — keeps the pre-existing UNKNOWN mapping.
            observation_quality = evidence.extra.get("observation_quality")
            if observation_quality == "observed_absence":
                checks = tuple(self.assert_evidence(evidence))
                failed = [c for c in checks if not c.passed]
                if not failed:
                    status = RunStatus.PASS
                    reason = "all checks passed"
                else:
                    status = RunStatus.FAIL
                    reason = (
                        f"{len(failed)} check(s) failed: "
                        + ", ".join(c.name for c in failed)
                    )
                return Result(
                    schema_version=RESULT_SCHEMA_VERSION,
                    status=status,
                    reason=reason,
                    checks=tuple(c.as_dict() for c in checks),
                    summary={
                        "check_count": len(checks),
                        "failed_count": len(failed),
                        "event_count": 0,
                        "observation_quality": observation_quality,
                    },
                )
            return Result(
                schema_version=RESULT_SCHEMA_VERSION,
                status=RunStatus.UNKNOWN,
                reason=(
                    "probe collected no runtime events; cannot determine "
                    "compliance"
                ),
                checks=(),
                summary={"event_count": 0},
            )

        checks = tuple(self.assert_evidence(evidence))
        failed = [c for c in checks if not c.passed]
        if not failed:
            status = RunStatus.PASS
            reason = "all checks passed"
        else:
            status = RunStatus.FAIL
            reason = f"{len(failed)} check(s) failed: " + ", ".join(
                c.name for c in failed
            )

        return Result(
            schema_version=RESULT_SCHEMA_VERSION,
            status=status,
            reason=reason,
            checks=tuple(c.as_dict() for c in checks),
            summary={
                "check_count": len(checks),
                "failed_count": len(failed),
                "event_count": len(evidence.events),
            },
        )


REQUIREMENT_REGISTRY: dict[str, RequirementTest] = {}


def register_requirement(test: RequirementTest) -> None:
    """Register a RequirementTest under its `id`. Replaces any prior."""
    REQUIREMENT_REGISTRY[test.id] = test


def get_requirement(requirement_id: str) -> RequirementTest:
    if requirement_id not in REQUIREMENT_REGISTRY:
        raise KeyError(f"unknown requirement_id: {requirement_id!r}")
    return REQUIREMENT_REGISTRY[requirement_id]