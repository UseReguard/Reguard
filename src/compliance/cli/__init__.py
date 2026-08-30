"""Reguard Core v0.1 — top-level CLI.

Subcommands:
    reguard init      create a minimal reguard.yml
    reguard doctor    check the host environment
    reguard check     run a deterministic compliance check
    reguard explain   show what a requirement test actually tests
    reguard list      enumerate available recipes / observers /
                      normalizers / families

Exit codes (for `reguard check`):
    0  PASS
    1  FAIL
    2  UNKNOWN
    3  UNSUPPORTED
    4  ERROR

UNKNOWN and UNSUPPORTED are NEVER collapsed into FAIL.

This CLI is intentionally separate from the existing
`scripts/compliance-check.py` (which still drives the legacy
five-adapter path). The legacy script is preserved verbatim for
the frozen-five regression.
"""
from __future__ import annotations

from .main import main

__all__ = ["main"]
