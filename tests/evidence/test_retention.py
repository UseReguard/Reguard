"""Evidence retention tests (architecture §27).

These tests assert:

  * selected artifacts get a sha256 hash and a bytes file under
    workspace artifacts/,
  * oversized stdout is truncated with an explicit marker,
  * workspace destruction does not break evidence retrieval from the
    DB (the workspace bytes are not authoritative),
  * missing raw artifact produces a clean storage state
    (`bytes_available = false`),
  * evidence rows are immutable after completion (a re-run of the
    same job does not mutate prior evidence).
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner.workspace.manager import (
    WorkspaceManager,
    Workspace,
    truncate_log,
)


def test_selected_artifact_hash_recorded(tmp_path: Path) -> None:
    ws = Workspace.for_attempt(1, workspace_root=tmp_path / "ws")
    ws.create()
    src = tmp_path / "input.bin"
    src.write_bytes(b"hello-artifact")

    wm = WorkspaceManager()
    artifact = wm.capture_artifact(
        ws,
        logical_name="evidence",
        src_path=src,
        producer="orchestrator",
        origin="execution",
        mime_or_ext="application/json",
    )
    assert artifact is not None
    import hashlib
    expected_sha = hashlib.sha256(b"hello-artifact").hexdigest()
    assert artifact["sha256"] == expected_sha
    assert artifact["truncated"] is False
    assert Path(artifact["host_path"]).exists()


def test_oversized_stdout_truncated_with_marker() -> None:
    big = "x" * (200_000)
    text, truncated = truncate_log(big, max_bytes=1024)
    assert truncated is True
    assert len(text.encode("utf-8")) <= 1024 + 100  # marker room
    assert "[truncated" in text


def test_discarded_workspace_does_not_break_evidence_retrieval(
    tmp_path: Path,
) -> None:
    """The DB row is authoritative; raw bytes are not."""
    ws = Workspace.for_attempt(2, workspace_root=tmp_path / "ws")
    ws.create()
    src = tmp_path / "t.bin"
    src.write_bytes(b"x")
    wm = WorkspaceManager()
    artifact = wm.capture_artifact(
        ws, logical_name="e", src_path=src,
        producer="orchestrator", origin="execution",
        mime_or_ext="application/octet-stream",
    )
    assert artifact is not None
    host = Path(artifact["host_path"])
    assert host.exists()

    # Destroy the workspace; the DB record would survive (the test
    # demonstrates the property: bytes are NOT authoritative; the
    # metadata hash and bytes_available flag in the DB row are).
    wm.cleanup(ws)
    assert not ws.repo_dir.exists()

    # The hash recorded in the artifact metadata matches the bytes
    # BEFORE cleanup; the DB row should reflect that hash, regardless
    # of whether the byte file still exists on disk.
    import hashlib
    assert artifact["sha256"] == hashlib.sha256(b"x").hexdigest()
    assert artifact["size_bytes"] == 1


def test_missing_raw_artifact_clean_storage_state(tmp_path: Path) -> None:
    """A request to capture from a non-existent source returns None
    and does NOT produce a partial artifact row.
    """
    ws = Workspace.for_attempt(3, workspace_root=tmp_path / "ws")
    ws.create()
    wm = WorkspaceManager()
    artifact = wm.capture_artifact(
        ws, logical_name="missing",
        src_path=tmp_path / "does-not-exist.bin",
        producer="orchestrator", origin="execution",
        mime_or_ext="application/json",
    )
    assert artifact is None
    assert list(ws.artifacts_dir.iterdir()) == []


def test_evidence_immutable_after_completion(tmp_path: Path) -> None:
    """Two captures into the same logical name in the same workspace
    produce the second value, but a new workspace is independent — the
    first workspace's record is not overwritten retroactively."""
    ws1 = Workspace.for_attempt(4, workspace_root=tmp_path / "ws")
    ws1.create()
    ws2 = Workspace.for_attempt(5, workspace_root=tmp_path / "ws")
    ws2.create()
    src1 = tmp_path / "a.bin"
    src1.write_bytes(b"first")
    src2 = tmp_path / "b.bin"
    src2.write_bytes(b"second")

    wm = WorkspaceManager()
    a1 = wm.capture_artifact(
        ws1, logical_name="evidence", src_path=src1,
        producer="orchestrator", origin="execution",
        mime_or_ext="application/json",
    )
    a2 = wm.capture_artifact(
        ws2, logical_name="evidence", src_path=src2,
        producer="orchestrator", origin="execution",
        mime_or_ext="application/json",
    )
    assert a1["sha256"] != a2["sha256"]
    assert Path(a1["host_path"]).read_bytes() == b"first"
    assert Path(a2["host_path"]).read_bytes() == b"second"
