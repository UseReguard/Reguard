"""repo-runtime — generic Python repository runtime.

Three responsibilities only:

    * Inspect — static inventory of a checked-out repository.
    * Build   — construct an installable/testable environment.
    * Test    — run the repository test suite.

This package does NOT know about:
    * GitHub URLs or the GitHub API
    * The corpus SQLite database
    * agent_repositories / compliance status / legal articles

The contract is: host checks out a SHA, mounts the directory, the
runtime inspects / builds / tests it, and writes a structured JSON
result plus artifacts. The host then destroys the container.

See runtime/README.md for the security model and limitations.
"""
__all__ = [
    "models",
    "detect",
]
