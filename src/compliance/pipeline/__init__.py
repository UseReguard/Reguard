"""Compliance pipeline: clone → SHA → runtime → deterministic result.

The pipeline orchestrates a single compliance check for one repository
in the corpus:

    1.  pick a corpus row         (corpus domain)
    2.  clone the repo at a SHA   (provenance)
    3.  run a per-repo adapter    (adapters domain)
    4.  score the evidence        (requirements domain)
    5.  write the verdict         (persistence)

The first requirement is hard-coded to AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
via `compliance.requirements.ai_act.article_12_1`.
"""
from __future__ import annotations

__all__ = [
    "RUNTIME_VERSION",
    "REQUIREMENT_VERSION",
]

RUNTIME_VERSION = "1.0.0"
REQUIREMENT_VERSION = "12.1/2026-08-27"