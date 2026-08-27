"""Per-repo adapters that operate a repository under the runtime.

An adapter knows how to drive a specific kind of AI-agent system
(mini-swe-agent, nanobot, CoreCoder, …) inside a fresh per-run
virtual environment. The pipeline wires one adapter per corpus
row and records the deterministic result.

Public surface
--------------
ADAPTER_REGISTRY   full_name → RepoAdapter
get_adapter(full_name) → RepoAdapter (raises KeyError on miss)
"""
from __future__ import annotations

from .registry import ADAPTER_REGISTRY, get_adapter

__all__ = ["ADAPTER_REGISTRY", "get_adapter"]