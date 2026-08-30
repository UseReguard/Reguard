"""Scenario registry — first-class versioned scenario identities.

These IDs are pinned for Corpus Runner v1. They match the P5 study
note IDs and the orchestration layer treats them as opaque strings;
the underlying probe behaviour is unchanged from the v1.4.0 contract.

The defaults used by the existing `driver.DEFAULT_SCENARIO_12_1`
remain `compliance.synthetic.hello` — semantically equivalent to
S1 (simple). Articles other than 12(1) would extend this registry;
Article 12(1) v1.4.0 alone is supported today.
"""
from __future__ import annotations

from dataclasses import dataclass

S1 = "compliance.article12_1.simple"
S2 = "compliance.article12_1.tool_success"
S3 = "compliance.article12_1.tool_failure"
S4 = "compliance.article12_1.multi_step"
S5 = "compliance.article12_1.system_error"

# Backwards-compatible baseline the legacy v1.4 driver uses.
LEGACY_S1 = "compliance.synthetic.hello"


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    description: str
    version: str

    @property
    def is_baseline(self) -> bool:
        """True for the S1-equivalent baseline scenarios.

        The first corpus-runner gate executes only the baseline to
        keep the run-time deterministic and bounded."""
        return self.scenario_id in (S1, LEGACY_S1)


SCENARIO_REGISTRY: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(S1, "Simple completion.", "1"),
    ScenarioSpec(S2, "Deterministic tool call.", "1"),
    ScenarioSpec(S3, "Tool returns controlled error.", "1"),
    ScenarioSpec(S4, "Multi-step execution (>=2 transitions).", "1"),
    ScenarioSpec(S5, "System-under-test error, probe stays clean.", "1"),
    ScenarioSpec(LEGACY_S1, "Legacy baseline (S1-equivalent).", "1"),
)


def known_scenario(scenario_id: str) -> ScenarioSpec | None:
    for s in SCENARIO_REGISTRY:
        if s.scenario_id == scenario_id:
            return s
    return None


def is_supported_by_capability(scenario_id: str, *, capability_set) -> bool:
    """Whether a scenario is supported by a given iterable of
    adapter-declared scenario IDs.

    If the adapter declares no supported_scenarios tuple (empty),
    Conservatively only S1 / legacy S1 are treated as supported.
    """
    declared = set(capability_set or ())
    if not declared:
        return scenario_id in (S1, LEGACY_S1)
    return scenario_id in declared
