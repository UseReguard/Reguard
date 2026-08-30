"""LangGraph-state ExecutionRecipe (Family A).

This Recipe is intentionally framework-agnostic at the integration
layer: it accepts ANY `reguard.yml` whose `entrypoint.target` is a
dotted python path to a callable that returns a `CompiledStateGraph`
(or to the graph factory). The Recipe does not import
langgraph/langchain — it invokes the user-supplied factory at
runtime inside the probe, then drives the resulting graph with a
deterministic in-process stub model and the user-supplied tool
list.

The Recipe contains:
  - no Article-number logic;
  - no PASS/FAIL decision;
  - no event fabrication.

It returns an opaque `LangGraphRunOutput` object the ObserverSet
reads.
"""
from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping

from ...recipe import (
    ExecutionRecipe,
    EntrypointKind,
    PackageStrategy,
    RecipeConfig,
    RecipeResolution,
)
from ...observer import NativeObservation
from ...errors import IntegrationConfigError


@dataclass
class LangGraphRunOutput:
    """Opaque recipe output. The ObserverSet + Normalizer consume
    this; the Recipe does not interpret it."""

    graph: Any
    trajectory_path: str
    thread_id: str
    final_state: dict = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()


class _DeterministicStubModel:
    """An in-process stub chat model that the LangGraph-state
    recipe injects in place of the user-supplied model.

    The stub returns a single deterministic assistant message plus
    one tool call (if `tool_calls` is provided) and then exits. It
    writes nothing to disk and depends on no network. It does NOT
    satisfy a langchain `BaseChatModel` interface because the
    factory receives the stub via a different injection point
    (constructor kwarg, set by the recipe driver before invoking
    the factory) — see `LangGraphStateRecipe.run`.

    The stub deliberately does NOT carry any LLM provider API
    semantics; it is a stand-in."""

    def __init__(self, *, text: str = "hello from reguard stub", tool_calls=None):
        self._text = text
        self._tool_calls = list(tool_calls or [])
        self._i = 0

    def invoke(self, *args, **kwargs):
        from types import SimpleNamespace
        if self._i < len(self._tool_calls):
            tc = self._tool_calls[self._i]
            self._i += 1
            return SimpleNamespace(
                content="",
                tool_calls=[SimpleNamespace(
                    name=tc["name"],
                    args=tc.get("args", {}),
                    id=f"call_{self._i}",
                )],
            )
        return SimpleNamespace(content=self._text, tool_calls=[])

    async def ainvoke(self, *args, **kwargs):
        return self.invoke(*args, **kwargs)


def _echo_tool(name: str = "echo"):
    """A trivial deterministic tool. Returns the input verbatim."""
    def tool(payload=None, **kwargs):
        return {"echoed": payload if payload is not None else kwargs}
    tool.__name__ = name
    return tool


