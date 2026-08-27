"""Tests for runtime.commands.inspect — security & invariants.

These tests run on the host (no Docker). The inspect logic is pure
stdlib and behaves the same inside the container as outside.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from runtime.commands import inspect as inspect_cmd
from runtime.models import NetworkPolicy, Status


# ---------------------------------------------------------------------------
# Behaviour: inspect never executes repo code
# ---------------------------------------------------------------------------

def test_inspect_does_not_import_repo_module(fixtures_map, temp_dir, sentinel_cleanup):
    """A repo module that writes a sentinel on import must not run."""
    repo_root = fixtures_map["10-malicious"]
    artifacts = temp_dir / "artifacts"
    result = inspect_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=30,
        repo_sha="deadbeef",
        output_path=artifacts / "result.json",
        network_policy=NetworkPolicy.NONE,
    )
    assert Path("/tmp/INSPECT_IMPORTED_A_REPO_MODULE").exists() is False
    assert Path("/tmp/INSPECT_EXECUTED_REPO_CODE").exists() is False
    assert result.status == Status.SUCCESS


def test_inspect_does_not_run_setup_py(fixtures_map, temp_dir, sentinel_cleanup):
    """Even on a fixture with a setup.py, inspect must not execute it."""
    # We don't have a malicious setup.py in the fixtures; instead we
    # verify that the inspect command records no `commands[]` entries
    # for any fixture.
    for slug in ("01-pyproject-simple", "06-setup-py-legacy",
                 "07-pytest", "10-malicious"):
        repo_root = fixtures_map[slug]
        artifacts = temp_dir / f"art-{slug}"
        result = inspect_cmd.run(
            repo_path=repo_root,
            artifacts_dir=artifacts,
            timeout_seconds=30,
            repo_sha="",
            network_policy=NetworkPolicy.NONE,
        )
        assert result.commands == [], \
            f"{slug}: inspect must record zero commands, got {result.commands}"
        assert result.exit_code == 0


def test_inspect_does_not_install_dependencies(fixtures_map, temp_dir):
    """Inspect must never invoke pip / uv / poetry."""
    banned = {"pip", "uv", "poetry", "setuptools", "pipenv"}
    for slug, repo_root in fixtures_map.items():
        artifacts = temp_dir / f"art-{slug}"
        result = inspect_cmd.run(
            repo_path=repo_root,
            artifacts_dir=artifacts,
            timeout_seconds=30,
            repo_sha="",
            network_policy=NetworkPolicy.NONE,
        )
        for cmd in result.commands:
            argv0 = Path(cmd.argv[0]).name if cmd.argv else ""
            assert argv0 not in banned, \
                f"{slug}: inspect invoked banned binary {argv0}"


# ---------------------------------------------------------------------------
# Behaviour: /input is never modified
# ---------------------------------------------------------------------------

def test_inspect_does_not_modify_repo(fixtures_map, temp_dir):
    repo_root = fixtures_map["01-pyproject-simple"]
    before = _hash_tree(repo_root)
    inspect_cmd.run(
        repo_path=repo_root,
        artifacts_dir=temp_dir / "art",
        timeout_seconds=30,
        repo_sha="",
        network_policy=NetworkPolicy.NONE,
    )
    after = _hash_tree(repo_root)
    assert before == after, "inspect mutated the host checkout"


def _hash_tree(root: Path) -> dict[str, str]:
    """Hash every file under root (paths relative to root)."""
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            try:
                out[str(p.relative_to(root))] = hashlib.sha256(
                    p.read_bytes()).hexdigest()
            except OSError:
                pass
    return out


# ---------------------------------------------------------------------------
# Behaviour: structured result is produced
# ---------------------------------------------------------------------------

def test_inspect_produces_result_json(fixtures_map, temp_dir):
    repo_root = fixtures_map["01-pyproject-simple"]
    out = temp_dir / "art" / "result.json"
    inspect_cmd.run(
        repo_path=repo_root,
        artifacts_dir=temp_dir / "art",
        timeout_seconds=30,
        repo_sha="abc123",
        output_path=out,
        network_policy=NetworkPolicy.NONE,
    )
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["schema_version"] == "1"
    assert data["mode"] == "inspect"
    assert data["repo"]["sha"] == "abc123"
    assert data["status"] == "success"


def test_inspect_records_python_files_inventory(fixtures_map, temp_dir):
    repo_root = fixtures_map["07-pytest"]
    artifacts = temp_dir / "art"
    inspect_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=30,
        repo_sha="",
        network_policy=NetworkPolicy.NONE,
    )
    inventory = json.loads((artifacts / "python_files.json").read_text())
    paths = {row["path"] for row in inventory}
    assert "pytest_pkg/__init__.py" in paths
    assert "tests/test_smoke.py" in paths
    # Every entry has parse_ok=True for valid syntax.
    assert all(row["parse_ok"] for row in inventory)


def test_inspect_reports_syntax_error_without_crashing(fixtures_map, temp_dir):
    repo_root = fixtures_map["09-invalid-python"]
    artifacts = temp_dir / "art"
    result = inspect_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=30,
        repo_sha="",
        network_policy=NetworkPolicy.NONE,
    )
    assert result.status == Status.SUCCESS
    inventory = json.loads((artifacts / "python_files.json").read_text())
    bad = [row for row in inventory if row["path"].endswith("syntax_error.py")]
    assert bad and not bad[0]["parse_ok"]
    assert "syntax" in (bad[0]["syntax_error"] or "").lower()


def test_inspect_detects_pytest_framework(fixtures_map, temp_dir):
    repo_root = fixtures_map["07-pytest"]
    result = inspect_cmd.run(
        repo_path=repo_root,
        artifacts_dir=temp_dir / "art",
        timeout_seconds=30,
        repo_sha="",
        network_policy=NetworkPolicy.NONE,
    )
    assert result.detection.test_framework == "pytest"


def test_inspect_detects_uv_lock(fixtures_map, temp_dir):
    repo_root = fixtures_map["04-uv-lock"]
    result = inspect_cmd.run(
        repo_path=repo_root,
        artifacts_dir=temp_dir / "art",
        timeout_seconds=30,
        repo_sha="",
        network_policy=NetworkPolicy.NONE,
    )
    assert result.detection.has_uv_lock is True
    assert result.detection.package_manager == "uv"


def test_inspect_skips_cache_and_venv_dirs(fixtures_map, temp_dir):
    """We must never descend into venv / __pycache__ / .git etc."""
    repo_root = fixtures_map["01-pyproject-simple"]
    # Inject a venv and a __pycache__ to make sure they are ignored.
    (repo_root / "__pycache__").mkdir()
    (repo_root / "__pycache__" / "should_not_appear.py").write_text("x = 1")
    (repo_root / "venv").mkdir()
    (repo_root / "venv" / "lib.py").write_text("x = 2")
    try:
        result = inspect_cmd.run(
            repo_path=repo_root,
            artifacts_dir=temp_dir / "art",
            timeout_seconds=30,
            repo_sha="",
            network_policy=NetworkPolicy.NONE,
        )
        inventory = json.loads(
            (temp_dir / "art" / "python_files.json").read_text())
        paths = {row["path"] for row in inventory}
        assert "should_not_appear.py" not in str(paths)
        assert "venv/lib.py" not in str(paths)
    finally:
        # Clean up the injection so other tests are unaffected.
        import shutil
        shutil.rmtree(repo_root / "__pycache__", ignore_errors=True)
        shutil.rmtree(repo_root / "venv", ignore_errors=True)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_inspect_output_is_deterministic(fixtures_map, temp_dir):
    repo_root = fixtures_map["07-pytest"]
    a = temp_dir / "a"; b = temp_dir / "b"
    inspect_cmd.run(repo_path=repo_root, artifacts_dir=a, timeout_seconds=30,
                    repo_sha="", network_policy=NetworkPolicy.NONE,
                    output_path=a / "result.json")
    inspect_cmd.run(repo_path=repo_root, artifacts_dir=b, timeout_seconds=30,
                    repo_sha="", network_policy=NetworkPolicy.NONE,
                    output_path=b / "result.json")
    ra = json.loads((a / "result.json").read_text())
    rb = json.loads((b / "result.json").read_text())
    # `duration_ms` and `python_files` count are stable; the rest must be identical.
    assert ra["detection"] == rb["detection"]
    assert ra["commands"] == rb["commands"]
    assert sorted(ra["extra"]["text_files"]) == sorted(rb["extra"]["text_files"])
    assert sorted(ra["extra"]["config_files"]) == sorted(rb["extra"]["config_files"])
    # python_files inventory order must be sorted by path.
    ia = json.loads((a / "python_files.json").read_text())
    ib = json.loads((b / "python_files.json").read_text())
    assert ia == ib
    assert [r["path"] for r in ia] == sorted(r["path"] for r in ia)
