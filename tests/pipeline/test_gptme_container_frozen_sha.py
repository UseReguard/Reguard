"""gptme probe via container executor at the frozen SHA.

This integration test verifies the Article 12(1) gptme probe path
runs cleanly through the container executor — the SAME
`container_runner.run_in_container()` call used by production
probes — at the historically pinned SHA.

Expected outcome at frozen SHA ``c574b83d34f970f816af18183bd77d01b22bd504``:

  * category=B (session-persistent recorder), status=PASS,
    requirement_version=1.4.0.

Skipped when no OCI runtime is on PATH or when the container
image is not available locally.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pytest

from compliance.adapters.registry import get_adapter
from compliance.pipeline.driver import run_one
from compliance.pipeline.persistence import (
    default_db_path,
    insert_run,
    load_run_by_dedup_key,
)
from compliance.pipeline.types import RunRecord


GPTME_FULL_NAME = "gptme/gptme"
GPTME_FROZEN_SHA = "c574b83d34f970f816af18183bd77d01b22bd504"


def _have_oci_runtime() -> bool:
    return shutil.which("docker") is not None or shutil.which("podman") is not None


pytestmark = pytest.mark.skipif(
    not _have_oci_runtime(),
    reason="no OCI runtime on PATH (docker or podman) — "
           "container executor integration test cannot run",
)


@pytest.fixture(autouse=True)
def _select_working_runtime(monkeypatch):
    """Pick a runtime that actually works on this host.

    The container_runner's discovery prefers docker first. On WSL
    hosts where `docker` is a non-functional shim, the runner will
    invoke it and fail with "docker exited 1". Prefer podman when
    it works; fall back to docker only when no other runtime is
    available. Also pin the runtime image to the local
    `localhost/python-agent-runtime:dev` tag so the test doesn't
    need a registry pull.
    """
    if shutil.which("podman") is not None:
        monkeypatch.setenv("REGUARD_RUNTIME_BINARY", "podman")
    monkeypatch.setenv(
        "REGUARD_RUNTIME_IMAGE",
        os.environ.get(
            "REGUARD_RUNTIME_IMAGE",
            "localhost/python-agent-runtime:dev",
        ),
    )
    yield


def test_gptme_container_frozen_sha_reproduces_pass():
    """Run gptme at frozen SHA via container executor.

    Asserts:
      * clone of pinned SHA succeeds (the SHA exists upstream),
      * the container executor runs the gptme probe end-to-end,
      * the result is a category=B PASS at requirement_version 1.4.0.

    Pre-clears the dedup row for this exact key so the probe is
    not skipped. The dedup key is:
        (repository_id, requirement_id, requirement_version,
         repo_sha, scenario_id, adapter_name, adapter_version)
    """
    db = default_db_path()
    # Pre-clear: any cached row at the frozen SHA hides fresh
    # probe results via load_run_by_dedup_key.
    import sqlite3
    con = sqlite3.connect(db)
    try:
        con.execute(
            "DELETE FROM compliance_runtime_runs "
            "WHERE repo_full_name = ? AND repo_sha = ? "
            "AND requirement_version = ?",
            (GPTME_FULL_NAME, GPTME_FROZEN_SHA, "1.4.0"),
        )
        con.commit()
    finally:
        con.close()

    record = run_one(
        full_name=GPTME_FULL_NAME,
        sha=GPTME_FROZEN_SHA,
        keep_repo=False,
        executor="container",
        # gptme==0.31.0 is preinstalled in the runtime image; the
        # container runs with --network none so we cannot pip install
        # at probe time. Skip the runtime's install step.
        container_skip_install=True,
    )

    assert isinstance(record, RunRecord), (
        f"expected RunRecord, got {type(record).__name__}"
    )
    # Identity is preserved: the SHA we asked for is the SHA the
    # record ran against.
    assert record.repository.sha == GPTME_FROZEN_SHA, (
        f"SHA mismatch: requested {GPTME_FROZEN_SHA}, "
        f"got {record.repository.sha}"
    )
    assert record.requirement_version == "1.4.0"
    assert record.adapter_name == get_adapter(GPTME_FULL_NAME).name
    # Frozen-SHA gptme must be category=B (session-persistent
    # recorder) and status=PASS.
    cat = (record.evidence.extra or {}).get("recording_category")
    assert cat == "B", (
        f"gptme frozen-SHA category must be B, got {cat!r}; "
        f"status={record.status} reason={record.reason}"
    )
    assert record.status == "PASS", (
        f"gptme frozen-SHA must PASS, got status={record.status} "
        f"reason={record.reason}"
    )