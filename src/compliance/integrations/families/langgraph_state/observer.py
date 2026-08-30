"""LangGraph-state ObserverSet.

This ObserverSet translates the LangGraph-state execution output
into a stream of `NativeObservation` records. It never invents
events: every observation corresponds to either

  - a state value that the framework itself populated during the
    run (system_state), or
  - a stub model call (system, because the stub is wired in by
    the recipe in place of the framework's own model), or
  - a harness-side artefact (harness).

The ObserverSet never decides provenance; the Normalizer maps the
free-form `producer` strings to EvidenceOrigin values.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from ...observer import (
    NativeObservation,
    ObserverContext,
    ObserverSet,
)


class LangGraphStateObserverSet(ObserverSet):
    """Observer for any CompiledStateGraph-style run."""

    observer_id = "langgraph-state.callback-observer"
    observer_version = "1.0.0"
    supported_kinds = (
        "model_request",
        "model_response",
        "tool_invocation",
        "tool_result",
        "state_checkpoint",
        "message_emitted",
    )

    def __init__(self) -> None:
        self._observations: list[NativeObservation] = []

    def prepare(self, context: ObserverContext) -> None:
        self._observations = []

    def observe(self, context: ObserverContext) -> Sequence[NativeObservation]:
        handle = context.handle
        if handle is None:
            return tuple(self._observations)

        run_output = handle
        graph = getattr(run_output, "graph", None)
        if isinstance(graph, dict) and graph.get("kind") == "dry-run":
            self._observations.extend(_dry_run_observations(run_output))
        elif graph is not None:
            self._observations.extend(_graph_observations(run_output))

        return tuple(self._observations)

    def finalize(self, context: ObserverContext):
        return ()


def _dry_run_observations(run_output):
    """Build the canonical observation stream for a dry-run."""
    final_state = run_output.final_state or {}
    messages = final_state.get("messages") or []
    obs: list[NativeObservation] = []
    obs.append(NativeObservation(
        kind="model_request",
        producer="harness",
        name="deterministic-stub",
        content={"messages_count": len(messages)},
    ))
    for msg in messages:
        if msg.get("role") == "user":
            obs.append(NativeObservation(
                kind="message_emitted",
                producer="system",
                name="user_prompt",
                content=msg.get("content", ""),
            ))
        elif msg.get("role") == "assistant":
            obs.append(NativeObservation(
                kind="model_response",
                producer="system",
                name="assistant",
                content=msg.get("content", ""),
            ))
    if run_output.trajectory_path:
        obs.append(NativeObservation(
            kind="state_checkpoint",
            producer="system_state",
            name="trajectory",
            content={"path": run_output.trajectory_path},
            framework_artifact_ref=run_output.trajectory_path,
        ))
    return obs


def _graph_observations(run_output):
    """Build observations from a real CompiledStateGraph run.

    The preferred source of truth is the framework-side JSONL
    trajectory file that the framework writes during a normal
    invocation. Each row becomes one SYSTEM_NATIVE (or
    SYSTEM_STATE_EXPORTED_BY_HARNESS, for state exports)
    observation. The trajectory path itself is stamped as a
    framework_artifact_ref on the final observation."""
    obs: list[NativeObservation] = []
    trajectory_path = getattr(run_output, "trajectory_path", "") or ""

    rows: list[dict] = []
    if trajectory_path and Path(trajectory_path).exists():
        try:
            for line in Path(trajectory_path).read_text(
                encoding="utf-8"
            ).splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            rows = []

    if rows:
        for row in rows:
            event = row.get("event")
            if event == "step":
                obs.append(NativeObservation(
                    kind="step",
                    producer="system_state",
                    name=row.get("role", "step"),
                    content=row.get("content", ""),
                    ts=str(row.get("ts", "")),
                ))
            elif event == "model_response":
                obs.append(NativeObservation(
                    kind="model",
                    producer="system_state",
                    name=row.get("name", "model"),
                    content=row.get("content", ""),
                    ts=str(row.get("ts", "")),
                    framework_artifact_ref=trajectory_path,
                ))
            elif event == "tool_invocation":
                obs.append(NativeObservation(
                    kind="tool",
                    producer="system_state",
                    name=row.get("name", "tool"),
                    content=row.get("args"),
                    ts=str(row.get("ts", "")),
                    framework_artifact_ref=trajectory_path,
                ))
        return obs

    final_state = run_output.final_state or {}
    messages = final_state.get("messages") or []
    for msg in messages:
        role = msg.get("role") or msg.get("type") or "system"
        if role in ("user", "human"):
            obs.append(NativeObservation(
                kind="message_emitted",
                producer="system_state",
                name="user",
                content=msg.get("content", ""),
                framework_artifact_ref=trajectory_path or "",
            ))
        elif role in ("assistant", "ai"):
            obs.append(NativeObservation(
                kind="model",
                producer="system_state",
                name="assistant",
                content=msg.get("content", ""),
                framework_artifact_ref=trajectory_path or "",
            ))
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                obs.append(NativeObservation(
                    kind="tool",
                    producer="system_state",
                    name=tc.get("name", "tool"),
                    content=tc.get("args"),
                    framework_artifact_ref=trajectory_path or "",
                ))
    if trajectory_path:
        obs.append(NativeObservation(
            kind="state_checkpoint",
            producer="system_state",
            name="checkpoint",
            framework_artifact_ref=trajectory_path,
        ))
    return obs
