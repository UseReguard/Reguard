"""LangGraph-state Normalizer.

Translates the LangGraph-state NativeObservation stream into the
canonical Reguard Evidence shape. Reuses the base implementation
in `integrations.normalizer` and applies the Family-A specific
A/B/C/D/E category derivation:

  - A  framework creates and persists its own log durably.
  - B  framework creates persistent / recoverable session state;
       harness only reads.
  - C  framework emits events but requires an external recorder.
  - D  framework keeps ephemeral in-memory state only.
  - E  framework provides no recording mechanism.

For Family A, the LangGraph checkpointer is framework-side
durable state. If the run produced a checkpoint artefact, the
recording category is B. If only in-memory state was produced,
the category is D. The category is recorded in
`NormalizerResult.extra['recording_category']` for the requirement
test to consume.
"""
from __future__ import annotations

from ...normalizer import (
    CANONICAL_EVENT_KINDS,
    Normalizer,
    NormalizerResult,
    PRODUCER_TO_ORIGIN,
)
from ...observer import NativeObservation


# Map the LangGraph-state observer's free-form `kind` strings onto
# the canonical Reguard event kinds.
_KIND_MAP: dict[str, str] = {
    "model_request": "model",
    "model_response": "model",
    "tool_invocation": "tool",
    "tool_result": "tool",
    "tool_error": "tool_error",
    "state_checkpoint": "checkpoint",
    "message_emitted": "message",
    "permission_request": "permission_request",
    "permission_decision": "permission_decision",
    "browser_navigate": "browser_navigate",
    "browser_action": "browser_action",
    "browser_observation": "browser_observation",
    "error": "error",
    "exit": "exit",
}


class LangGraphStateNormalizer(Normalizer):
    """Family A normalizer."""

    normalizer_id = "langgraph-state.canonical-normalizer"
    normalizer_version = "1.0.0"

    def normalize(
        self,
        observations,
        *,
        recipe_id: str,
        recipe_version: str,
    ):
        if not observations:
            return NormalizerResult(
                canonical_events=(),
                framework_persists_durably=False,
                framework_artifact_paths=(),
                harness_artifact_paths=(),
                extra={
                    "recording_category": "E",
                    "recipe_id": recipe_id,
                    "recipe_version": recipe_version,
                    "family_id": "langgraph-state",
                },
            )

        events: list[dict] = []
        framework_artifacts: list[str] = []
        harness_artifacts: list[str] = []
        any_system_native = False
        any_system_state = False

        for obs in observations:
            origin = PRODUCER_TO_ORIGIN.get(obs.producer, "HARNESS_GENERATED")
            if origin == "SYSTEM_NATIVE":
                any_system_native = True
            elif origin == "SYSTEM_STATE_EXPORTED_BY_HARNESS":
                any_system_state = True

            kind = _KIND_MAP.get(obs.kind, obs.kind)
            if kind not in CANONICAL_EVENT_KINDS:
                kind = "step"

            events.append({
                "kind": kind,
                "origin": origin,
                "ts": obs.ts,
                "name": obs.name,
                "content": obs.content,
            })

            if obs.framework_artifact_ref:
                if origin in ("SYSTEM_NATIVE", "SYSTEM_STATE_EXPORTED_BY_HARNESS"):
                    framework_artifacts.append(obs.framework_artifact_ref)
                else:
                    harness_artifacts.append(obs.framework_artifact_ref)

        framework_persists = bool(framework_artifacts) and (
            any_system_native or any_system_state
        )
        category = "B" if framework_persists else "D" if events else "E"

        return NormalizerResult(
            canonical_events=tuple(events),
            framework_persists_durably=framework_persists,
            framework_artifact_paths=tuple(framework_artifacts),
            harness_artifact_paths=tuple(harness_artifacts),
            extra={
                "recording_category": category,
                "recipe_id": recipe_id,
                "recipe_version": recipe_version,
                "family_id": "langgraph-state",
                "family_observed_kinds": sorted({ev["kind"] for ev in events}),
            },
        )
