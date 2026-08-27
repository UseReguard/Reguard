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

            any ERROR evidence -> ERROR
            no events at all    -> UNKNOWN
            all checks PASSED   -> PASS
            some checks failed  -> FAIL
            adapter said n/a    -> UNSUPPORTED  (handled in adapter layer)
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

        if not evidence.events:
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