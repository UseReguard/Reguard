"""Project-root pytest configuration.

Adds `src/` to sys.path so tests can `from compliance.X import …` even
when the package is not yet installed editable. Also keeps the project
root on sys.path so `runtime.X` (a top-level package next to `src/`)
remains importable.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC = PROJECT_ROOT / "src"

for p in (str(PROJECT_ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)