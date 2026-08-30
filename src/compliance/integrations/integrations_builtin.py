"""Built-in integration manifests shipped with Reguard Core v0.1.

The pilot ships manifests for the three Family-A repositories
that are config-only candidates:

    - langchain-ai/langchain
    - langchain-ai/langgraph
    - bytedance/deer-flow

Each manifest selects the same shared Recipe, ObserverSet, and
Normalizer. Per-repo differences are entirely declarative
(entrypoint target, package root).

These manifests do NOT include any frozen CR-3 SHAs in the
runtime resolution path; the SHAs live in the corpus layer and
are passed through the orchestrator. The integration manifest
is configuration-only.
"""
from __future__ import annotations

from typing import Any


# Recipe + ObserverSet + Normalizer are the same across all three
# Family-A manifests. Per-repo differences are entrypoint + root.
_FAMILY_A_RECIPE = "langgraph-state"
_FAMILY_A_OBSERVER = "langgraph-state.callback-observer"
_FAMILY_A_NORMALIZER = "langgraph-state.canonical-normalizer"
_FAMILY_A_SCENARIOS = ("compliance.article12_1.simple",)


def _manifest(
    *,
    entrypoint_target: str,
    package_root: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "integration": {
            "recipe": _FAMILY_A_RECIPE,
            "recipe_version": "1.0.0",
            "package_root": package_root,
            "entrypoint": {
                "target": entrypoint_target,
                "mode": "sync",
            },
            "model": {"strategy": "deterministic_stub"},
            "observers": [_FAMILY_A_OBSERVER],
            "normalizer": {"id": _FAMILY_A_NORMALIZER},
            "params": params or {"invocation_mode": "dry-run"},
        },
        "scenarios": list(_FAMILY_A_SCENARIOS),
    }


BUILTIN_INTEGRATIONS: dict[str, dict] = {
    "langchain-ai/langchain": _manifest(
        entrypoint_target="langchain.agents.factory:create_agent",
        package_root="libs/langchain_v1",
        params={"invocation_mode": "dry-run"},
    ),
    "langchain-ai/langgraph": _manifest(
        entrypoint_target="langgraph.graph:StateGraph",
        package_root="libs/langgraph",
        params={"invocation_mode": "dry-run"},
    ),
    "bytedance/deer-flow": _manifest(
        entrypoint_target="deerflow.agents:_assemble_lead_agent",
        package_root=".",
        params={"invocation_mode": "dry-run"},
    ),
}


def all_builtin_integrations() -> dict[str, dict]:
    return dict(BUILTIN_INTEGRATIONS)
