"""Normalizer — translates native framework observations into
canonical Reguard Evidence events.

A Normalizer is a *named* Python class. It takes the raw
NativeObservation stream from the ObserverSet plus the recipe
resolution and produces a NormalizerResult containing:

    - canonical_events : tuple of dicts suitable for
                         compliance.pipeline.types.Evidence
                         (each dict has at minimum: kind, origin,
                         ts, name?, content?)
    - framework_persists_durably : bool
        True if a framework-side durable artifact was observed.
    - framework_artifact_paths : tuple[str, ...]
        Paths to durable framework artifacts observed during the
        run (e.g. trajectory.jsonl written by langchain agent).
    - harness_artifact_paths : tuple[str, ...]
        Paths to artifacts written by the harness (NOT eligible
        to establish PASS).

Normalizers must NEVER:
  - return PASS / FAIL;
  - reference Article numbers;
  - decide provenance eligibility (they translate it but the
    requirement test decides whether the provenance is
    eligible for PASS);
  - invent events.
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Sequence

from .observer import NativeObservation


# Map the free-form observer `producer` strings onto the canonical
# EvidenceOrigin enum values. Centralised here so normalizers stay
# consistent and the provenance boundary remains the same.
PRODUCER_TO_ORIGIN: dict[str, str] = {
    "system": "SYSTEM_NATIVE",
    "system_state": "SYSTEM_STATE_EXPORTED_BY_HARNESS",
    "harness": "HARNESS_GENERATED",
}


# Canonical event-kind vocabulary. ObserverSets emit these via
# NativeObservation.kind; Normalizers preserve them (with a small
# mapping table for framework-specific synonyms).
CANONICAL_EVENT_KINDS: frozenset[str] = frozenset({
    "step",
    "tool",
    "model",
    "tool_error",
    "error",
    "exit",
    "message",
    "checkpoint",
    "permission_request",
    "permission_decision",
    "browser_navigate",
    "browser_action",
    "browser_observation",
    "completion",
})


@dataclass(frozen=True)
class NormalizerResult:
    """Output of a Normalizer.normalize() call."""

    canonical_events: tuple[dict, ...] = ()
    framework_persists_durably: bool = False
    framework_artifact_paths: tuple[str, ...] = ()
    harness_artifact_paths: tuple[str, ...] = ()
    extra: dict = field(default_factory=dict)

    def recording_category(self) -> str:
        """Derive the A/B/C/D/E category the requirement test
        consumes. The normalizer emits the FACT; the requirement
        test consumes the category. We compute it here so the
        consumer does not have to re-derive.

        The category is set in `extra['recording_category']` to
        match what `compliance.pipeline.types.Evidence.extra`
        already accepts. The Article 12(1) v1.4.0 requirement
        consumes it from there."""
        return str(self.extra.get("recording_category", "E"))


class Normalizer(ABC):
    """Base class for a named, versioned normalizer."""

    normalizer_id: str = "UNSET"
    normalizer_version: str = "0.0.0"

    def normalize(
        self,
        observations: Sequence[NativeObservation],
        *,
        recipe_id: str,
        recipe_version: str,
    ) -> NormalizerResult:
        """Translate a NativeObservation stream into a
        NormalizerResult. Subclasses MUST implement.

        The base implementation is a reference implementation that
        handles the trivial case (every observation is one event,
        producer -> origin, framework_artifact_ref -> artifact
        path). It returns category E unless framework_persists is
        explicitly set."""
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
                },
            )

        events: list[dict] = []
        framework_artifacts: list[str] = []
        harness_artifacts: list[str] = []
        for obs in observations:
            origin = PRODUCER_TO_ORIGIN.get(obs.producer, "HARNESS_GENERATED")
            event = {
                "kind": obs.kind if obs.kind in CANONICAL_EVENT_KINDS else "step",
                "origin": origin,
                "ts": obs.ts,
                "name": obs.name,
                "content": obs.content,
            }
            events.append(event)
            if obs.framework_artifact_ref:
                if origin == "SYSTEM_NATIVE":
                    framework_artifacts.append(obs.framework_artifact_ref)
                elif origin == "SYSTEM_STATE_EXPORTED_BY_HARNESS":
                    framework_artifacts.append(obs.framework_artifact_ref)
                else:
                    harness_artifacts.append(obs.framework_artifact_ref)

        framework_persists = any(
            ev["origin"] in {"SYSTEM_NATIVE", "SYSTEM_STATE_EXPORTED_BY_HARNESS"}
            for ev in events
        ) and bool(framework_artifacts)

        return NormalizerResult(
            canonical_events=tuple(events),
            framework_persists_durably=framework_persists,
            framework_artifact_paths=tuple(framework_artifacts),
            harness_artifact_paths=tuple(harness_artifacts),
            extra={
                "recording_category": "B" if framework_persists else "D",
                "recipe_id": recipe_id,
                "recipe_version": recipe_version,
            },
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_NORMALIZER_REGISTRY: dict[tuple[str, str], Normalizer] = {}


def register_normalizer(normalizer: Normalizer) -> Normalizer:
    key = (normalizer.normalizer_id, normalizer.normalizer_version)
    if key in _NORMALIZER_REGISTRY:
        return _NORMALIZER_REGISTRY[key]
    _NORMALIZER_REGISTRY[key] = normalizer
    return normalizer


def get_normalizer(normalizer_id: str, normalizer_version: str | None = None) -> Normalizer:
    candidates = [
        (ver, n) for (nid, ver), n in _NORMALIZER_REGISTRY.items()
        if nid == normalizer_id
    ]
    if not candidates:
        raise KeyError(f"no normalizer registered for id {normalizer_id!r}")
    if normalizer_version is not None:
        for ver, n in candidates:
            if ver == normalizer_version:
                return n
        raise KeyError(
            f"no normalizer registered for {normalizer_id}@{normalizer_version}"
        )
    candidates.sort(key=lambda kv: kv[0])
    return candidates[-1][1]


def all_normalizers() -> list[Normalizer]:
    return sorted(
        _NORMALIZER_REGISTRY.values(),
        key=lambda n: (n.normalizer_id, n.normalizer_version),
    )


def reset_normalizer_registry() -> None:
    _NORMALIZER_REGISTRY.clear()
