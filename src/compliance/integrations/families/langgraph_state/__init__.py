"""LangGraph-state family (Family A in the discovery taxonomy).

Members (per CR-3 discovery sample):
    - langchain-ai/langchain @ 5893459c4f2bfac6c8d3262cae1e3f2246d9287f
    - langchain-ai/langgraph @ 11ee185999b86bfea2d8c0e69cef9a5e37acf686
    - bytedance/deer-flow     @ bf740ffa9077f55661fce80186b656651f497c89

All three expose a `CompiledStateGraph` execution shape with a
`messages` channel and an optional LangGraph checkpointer. They
share the same Recipe, ObserverSet, and Normalizer in v0.1.

The Recipe + ObserverSet + Normalizer are imported here so they
self-register on package import.
"""
from __future__ import annotations

from .recipe import LangGraphStateRecipe
from .observer import LangGraphStateObserverSet
from .normalizer import LangGraphStateNormalizer


def register() -> None:
    """Idempotent registration helper. Called from the families
    package __init__. The `register_*` calls happen at import time
    of each module below; this function exists so an explicit
    `families.register()` can be invoked from tests if needed."""
    from ...recipe import register_recipe
    from ...observer import register_observer
    from ...normalizer import register_normalizer

    register_recipe(LangGraphStateRecipe())
    register_observer(LangGraphStateObserverSet())
    register_normalizer(LangGraphStateNormalizer())


__all__ = [
    "LangGraphStateRecipe",
    "LangGraphStateObserverSet",
    "LangGraphStateNormalizer",
    "register",
]
