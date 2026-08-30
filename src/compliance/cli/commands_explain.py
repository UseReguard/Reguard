"""`reguard explain` — show what a requirement test actually tests."""
from __future__ import annotations

import argparse
import sys


def _ensure_requirements_registered() -> None:
    """Trigger registration of the frozen Article 12(1) requirement
    test. Idempotent."""
    import importlib
    importlib.import_module("compliance.requirements.ai_act.article_12_1")


def cmd_explain(args: argparse.Namespace) -> int:
    from ..requirements.base import REQUIREMENT_REGISTRY, get_requirement

    _ensure_requirements_registered()

    rid = args.requirement_id
    try:
        req = get_requirement(rid)
    except KeyError:
        print(f"reguard explain: unknown requirement_id {rid!r}", file=sys.stderr)
        print("Available:", ", ".join(sorted(REQUIREMENT_REGISTRY.keys())))
        return 1

    print(f"Requirement     : {req.id}")
    print(f"Contract version: {req.version}")
    print()
    print("Technical contract")
    print(
        "  Verify that the agent runtime itself records events "
        "automatically during a controlled invocation, with at "
        "least one step/tool/model event tagged SYSTEM_NATIVE or "
        "SYSTEM_STATE_EXPORTED_BY_HARNESS and a corresponding "
        "framework-side durable artefact."
    )
    print()
    print("Required observations")
    print("  - ≥ 1 non-error event of kind step / tool / model")
    print("  - 0 HARNESS_GENERATED events")
    print("  - recording category A or B (framework-side durability)")
    print("  - framework-side durable artefact path")
    print()
    print("Explicit limitations")
    print("  - Does not certify EU AI Act compliance.")
    print("  - Does not score foundation-model properties.")
    print("  - Does not infer compliance from source patterns.")
    return 0
