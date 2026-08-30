"""`reguard list` — enumerate registered recipes, observers,
normalizers, families, and built-in integrations."""
from __future__ import annotations

import argparse
import sys

from ..integrations.families import register as register_families, REGUARD_FAMILIES


def cmd_list(args: argparse.Namespace) -> int:
    register_families()
    what = args.what

    if what in ("all", "requirements"):
        print("Requirements:")
        from ..requirements.base import REQUIREMENT_REGISTRY
        import importlib
        importlib.import_module("compliance.requirements.ai_act.article_12_1")
        for rid in sorted(REQUIREMENT_REGISTRY):
            req = REQUIREMENT_REGISTRY[rid]
            print(f"  - {rid} @ {req.version}")
        print()

    if what in ("all", "recipes"):
        print("Recipes:")
        from ..integrations.recipe import all_recipes
        for r in all_recipes():
            print(f"  - {r.recipe_id} @ {r.recipe_version}")
            print(f"      supported scenarios: {', '.join(r.supported_scenarios)}")
        print()

    if what in ("all", "observers"):
        print("Observers:")
        from ..integrations.observer import all_observers
        for o in all_observers():
            print(f"  - {o.observer_id} @ {o.observer_version}")
        print()

    if what in ("all", "normalizers"):
        print("Normalizers:")
        from ..integrations.normalizer import all_normalizers
        for n in all_normalizers():
            print(f"  - {n.normalizer_id} @ {n.normalizer_version}")
        print()

    if what in ("all", "families"):
        print("Families:")
        for fid, info in REGUARD_FAMILIES.items():
            print(f"  - {fid}")
            print(f"      {info['description']}")
            print(f"      members: {', '.join(info['members'])}")
        print()

    if what in ("all", "integrations"):
        print("Built-in integrations:")
        from ..integrations.integrations_builtin import BUILTIN_INTEGRATIONS
        if BUILTIN_INTEGRATIONS:
            for full_name in BUILTIN_INTEGRATIONS:
                print(f"  - {full_name}")
        else:
            print("  (none — supply your own reguard.yml)")
        print()

    return 0
