"""Tests for runtime.commands.test — auto-setup lifecycle + supported strategies.

These verify that `test` mode can build its environment inside a single
container invocation, addressing the lifecycle gap where each fresh
container starts with no third-party packages installed.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from runtime.commands import test as test_cmd
from runtime.models import NetworkPolicy, Status


def _setup_pure_python_fixture(temp_dir: Path) -> Path:
    """Build a minimal pyproject repo whose tests pass after `pip install -e .`.

    The fixture's test imports from the package it just installed —
    exactly the lifecycle `test` mode must support.
    """
    repo = temp_dir / "pure-pyproject"
    repo.mkdir()
    pkg = repo / "ppkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("VALUE = 42\n")
    (pkg / "ops.py").write_text("def double(x):\n    return x * 2\n")
    (repo / "pyproject.toml").write_text(
        "[build-system]\n"
        "requires=['setuptools>=68']\n"
        "build-backend='setuptools.build_meta'\n"
        "[project]\n"
        "name='ppkg'\n"
        "version='0.1.0'\n"
    )
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_smoke.py").write_text(
        "import ppkg\n"
        "from ppkg.ops import double\n"
        "def test_value():\n"
        "    assert ppkg.VALUE == 42\n"
        "def test_double():\n"
        "    assert double(3) == 6\n"
    )
    return repo


def test_test_mode_unsupported_when_no_pytest_and_no_command(fixtures_map, temp_dir):
    repo_root = fixtures_map["01-pyproject-simple"]
    artifacts = temp_dir / "art"
    result = test_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=30,
        repo_sha="",
        auto_setup=False,   # even if setup were enabled, this fixture has no tests
    )
    assert result.status == Status.UNSUPPORTED


def test_test_mode_unsupported_for_poetry_project(fixtures_map, temp_dir):
    """Poetry repos must produce status=unsupported, not a missing-binary crash."""
    repo_root = fixtures_map["05-poetry"]
    artifacts = temp_dir / "art"
    result = test_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=30,
        repo_sha="",
    )
    assert result.status == Status.UNSUPPORTED


def test_test_mode_records_setup_commands(fixtures_map, temp_dir):
    """When auto_setup is enabled and the project is buildable, test mode
    should record the install command(s) in commands[] before the test command.
    """
    # 07-pytest has both pip-installable pyproject AND a pytest test directory.
    repo_root = fixtures_map["07-pytest"]
    artifacts = temp_dir / "art"
    result = test_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=60,
        repo_sha="",
        auto_setup=True,
        network_policy=NetworkPolicy.ENABLED,
    )
    # The fixture is pip-installable; install should be attempted.
    assert any(c.label.startswith("01_install") for c in result.commands), \
        f"expected an install command, got labels: {[c.label for c in result.commands]}"
    install = next(c for c in result.commands if c.label == "01_install")
    # On host Python 3.14 with PEP 668 this will fail; we only assert the
    # command was attempted.
    assert install.argv[:3] == [sys.executable, "-m", "pip"]


def test_test_mode_no_auto_setup_runs_only_test_command(fixtures_map, temp_dir):
    """With auto_setup=False, commands[] must contain only the test command."""
    repo_root = fixtures_map["07-pytest"]
    artifacts = temp_dir / "art"
    result = test_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=30,
        repo_sha="",
        auto_setup=False,
    )
    # No setup, just the test command.
    assert all(not c.label.startswith("00_setup") and not c.label.startswith("01_install")
               for c in result.commands), \
        f"unexpected setup commands: {[c.label for c in result.commands]}"
    assert any(c.label == "02_pytest" for c in result.commands)


def test_test_mode_explicit_command_skips_detection(fixtures_map, temp_dir):
    """An explicit --command must be used verbatim regardless of detection."""
    repo_root = fixtures_map["08-no-build-system"]   # no pytest, no packaging
    artifacts = temp_dir / "art"
    result = test_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=10,
        repo_sha="",
        command=["echo", "hello"],
        auto_setup=False,
    )
    assert result.status == Status.SUCCESS
    assert result.commands[0].argv == ["echo", "hello"]


def test_test_mode_lifecycle_does_not_modify_host_checkout(fixtures_map, temp_dir):
    """The host checkout must remain unchanged even after install+test."""
    repo_root = _setup_pure_python_fixture(temp_dir)   # host checkout here
    before = {str(p.relative_to(repo_root)): p.read_bytes()
              for p in repo_root.rglob("*") if p.is_file()}
    artifacts = temp_dir / "art"
    test_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=60,
        repo_sha="",
        auto_setup=True,
        network_policy=NetworkPolicy.ENABLED,
    )
    after = {str(p.relative_to(repo_root)): p.read_bytes()
             for p in repo_root.rglob("*") if p.is_file()}
    assert before == after, "test mode mutated the host checkout"


def test_test_mode_does_not_modify_repo_when_install_fails(temp_dir):
    """Even when install fails, /input must remain untouched."""
    # Create a repo with a deliberately broken install (invalid setup.py).
    repo = temp_dir / "broken-install"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[build-system]\n"
        "requires=['setuptools>=68']\n"
        "build-backend='setuptools.build_meta'\n"
        "[project]\n"
        "name='broken'\n"
        "version='0.1.0'\n"
    )
    (repo / "setup.py").write_text("raise RuntimeError('setup refused to run')\n")
    before_files = sorted(str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file())
    artifacts = temp_dir / "art"
    result = test_cmd.run(
        repo_path=repo,
        artifacts_dir=artifacts,
        timeout_seconds=30,
        repo_sha="",
        auto_setup=True,
        network_policy=NetworkPolicy.ENABLED,
    )
    after_files = sorted(str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file())
    assert before_files == after_files, "broken-install fixture was mutated"


def test_test_mode_records_workspace_isolation(fixtures_map, temp_dir):
    """After test mode runs, the host checkout should not contain __pycache__
    from pytest's own collection (because pytest runs in /workspace/repo,
    not /input)."""
    repo_root = fixtures_map["07-pytest"]
    artifacts = temp_dir / "art"
    test_cmd.run(
        repo_path=repo_root,
        artifacts_dir=artifacts,
        timeout_seconds=30,
        repo_sha="",
        auto_setup=False,
    )
    pycache_count = sum(1 for _ in repo_root.rglob("__pycache__"))
    # __pycache__ should never appear in the host checkout because pytest
    # ran in /workspace/repo (a copy). Some pytest plugins create
    # .pytest_cache though — that's also a side-effect we don't want.
    assert pycache_count == 0, \
        "host checkout now has __pycache__ — test ran in /input, not /workspace/repo"
