"""Article 12(1) requirement test v1.4.0.

Legal text (CELEX 32024R1689, Article 12(1)):

    High-risk AI systems shall have technical capability to automatically
    record events ('logs') over the lifetime of the system.

Operating principle
-------------------
The article requires that the *system itself* records events automatically.
A harness may observe or export that record, but it must not produce the
record and then test for it. The contract distinguishes five categories
of system-side recording capability, set by the adapter at parse time in
`evidence.extra["recording_category"]`:

    A. framework creates and persists its own log durably (file, native
       DB, native session store written by framework code during a normal
       run).
    B. framework creates persistent / recoverable session state. The
       harness only reads.
    C. framework emits events but requires an external recorder (bus,
       queue, sink) to persist anything.
    D. framework keeps ephemeral in-memory state only.
    E. framework provides no recording mechanism.

Verdict mapping:

    category A or B    -> PASS-eligible when the event-kind checks hold.
    category C         -> FAIL. Framework-side recording capability
                          depends on a sink the framework does not own.
    category D         -> FAIL. Framework does not durably record.
    category E         -> FAIL when absence is observed at runtime; the
                          empty-events case is mapped to UNKNOWN upstream
                          of assert_evidence (handled in the base class).
    probe/setup failure -> ERROR.

The `framework_persists_durably` flag and `framework_artifact_paths` /
`harness_artifact_paths` lists are set by the adapter from runtime
observation. The RequirementTest does not look at the framework's source
code; it inspects only what the controlled run produced.

v1.4 -> v1.3 deltas
-------------------
- `TERMINAL_KIND_PRESENT` removed. Article 12(1) requires automatic
  system-side recording of runtime events. A framework can demonstrate
  that capability without modelling invocation termination as a
  dedicated `exit` or `completed` event. gptme's runtime evidence
  exposed the v1.3 terminal-marker requirement as an
  implementation-specific false negative: gptme's LogManager writes
  every conversation turn to a framework-side `conversation.jsonl`
  that is durable and recoverable, but does not emit an explicit
  terminal marker. That is a valid Article 12(1) implementation, not
  a capability gap.
- No replacement terminal/completion assertion is introduced. The
  remaining A/B checks (`RECORDING_CATEGORY_FRAMEWORK_PERSISTS` and
  `STEP_OR_TOOL_KIND_PRESENT`) already establish automatic recording
  capability when combined with the provenance requirement.
- A–E taxonomy unchanged. C/D semantics unchanged. E observed-absence
  semantics unchanged. UNKNOWN / ERROR / UNSUPPORTED unchanged.
- Provenance rules unchanged (`SYSTEM_NATIVE` /
  `SYSTEM_STATE_EXPORTED_BY_HARNESS` eligible; `HARNESS_GENERATED`
  rejected).
- `PROBE_RAN_CLEANLY` short-circuit (ERROR on probe_status != "ok")
  unchanged and still lives in the base class.
- Generic `observation_quality` dispatch unchanged.
"""
from __future__ import annotations

from typing import Iterable

from compliance.pipeline.types import Evidence, EvidenceOrigin

from ..base import CheckResult, RequirementTest, register_requirement


# Per-event-kind sets. Unchanged from v1.3.0.
_VALID_STEP_KINDS = {"step", "tool", "model"}

# Origins that may participate in PASS eligibility for A/B categories.
_PASS_ELIGIBLE_ORIGINS = {
    EvidenceOrigin.SYSTEM_NATIVE,
    EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS,
}


def _origin(event: dict) -> EvidenceOrigin | None:
    raw = event.get("origin")
    if not raw:
        return None
    try:
        return EvidenceOrigin(raw)
    except ValueError:
        return None


def _eligible_events(events: list[dict], kind_set: set[str]) -> list[dict]:
    out: list[dict] = []
    for event in events:
        if event.get("kind") not in kind_set:
            continue
        if _origin(event) not in _PASS_ELIGIBLE_ORIGINS:
            continue
        out.append(event)
    return out


def _is_fatal_error(event: dict) -> bool:
    return event.get("kind") == "error"


