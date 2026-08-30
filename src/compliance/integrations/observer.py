"""ObserverSet — reusable, framework-agnostic observers.

An ObserverSet is a *named* Python class that knows how to attach
to a framework's native observation surface and emit a stream of
`NativeObservation` records. Observers observe runtime behavior.

Observers must NEVER:
  - return PASS / FAIL;
  - reference Article numbers;
  - classify A / B / C / D / E provenance categories;
  - decide whether the system is "compliant";
  - invent events.

Observers may stamp each observation with a `producer` (who
created the underlying fact) and a `framework_artifact_ref` (a
durable artifact path or state-store key that the system itself
populated). The Normalizer uses these to translate the
observation stream into canonical Reguard Evidence events with
proper provenance.
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class NativeObservation:
    """One observation recorded by a framework-specific observer.

    The `producer` field is a free-form string identifying who
    actually produced the underlying fact. The Normalizer maps
    `producer` to one of the canonical `EvidenceOrigin` values:

        SYSTEM_NATIVE                       -> SYSTEM_NATIVE
        SYSTEM_STATE_EXPORTED_BY_HARNESS    -> SYSTEM_STATE_EXPORTED_BY_HARNESS
        HARNESS_GENERATED                   -> HARNESS_GENERATED
    """

    kind: str
    """Free-form observation kind, e.g. "model_request",
    "tool_invocation", "tool_result", "state_checkpoint",
    "message_emitted", "permission_request", "browser_navigate",
    "browser_action", "error". The Normalizer decides the
    canonical Reguard event kind."""

    producer: str
    """Who created the underlying fact:
        "system"             SYSTEM_NATIVE
        "system_state"       SYSTEM_STATE_EXPORTED_BY_HARNESS
        "harness"            HARNESS_GENERATED
    """

    name: str = ""
    """Optional tool / model / step name."""

    content: Any = None
    """Optional raw payload (text, dict, etc.)."""

    ts: str = ""
    """ISO8601 UTC timestamp if available. Empty if the framework
    did not provide one."""

    framework_artifact_ref: str = ""
    """Path or identifier of a durable framework-side artifact
    that contains the underlying state for this observation.
    Set by the observer when applicable."""

    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ObserverContext:
    """What the ObserverSet needs to attach and run.

    Built by the integration resolver. The `handle` field is an
    opaque runtime handle (a CompiledStateGraph, a Controller
    object, a Pipeline instance, etc.) that the observer knows
    how to subscribe to.
    """

    handle: Any
    config: Any
    """RecipeConfig for the current run. Observers may read this
    to decide what to capture."""


class ObserverSet(ABC):
    """Base class for a named, versioned observer set."""

    observer_id: str = "UNSET"
    observer_version: str = "0.0.0"
    supported_kinds: tuple[str, ...] = ()

    def prepare(self, context: ObserverContext) -> None:
        """Attach to the framework's observation surface.

        Default: no-op. Subclasses override to subscribe to
        callbacks, register listeners, etc.
        """

    def observe(self, context: ObserverContext) -> Sequence[NativeObservation]:
        """Return all observations captured so far.

        Default: empty. Subclasses override to drain their
        internal buffers or query framework-side state.
        """
        return ()

    def finalize(self, context: ObserverContext) -> Iterable[NativeObservation]:
        """Tear down subscriptions and flush any final state.

        Default: empty. Subclasses override to unsubscribe /
        persist last observations.
        """
        return ()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_OBSERVER_REGISTRY: dict[tuple[str, str], ObserverSet] = {}


def register_observer(observer: ObserverSet) -> ObserverSet:
    key = (observer.observer_id, observer.observer_version)
    if key in _OBSERVER_REGISTRY:
        return _OBSERVER_REGISTRY[key]
    _OBSERVER_REGISTRY[key] = observer
    return observer


def get_observer(observer_id: str, observer_version: str | None = None) -> ObserverSet:
    candidates = [
        (ver, obs) for (oid, ver), obs in _OBSERVER_REGISTRY.items()
        if oid == observer_id
    ]
    if not candidates:
        raise KeyError(f"no observer registered for id {observer_id!r}")
    if observer_version is not None:
        for ver, obs in candidates:
            if ver == observer_version:
                return obs
        raise KeyError(
            f"no observer registered for {observer_id}@{observer_version}"
        )
    candidates.sort(key=lambda kv: kv[0])
    return candidates[-1][1]


def all_observers() -> list[ObserverSet]:
    return sorted(
        _OBSERVER_REGISTRY.values(),
        key=lambda o: (o.observer_id, o.observer_version),
    )


def reset_observer_registry() -> None:
    _OBSERVER_REGISTRY.clear()
