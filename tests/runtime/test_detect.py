"""Tests for runtime.detect — static detection of build strategy."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.detect import (
    BUILD_STRATEGY_PIP, BUILD_STRATEGY_POETRY, BUILD_STRATEGY_SETUPTOOLS,
    BUILD_STRATEGY_UV, BUILD_STRATEGY_PIPENV, BUILD_STRATEGY_NONE,
    detect,
)


def _strategy(fixtures_map, slug):
    repo_root = fixtures_map[slug]
    _, strategy = detect(repo_root)
    return strategy


def test_pyproject_simple_uses_pip_with_hatchling(fixtures_map):
    """A bare pyproject.toml without poetry/uv locks → pip editable install."""
    strategy = _strategy(fixtures_map, "01-pyproject-simple")
    assert strategy.strategy == BUILD_STRATEGY_PIP
    assert strategy.command[-2:] == ["-e", "."]
    assert strategy.command[0].endswith("python") or strategy.command[0].endswith("python3")


def test_src_layout_detection(fixtures_map):
    repo_root = fixtures_map["02-src-layout"]
    detection, _ = detect(repo_root)
    assert detection.layout == "src"
    assert detection.has_pyproject is True
    assert detection.build_system == "setuptools"


def test_requirements_only_uses_pip(fixtures_map):
    strategy = _strategy(fixtures_map, "03-requirements-txt")
    assert strategy.strategy == BUILD_STRATEGY_PIP
    assert any("requirements" in a for a in strategy.command)


def test_uv_lock_wins_over_pyproject(fixtures_map):
    """When uv.lock exists, that overrides the pyproject build-system."""
    strategy = _strategy(fixtures_map, "04-uv-lock")
    assert strategy.strategy == BUILD_STRATEGY_UV
    # setup step should be `uv sync --frozen`
    assert strategy.setup and strategy.setup[0] == "uv"
    assert strategy.setup[-1] == "--frozen"


def test_poetry_lock_is_supported_when_runtime_installs_poetry(fixtures_map):
    """The runtime image installs Poetry 2.x, so a poetry.lock repo
    gets a real install command (not an empty unsupported one).

    The strategy still resolves to "poetry", but the command now
    runs `poetry install --no-interaction --only main` so dependency
    installation actually happens.
    """
    strategy = _strategy(fixtures_map, "05-poetry")
    assert strategy.strategy == BUILD_STRATEGY_POETRY
    assert strategy.command  # non-empty install command
    assert strategy.command[0] == "poetry"
    assert "poetry" not in __import__("runtime").detect.UNSUPPORTED_STRATEGIES


def test_pyproject_with_poetry_metadata_is_supported(fixtures_map, temp_dir):
    """A pyproject.toml using [tool.poetry] without a lockfile gets a
    real install command when Poetry is installed in the runtime."""
    repo = temp_dir / "poetry_only_pyproject"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[tool.poetry]\nname='x'\nversion='0.1.0'\n"
        "[build-system]\nrequires=['poetry-core']\n"
        "build-backend='poetry.core.masonry.api'\n"
    )
    _, strategy = detect(repo)
    assert strategy.strategy == BUILD_STRATEGY_POETRY
    assert strategy.command  # non-empty install command


def test_setup_py_legacy_uses_setuptools(fixtures_map):
    repo_root = fixtures_map["06-setup-py-legacy"]
    detection, strategy = detect(repo_root)
    assert detection.has_setup_py is True
    assert detection.build_system == "setuptools"
    assert detection.python_version_constraint == ">=3.8"
    assert strategy.strategy == BUILD_STRATEGY_SETUPTOOLS


def test_pytest_project_detected(fixtures_map):
    repo_root = fixtures_map["07-pytest"]
    detection, _ = detect(repo_root)
    assert detection.test_framework == "pytest"


def test_no_build_system_returns_none(fixtures_map):
    repo_root = fixtures_map["08-no-build-system"]
    detection, strategy = detect(repo_root)
    assert detection.package_manager is None
    assert strategy.strategy == BUILD_STRATEGY_NONE


def test_invalid_python_does_not_crash_detection(fixtures_map):
    """Detection should be robust to syntactically broken .py files."""
    repo_root = fixtures_map["09-invalid-python"]
    # Should not raise — detection only walks paths, it does not parse.
    detection, _ = detect(repo_root)
    assert detection.python_files >= 2


def test_detection_is_deterministic(fixtures_map):
    """Two runs over the same repo must produce equivalent Detection dicts."""
    repo_root = fixtures_map["01-pyproject-simple"]
    d1, s1 = detect(repo_root)
    d2, s2 = detect(repo_root)
    assert d1 == d2
    assert s1 == s2


def test_uv_lock_precedence_over_poetry_marker(fixtures_map, temp_dir):
    """If both uv.lock and a pyproject with [tool.poetry] exist, uv wins."""
    repo = temp_dir / "combo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[tool.poetry]\nname='x'\nversion='0.1.0'\n"
        "[build-system]\nrequires=['poetry-core']\n"
        "build-backend='poetry.core.masonry.api'\n"
    )
    (repo / "uv.lock").write_text("version = 1\n")
    _, strategy = detect(repo)
    assert strategy.strategy == BUILD_STRATEGY_UV


def test_pipfile_is_reported_unsupported(fixtures_map, temp_dir):
    repo = temp_dir / "pipenv"
    repo.mkdir()
    (repo / "Pipfile").write_text('[[source]]\nname="pypi"\n')
    _, strategy = detect(repo)
    # We surface it explicitly so the host can decide.
    assert strategy.strategy == BUILD_STRATEGY_PIPENV
    assert strategy.command == []


def test_pyproject_uses_poetry_without_lock(fixtures_map, temp_dir):
    repo = temp_dir / "poetry_only_pyproject"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[tool.poetry]\nname='x'\nversion='0.1.0'\n"
        "[build-system]\nrequires=['poetry-core']\n"
        "build-backend='poetry.core.masonry.api'\n"
    )
    _, strategy = detect(repo)
    # Poetry is now installed in the runtime; the strategy resolves
    # to a real install command instead of an unsupported stub.
    assert strategy.strategy == BUILD_STRATEGY_POETRY
    assert strategy.command