class Article121AutomaticLoggingTest(RequirementTest):
    id = "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING"
    version = "1.4.0"

    def assert_evidence(self, evidence: Evidence) -> Iterable[CheckResult]:
        events = list(evidence.events)

        # Universal provenance boundary. Every category yields this.
        harness_generated = [
            event for event in events
            if _origin(event) == EvidenceOrigin.HARNESS_GENERATED
        ]
        yield CheckResult(
            name="NO_HARNESS_GENERATED_EVENTS",
            passed=not harness_generated,
            detail=(
                f"observed {len(harness_generated)} HARNESS_GENERATED event(s); "
                "system must emit every event the harness records"
                if harness_generated
                else "no HARNESS_GENERATED events present"
            ),
        )

        non_error_events = [event for event in events if not _is_fatal_error(event)]
        yield CheckResult(
            name="AT_LEAST_ONE_EVENT",
            passed=len(non_error_events) >= 1,
            detail=(
                f"observed {len(non_error_events)} non-error event(s) "
                f"out of {len(events)} total"
            ),
        )

        category = (evidence.extra.get("recording_category") or "E")
        framework_persists = bool(
            evidence.extra.get("framework_persists_durably", False)
        )
        framework_artifacts: list[str] = list(
            evidence.extra.get("framework_artifact_paths") or ()
        )
        harness_artifacts: list[str] = list(
            evidence.extra.get("harness_artifact_paths") or ()
        )

        if category in ("A", "B"):
            # PASS-eligible. Both categories require that the framework
            # itself wrote a durable artefact during the run, and that
            # the recorded entries represent real agent activity (not
            # just harness noise). v1.4.0 dropped the terminal-event
            # requirement: a framework can satisfy Article 12(1)
            # without modelling invocation termination as a dedicated
            # `exit` or `completed` event.
            yield CheckResult(
                name="RECORDING_CATEGORY_FRAMEWORK_PERSISTS",
                passed=framework_persists and len(framework_artifacts) > 0,
                detail=(
                    f"category={category}; "
                    f"framework_persists_durably={framework_persists}; "
                    f"framework_artifact_paths={framework_artifacts}; "
                    f"harness_artifact_paths={harness_artifacts}"
                ),
            )
            eligible_step = _eligible_events(events, _VALID_STEP_KINDS)
            yield CheckResult(
                name="STEP_OR_TOOL_KIND_PRESENT",
                passed=len(eligible_step) >= 1,
                detail=(
                    f"observed {len(eligible_step)} eligible event(s) with "
                    f"kind in {sorted(_VALID_STEP_KINDS)} (of "
                    f"{sum(1 for e in events if e.get('kind') in _VALID_STEP_KINDS)} "
                    "total with that kind)"
                ),
            )

        elif category == "C":
            # Non-PASS. Framework emits events but requires an external
            # recorder. The harness-side persistence does not establish
            # automatic-recording-by-the-system capability.
            yield CheckResult(
                name="RECORDING_CATEGORY_NON_PASS_C",
                passed=False,
                detail=(
                    "category=C; framework emits events but its automatic "
                    "recording capability depends on an external recorder "
                    f"not in the framework. harness_artifacts={harness_artifacts}"
                ),
            )

        elif category == "D":
            # Non-PASS. Framework keeps ephemeral state only.
            yield CheckResult(
                name="RECORDING_CATEGORY_NON_PASS_D",
                passed=False,
                detail=(
                    "category=D; framework exposes only ephemeral in-memory "
                    "state with no built-in persistence. The framework does "
                    "not durably record events."
                ),
            )

        elif category == "E":
            # No recording mechanism. Per the verdict map: FAIL when
            # absence is observed at runtime; UNKNOWN is produced by the
            # base class when no events were collected at all.
            any_eligible = any(
                _origin(event) in _PASS_ELIGIBLE_ORIGINS for event in events
            )
            absence_observable = (
                not framework_artifacts and not any_eligible
            )
            yield CheckResult(
                name="RECORDING_CATEGORY_E_NON_PASS",
                passed=False,
                detail=(
                    f"category=E; framework provides no automatic recording "
                    f"mechanism. framework_artifact_paths={framework_artifacts}; "
                    f"any_eligible_event={any_eligible}; "
                    f"absence_observable={absence_observable}"
                ),
            )

        else:
            # Unknown category label. The adapter is misconfigured. We
            # record the issue and let the verdict collapse to FAIL.
            yield CheckResult(
                name="RECORDING_CATEGORY_KNOWN",
                passed=False,
                detail=(
                    f"recording_category={category!r} is not in "
                    "{'A','B','C','D','E'}; adapter must declare a valid category"
                ),
            )


register_requirement(Article121AutomaticLoggingTest())
