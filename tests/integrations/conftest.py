"""Project-root pytest configuration for integration tests.

Adds `src/` to sys.path and triggers registration of all
built-in families + requirements. Idempotent across test
modules."""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Register built-ins once at import time.
from compliance.integrations.families import register as register_families
register_families()

# Trigger requirement registration.
import importlib
importlib.import_module("compliance.requirements.ai_act.article_12_1")
