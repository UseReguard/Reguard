"""Unit tests for the three-abstraction integration model."""
from __future__ import annotations

import pytest

from compliance.integrations.recipe import (
    ExecutionRecipe,
    RecipeConfig,
    PackageStrategy,
    EntrypointKind,
    InvocationDriver,
    register_recipe,
    get_recipe,
    all_recipes,
)
from compliance.integrations.observer import (
    ObserverSet,
    ObserverContext,
    NativeObservation,
    register_observer,
    get_observer,
)
from compliance.integrations.normalizer import (
    Normalizer,
    NormalizerResult,
    register_normalizer,
    get_normalizer,
    PRODUCER_TO_ORIGIN,
    CANONICAL_EVENT_KINDS,
)


# ---------------------------------------------------------------------------
# Recipe
# ---------------------------------------------------------------------------
def test_recipe_register_and_lookup():
    register_recipe(ExecutionRecipe())
    # The langgraph-state recipe should be registered because
    # families/langgraph_state/__init__.py registers it on import.
    recipe = get_recipe("langgraph-state")
    assert recipe.recipe_id == "langgraph-state"


def test_recipe_unknown_id_raises():
    with pytest.raises(KeyError):
        get_recipe("not-a-real-recipe-id")


def test_recipe_resolve_dotted():
    from compliance.integrations.families.langgraph_state.recipe import (
        LangGraphStateRecipe,
    )
    recipe = LangGraphStateRecipe()
    cfg = RecipeConfig(
        recipe_id="langgraph-state",
        recipe_version="1.0.0",
        package_root=".",
        entrypoint_kind=EntrypointKind.PYTHON_DOTTED,
        entrypoint_target="my_agent:build_graph",
    )
    resolution = recipe.resolve(cfg)
    assert resolution.entrypoint_module == "my_agent"
    assert resolution.entrypoint_attr == "build_graph"


def test_recipe_resolve_missing_target_raises():
    from compliance.integrations.families.langgraph_state.recipe import (
        LangGraphStateRecipe,
    )
    recipe = LangGraphStateRecipe()
    cfg = RecipeConfig(
        recipe_id="langgraph-state",
        recipe_version="1.0.0",
        package_root=".",
        entrypoint_target="",
    )
    with pytest.raises(ValueError):
        recipe.resolve(cfg)


def test_recipe_dry_run_returns_opaque_output():
    from compliance.integrations.families.langgraph_state.recipe import (
        LangGraphStateRecipe,
    )
    from compliance.pipeline.types import Scenario

    recipe = LangGraphStateRecipe()
    cfg = RecipeConfig(
        recipe_id="langgraph-state",
        recipe_version="1.0.0",
        package_root=".",
        entrypoint_kind=EntrypointKind.PYTHON_DOTTED,
        entrypoint_target="x:y",
        params={"invocation_mode": "dry-run"},
    )
    resolution = recipe.resolve(cfg)
    out = recipe.run(resolution, Scenario(
        scenario_id="compliance.article12_1.simple",
        user_prompt="hello",
    ))
    assert out.thread_id
    assert out.final_state["messages"]


# ---------------------------------------------------------------------------
# Observer
# ---------------------------------------------------------------------------
def test_observer_register_and_lookup():
    obs = get_observer("langgraph-state.callback-observer")
    assert obs.observer_id == "langgraph-state.callback-observer"


def test_observer_unknown_id_raises():
    with pytest.raises(KeyError):
        get_observer("not-a-real-observer")


def test_native_observation_is_frozen():
    obs = NativeObservation(kind="step", producer="system", name="x")
    with pytest.raises(Exception):
        obs.kind = "tool"


def test_observer_set_producer_strings_map_to_canonical_origins():
    # producer -> EvidenceOrigin
    assert PRODUCER_TO_ORIGIN["system"] == "SYSTEM_NATIVE"
    assert PRODUCER_TO_ORIGIN["system_state"] == "SYSTEM_STATE_EXPORTED_BY_HARNESS"
    assert PRODUCER_TO_ORIGIN["harness"] == "HARNESS_GENERATED"


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------
def test_normalizer_register_and_lookup():
    n = get_normalizer("langgraph-state.canonical-normalizer")
    assert n.normalizer_id == "langgraph-state.canonical-normalizer"


def test_normalizer_unknown_id_raises():
    with pytest.raises(KeyError):
        get_normalizer("not-a-real-normalizer")


def test_normalizer_empty_observations_returns_category_E():
    from compliance.integrations.families.langgraph_state.normalizer import (
        LangGraphStateNormalizer,
    )
    n = LangGraphStateNormalizer()
    out = n.normalize([], recipe_id="langgraph-state", recipe_version="1.0.0")
    assert out.canonical_events == ()
    assert out.recording_category() == "E"
    assert not out.framework_persists_durably


def test_normalizer_canonicalizes_observations():
    from compliance.integrations.families.langgraph_state.normalizer import (
        LangGraphStateNormalizer,
    )
    n = LangGraphStateNormalizer()
    obs = [
        NativeObservation(
            kind="model_response",
            producer="system_state",
            name="assistant",
            content="hello",
            framework_artifact_ref="/tmp/agent_traj.jsonl",
        ),
    ]
    out = n.normalize(obs, recipe_id="langgraph-state", recipe_version="1.0.0")
    assert len(out.canonical_events) == 1
    ev = out.canonical_events[0]
    assert ev["origin"] == "SYSTEM_STATE_EXPORTED_BY_HARNESS"
    assert ev["kind"] == "model"
    assert out.recording_category() in ("A", "B")
    assert "/tmp/agent_traj.jsonl" in out.framework_artifact_paths


def test_canonical_event_kinds_are_a_frozenset():
    assert isinstance(CANONICAL_EVENT_KINDS, frozenset)
    assert "step" in CANONICAL_EVENT_KINDS
    assert "tool" in CANONICAL_EVENT_KINDS
    assert "model" in CANONICAL_EVENT_KINDS
    assert "checkpoint" in CANONICAL_EVENT_KINDS
