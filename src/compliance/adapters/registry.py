"""Concrete per-framework adapters.

Each adapter registers itself in ADAPTER_REGISTRY keyed by
repository full_name (e.g. "SWE-agent/mini-swe-agent"). The
orchestrator looks up the right adapter by exact full_name.
"""
from __future__ import annotations

from .base import RepoAdapter
from .corecoder import CoreCoderAdapter
from .gptme import GptMeAdapter
from .mini_swe_agent import MiniSweAgentAdapter
from .nanobot import NanobotAdapter
from .pocketflow import PocketFlowAdapter

ADAPTER_REGISTRY: dict[str, RepoAdapter] = {
    "SWE-agent/mini-swe-agent": MiniSweAgentAdapter(),
    "he-yufeng/CoreCoder": CoreCoderAdapter(),
    "HKUDS/nanobot": NanobotAdapter(),
    # P3 batch: a small library and a session-persistent agent.
    "The-Pocket/PocketFlow": PocketFlowAdapter(),
    "gptme/gptme": GptMeAdapter(),
}


def get_adapter(full_name: str) -> RepoAdapter:
    if full_name not in ADAPTER_REGISTRY:
        raise KeyError(f"no adapter registered for {full_name!r}")
    return ADAPTER_REGISTRY[full_name]


__all__ = ["ADAPTER_REGISTRY", "get_adapter"]