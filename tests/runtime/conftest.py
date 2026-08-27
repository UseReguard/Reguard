"""Pytest fixtures and helpers for runtime tests."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


# Make runtime importable on the host so we can unit-test the inspect
# logic without Docker.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Point the runtime at a writable per-session tempdir. The runtime reads
# REPO_RUNTIME_WORKSPACE at import time to decide where to copy the host
# checkout for build/test modes. Without this, /workspace (the default)
# is not writable on developer hosts that don't run Docker.
_TEST_WORKSPACE = Path(tempfile.mkdtemp(prefix="runtime-tests-ws-"))
os.environ["REPO_RUNTIME_WORKSPACE"] = str(_TEST_WORKSPACE)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def temp_dir():
    """Writable temporary directory removed at the end of the test."""
    d = tempfile.mkdtemp(prefix="runtime-test-")
    try:
        yield Path(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def fixtures_map() -> dict[str, Path]:
    """Map fixture slug → absolute path."""
    out = {}
    for entry in sorted(FIXTURES_DIR.iterdir()):
        if entry.is_dir():
            out[entry.name] = entry
    return out


@pytest.fixture
def sentinel_cleanup():
    """Yield a list of sentinel paths; remove them after the test."""
    paths = [
        Path("/tmp/INSPECT_IMPORTED_A_REPO_MODULE"),
        Path("/tmp/INSPECT_EXECUTED_REPO_CODE"),
    ]
    for p in paths:
        p.unlink(missing_ok=True)
    yield paths
    for p in paths:
        p.unlink(missing_ok=True)
