"""Minimal deterministic agent for the reguard v0.1 demo.

This module exposes a `build_graph()` factory that the
langgraph-state Recipe invokes in **live mode**. The factory
returns a self-contained object that:

  - implements a minimal `.invoke()` API (the recipe calls it
    with `{"messages": [...]}`),
  - records every step into a durable JSONL trajectory file
    inside the workspace,
  - exposes a `.trajectory_path` attribute so the ObserverSet
    can find the artefact.

The factory depends on NO external services, NO foundation
model, and NO network access. It exists so the integration
path can be exercised end-to-end deterministically.

Users who want to plug in a real langgraph `CompiledStateGraph`
should replace `build_graph` with a function that returns one.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path


class _MinimalGraph:
    """Self-contained stand-in for a `CompiledStateGraph`.

    Implements the subset of the API the langgraph-state recipe
    actually calls: `.invoke(messages, config=...)` and a
    `.trajectory_path` attribute."""

    def __init__(self) -> None:
        self._trajectory_path = Path(
            os.environ.get(
                "REGUARD_DEMO_TRAJECTORY",
                str(Path(tempfile.gettempdir()) / "reguard_demo_trajectory.jsonl"),
            )
        )
        self._trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        self._trajectory_path.write_text("", encoding="utf-8")
        self._thread_id = f"reguard-demo-{uuid.uuid4().hex[:8]}"

    @property
    def trajectory_path(self) -> str:
        return str(self._trajectory_path)

    def invoke(self, payload, config=None):
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        out_messages: list[dict] = []
        ts0 = time.time()
        for m in messages:
            self._record({"event": "step", "role": m.get("role", "user"),
                          "content": m.get("content", ""), "ts": ts0})
            out_messages.append(m)
        assistant = {"role": "assistant",
                     "content": "hello from minimal agent (deterministic stub)"}
        self._record({"event": "model_response",
                      "name": "deterministic-stub",
                      "content": assistant["content"],
                      "ts": ts0})
        out_messages.append(assistant)
        return {"messages": out_messages}

    def _record(self, row: dict) -> None:
        with self._trajectory_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_graph(*, model=None, tools=None):
    """Factory the recipe loads via `entrypoint.target = my_agent:build_graph`."""
    return _MinimalGraph()