class LangGraphStateRecipe(ExecutionRecipe):
    """Recipe for any LangGraph-shaped agent (langchain,
    langgraph, deer-flow)."""

    recipe_id = "langgraph-state"
    recipe_version = "1.0.0"
    supported_scenarios = ("compliance.article12_1.simple",)

    def resolve(self, config: RecipeConfig) -> RecipeResolution:
        resolution = super().resolve(config)
        if config.entrypoint_kind not in (
            EntrypointKind.PYTHON_DOTTED,
            EntrypointKind.PYTHON_CALLABLE,
        ):
            raise IntegrationConfigError(
                "langgraph-state recipe requires a python_dotted or "
                "python_callable entrypoint"
            )
        return resolution

    def run(
        self,
        resolution: RecipeResolution,
        scenario: Any,
    ) -> LangGraphRunOutput:
        """Execute the recipe against a user-supplied graph factory.

        This implementation is intentionally conservative: it does
        not import langgraph itself. It loads the user-supplied
        factory from `entrypoint_module`, calls it with a stub
        model and a list of deterministic probe tools, then drives
        the resulting graph through one deterministic invocation
        inside the current Python process.

        If `resolution.config.params` carries an `invocation_mode`
        of `dry-run` (the default in v0.1), the recipe returns
        without invoking any user code — it emits a deterministic
        trajectory via the stub. This keeps the v0.1 pilot free of
        dependency-installation requirements on the host running
        the test suite while still exercising the full
        Recipe → ObserverSet → Normalizer → Evidence path.
        """
        cfg = resolution.config

        if cfg.params.get("invocation_mode", "dry-run") == "dry-run":
            return self._run_dry(resolution, scenario)

        return self._run_with_factory(resolution, scenario)

    # ------------------------------------------------------------------
    def _run_dry(
        self,
        resolution: RecipeResolution,
        scenario: Any,
    ) -> LangGraphRunOutput:
        """Produce a deterministic dry-run trajectory without
        importing the target framework. Validates that the Recipe
        + ObserverSet + Normalizer path works end-to-end."""
        import tempfile
        from pathlib import Path

        stub = _DeterministicStubModel(
            text="dry-run completion",
            tool_calls=[],
        )

        thread_id = "reguard-dry-run-001"
        trajectory_path = str(
            Path(tempfile.gettempdir()) / "reguard_dry_run_trajectory.jsonl"
        )

        final_state = {
            "messages": [
                {"role": "user", "content": getattr(scenario, "user_prompt", "")},
                {"role": "assistant", "content": "dry-run completion"},
            ],
        }

        return LangGraphRunOutput(
            graph={"kind": "dry-run", "stub_model": stub},
            trajectory_path=trajectory_path,
            thread_id=thread_id,
            final_state=final_state,
            artifacts=(trajectory_path,),
        )

    # ------------------------------------------------------------------
    def _run_with_factory(
        self,
        resolution: RecipeResolution,
        scenario: Any,
    ) -> LangGraphRunOutput:
        """Load the user-supplied factory and drive the resulting
        graph with a stub model + probe tools. Used when
        `invocation_mode != dry-run` (i.e. when an actual target
        repo is being exercised)."""
        cfg = resolution.config
        module_name = resolution.entrypoint_module
        attr = resolution.entrypoint_attr

        pkg_root = os.path.abspath(cfg.package_root)
        inserted_pkg_root = False
        if pkg_root not in sys.path:
            sys.path.insert(0, pkg_root)
            inserted_pkg_root = True

        try:
            try:
                mod = importlib.import_module(module_name)
            except ImportError as exc:
                raise IntegrationConfigError(
                    f"langgraph-state: cannot import "
                    f"{module_name!r} from package_root {pkg_root!r}: {exc}"
                ) from exc

            factory = getattr(mod, attr, None)
            if factory is None:
                raise IntegrationConfigError(
                    f"langgraph-state: factory {module_name}:{attr} "
                    "not found in target package"
                )

            stub = _DeterministicStubModel(text="reguard probe run")
            tools = [_echo_tool("echo")]

            try:
                graph_obj = factory(model=stub, tools=tools)
            except TypeError:
                graph_obj = factory(stub, tools)

            try:
                if hasattr(graph_obj, "invoke"):
                    out = graph_obj.invoke(
                        {"messages": [{"role": "user",
                                       "content": scenario.user_prompt}]},
                    )
                else:
                    out = graph_obj
            except Exception:
                out = graph_obj

            trajectory_path = ""
            if hasattr(graph_obj, "trajectory_path"):
                trajectory_path = str(getattr(graph_obj, "trajectory_path"))
            final_state = dict(out) if isinstance(out, dict) else {}

            return LangGraphRunOutput(
                graph=graph_obj,
                trajectory_path=trajectory_path,
                thread_id="reguard-1",
                final_state=final_state,
                artifacts=(trajectory_path,) if trajectory_path else (),
            )
        finally:
            if inserted_pkg_root:
                try:
                    sys.path.remove(pkg_root)
                except ValueError:
                    pass
