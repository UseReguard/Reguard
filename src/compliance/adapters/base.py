"""Adapter interface — one concrete class per agent framework.

An adapter knows how to:
    1. Locate the agent under test inside a repo checkout.
    2. Build a controlled scenario that exercises the agent.
    3. Translate the agent's native log/trajectory into a normalised
       Evidence object.

The adapter does NOT decide pass/fail. That is the RequirementTest's job.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from compliance.pipeline.types import Evidence, RepositoryTarget, Scenario


@dataclass(frozen=True)
class AdapterCapabilities:
    """Static metadata describing what an adapter requires from the host."""

    python_version: str = "3.12"
    needs_network: bool = False
    """If True, the container must permit outbound traffic (e.g. for
    package installs). The orchestrator chooses the right NetworkPolicy."""
    install_timeout_seconds: int = 600
    run_timeout_seconds: int = 120
    install_command: str = ""
    """Shell command run inside the repo working dir during probe
    install. Empty means: install via `pip install -e .` (auto)."""
    supported_scenarios: tuple[str, ...] = field(default_factory=tuple)
    """Scenario IDs the adapter's probe currently exercises. Used by
    the Corpus Runner for orchestration-level eligibility checks.
    Adapters that do not declare any scenario are conservatively
    treated as supporting the baseline Article 12(1) scenario only.
    This field is additive and does not change verdict semantics.
    """


class RepoAdapter(ABC):
    """Base class for per-repo adapters."""

    name: str = "UNSET"
    version: str = "0.0.0"

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    def resolve_agent(self, repo_root: str) -> str:
        """Return the importable python dotted path of the agent class.

        Example: 'minisweagent.agents.default.DefaultAgent'.

        Used by the probe to import the agent class without hard-coding
        per-agent knowledge in the test harness.
        """

    @abstractmethod
    def render_synthetic_task(self, scenario: Scenario) -> str:
        """Translate the deterministic scenario into the agent's native
        task format. The output should be deterministic and identical
        across runs."""

    @abstractmethod
    def parse_trajectory(self, trajectory_path: str, scenario: Scenario) -> Evidence:
        """Read whatever the agent wrote to disk during the run and turn
        it into a normalised Evidence object. Raise on I/O errors but
        never silently fabricate events."""

    def supported_repository(self, repo: RepositoryTarget) -> bool:
        """Return True if this adapter claims the given repo. The
        orchestrator dispatches by full_name match against a registry."""
        return True