"""Built-in execution families.

A "family" bundles a Recipe, an ObserverSet, and a Normalizer
together. New families can be added by:

  1. dropping a new module under
     `src/compliance/integrations/families/<family_id>/`;
  2. importing the three classes here so they self-register on
     package import;
  3. declaring the family in `REGUARD_FAMILIES` (used by
     `reguard list`).

The v0.1 pilot ships exactly one family: `langgraph-state`.
"""
from __future__ import annotations

from .langgraph_state import (
    LangGraphStateRecipe,
    LangGraphStateObserverSet,
    LangGraphStateNormalizer,
)


def register() -> None:
    """Idempotent registration of all built-in families.

    Imports trigger the module-level registrations inside each
    family package; this function is therefore a convenient
    explicit hook."""
    from .langgraph_state import register as _lg
    _lg()


REGUARD_FAMILIES: dict[str, dict] = {
    "langgraph-state": {
        "family_id": "langgraph-state",
        "description": (
            "CompiledStateGraph + checkpointer shape (langchain, "
            "langgraph, deer-flow). Single shared Recipe, "
            "ObserverSet, and Normalizer across all three."
        ),
        "recipe_id": LangGraphStateRecipe.recipe_id,
        "observer_ids": [
            LangGraphStateObserverSet.observer_id,
        ],
        "normalizer_id": LangGraphStateNormalizer.normalizer_id,
        "members": [
            "langchain-ai/langchain",
            "langchain-ai/langgraph",
            "bytedance/deer-flow",
        ],
        "stub_model_strategy": "in-process fake chat model",
        "tool_injection_strategy": "constructor list (tools=[...])",
    },
}


def all_families() -> list[dict]:
    return [dict(v) for v in REGUARD_FAMILIES.values()]


__all__ = ["REGUARD_FAMILIES", "all_families"]
