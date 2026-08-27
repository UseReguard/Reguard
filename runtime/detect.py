"""Static detection of build strategy, layout, and test framework.

Pure parsing — no execution. Every function here may import nothing
from the repository and may run arbitrary subprocesses only against
clearly-named tooling (e.g. `git`) but never against repository code.

Detection precedence for the build strategy is explicit:

    1. uv.lock             → uv
    2. poetry.lock         → poetry
    3. pyproject.toml      → project metadata parsing (PEP 621 + poetry table)
    4. Pipfile             → pipenv (rare; we report unsupported with reason)
    5. requirements*.txt   → pip
    6. setup.py / setup.cfg → setuptools (legacy)
    7. none                → unsupported

We do not silently fall through to alternative strategies after a
failure. The detected strategy is part of the result, and the host can
decide what to do with `unsupported`.
"""
from __future__ import annotations

import configparser
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    # Python 3.11+: tomllib is in stdlib. Python 3.12 runtime uses this.
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover — host dev fallback only
    tomllib = None  # type: ignore[assignment]

try:
    import yaml  # type: ignore[import-untyped]
    _YAML_OK = True
except ModuleNotFoundError:
    yaml = None  # type: ignore[assignment]
    _YAML_OK = False

# Lightweight YAML-ish heuristic used only when PyYAML isn't available.
# The runtime image does not bake PyYAML — most static facts (pytest,
# tox, GitHub Actions) are also expressible in JSON or TOML.

from .models import Detection  # noqa: E402


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Build strategy
# ---------------------------------------------------------------------------

BUILD_STRATEGY_NONE      = "none"
BUILD_STRATEGY_UV        = "uv"
BUILD_STRATEGY_POETRY    = "poetry"   # detected but explicitly unsupported (see below)
BUILD_STRATEGY_PIP       = "pip"
BUILD_STRATEGY_SETUPTOOLS = "setuptools"
BUILD_STRATEGY_PIPENV    = "pipenv"   # reported but unsupported by MVP

# Strategy is detected but explicitly unsupported by the runtime.
# The runtime image installs `uv` only. Poetry and pipenv are NOT
# installed to keep the image small and reproducible. Repos that
# require them get status=unsupported with a clear message.
UNSUPPORTED_STRATEGIES = frozenset({"poetry", "pipenv", "none"})


@dataclass(frozen=True)
class BuildStrategy:
    """The detected way to make this repository installable.

    `command` is the argv (list of strings) the runtime will run from
    /workspace/repo to install the project. `setup` is the optional
    pre-install environment bootstrap argv (e.g. `uv sync --frozen`).
    """
    strategy: str
    command:  list[str]
    setup:    list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Detection entry points
# ---------------------------------------------------------------------------

MAX_INSPECT_BYTES = 5 * 1024 * 1024   # 5 MiB — refuse to slurp bigger files
MAX_WALK_FILES    = 200_000           # hard ceiling on file enumeration


# Files / dirs we never descend into during static inspection.
_PRUNE_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".nox",
    "node_modules",
    "venv", ".venv", "env", ".env",
    "dist", "build", ".eggs",
    "site-packages",
    ".idea", ".vscode",
}


def detect(repo_root: Path) -> tuple[Detection, BuildStrategy]:
    """Walk `repo_root` once and produce both the Detection summary and the
    concrete BuildStrategy.

    `repo_root` must be the read-only host checkout (mounted at /input
    inside the container). The function never writes to it.
    """
    files = _walk_python_files(repo_root)

    has_uv_lock      = (repo_root / "uv.lock").is_file()
    has_poetry_lock  = (repo_root / "poetry.lock").is_file()
    has_pipfile      = (repo_root / "Pipfile").is_file()
    has_pyproject    = (repo_root / "pyproject.toml").is_file()
    has_setup_py     = (repo_root / "setup.py").is_file()
    has_setup_cfg    = (repo_root / "setup.cfg").is_file()
    has_requirements = any(
        p.is_file() and p.name.startswith("requirements")
        for p in repo_root.iterdir() if p.is_file()
    ) if repo_root.is_dir() else False

    pyproject = _safe_read_text(repo_root / "pyproject.toml") if has_pyproject else None
    setup_py  = _safe_read_text(repo_root / "setup.py")        if has_setup_py     else None
    setup_cfg = _safe_read_text(repo_root / "setup.cfg")        if has_setup_cfg    else None

    build_system, py_version_constraint = _detect_build_system(
        pyproject_text=pyproject,
        setup_py_text=setup_py,
        setup_cfg_text=setup_cfg,
    )

    layout = _detect_layout(repo_root, files)
    test_framework = _detect_test_framework(
        repo_root=repo_root,
        pyproject_text=pyproject,
        setup_cfg_text=setup_cfg,
        files=files,
    )

    package_manager: Optional[str] = None
    if has_uv_lock:
        package_manager = "uv"
    elif has_poetry_lock:
        package_manager = "poetry"
    elif has_pipfile:
        package_manager = "pipenv"
    elif has_pyproject:
        package_manager = "pip"
    elif has_requirements or has_setup_py or has_setup_cfg:
        package_manager = "pip"

    strategy = _build_strategy(
        repo_root=repo_root,
        has_uv_lock=has_uv_lock,
        has_poetry_lock=has_poetry_lock,
        has_pipfile=has_pipfile,
        has_pyproject=has_pyproject,
        has_requirements=has_requirements,
        has_setup_py=has_setup_py,
        has_setup_cfg=has_setup_cfg,
        pyproject_text=pyproject,
    )

    detection = Detection(
        package_manager=package_manager,
        build_system=build_system,
        test_framework=test_framework,
        layout=layout,
        has_pyproject=has_pyproject,
        has_setup_py=has_setup_py,
        has_setup_cfg=has_setup_cfg,
        has_requirements=has_requirements,
        has_uv_lock=has_uv_lock,
        has_poetry_lock=has_poetry_lock,
        has_pipfile=has_pipfile,
        python_version_constraint=py_version_constraint,
        files_inspected=len(files),
        python_files=sum(1 for p in files if p.suffix == ".py"),
    )
    return detection, strategy


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _walk_python_files(repo_root: Path) -> list[Path]:
    """Walk `repo_root`, returning all files in deterministic order.

    Prunes cache/venv/IDE/build directories. Caps the walk at
    `MAX_WALK_FILES`. Order is sorted by relative path to keep inspect
    output stable across runs and filesystems.
    """
    if not repo_root.is_dir():
        return []

    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root, followlinks=False):
        # In-place mutation of dirnames prunes the walk.
        dirnames[:] = sorted(d for d in dirnames if d not in _PRUNE_DIRS)
        for fn in sorted(filenames):
            out.append(Path(dirpath) / fn)
            if len(out) >= MAX_WALK_FILES:
                log.warning("walk truncated at %d files", MAX_WALK_FILES)
                return out
    return out


def _safe_read_text(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_INSPECT_BYTES:
            log.info("skip large file %s (%d bytes)", path, path.stat().st_size)
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.info("cannot read %s: %s", path, exc)
        return None


def _detect_build_system(
    *,
    pyproject_text: Optional[str],
    setup_py_text:   Optional[str],
    setup_cfg_text:  Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Return (build_system, raw_python_version_constraint).

    Detection order: pyproject.toml → setup.cfg → setup.py fallback.
    """
    constraint: Optional[str] = None

    if pyproject_text and tomllib is not None:
        try:
            data = tomllib.loads(pyproject_text)
            build_system, constraint = _build_system_from_pyproject(data)
            if build_system is not None:
                return build_system, constraint
        except tomllib.TOMLDecodeError as exc:
            log.info("pyproject.toml parse failed: %s", exc)

    if setup_cfg_text:
        try:
            cp = configparser.ConfigParser()
            cp.read_string(setup_cfg_text)
            if cp.has_section("options"):
                if cp.has_option("options", "python_requires"):
                    constraint = cp.get("options", "python_requires").strip()
            if cp.has_section("build_system") and cp.has_option(
                "build_system", "build-backend"
            ):
                backend = cp.get("build_system", "build-backend").strip()
                return _backend_to_build_system(backend), constraint
            # Legacy setuptools without build-system declared.
            if cp.has_section("metadata") or cp.has_section("options"):
                return "setuptools", constraint
        except (configparser.Error, ValueError) as exc:
            log.info("setup.cfg parse failed: %s", exc)

    if setup_py_text:
        m = re.search(r"python_requires\s*=\s*['\"]([^'\"]+)['\"]", setup_py_text)
        if m:
            constraint = m.group(1).strip()
        return "setuptools", constraint

    return None, None


def _build_system_from_pyproject(data: dict) -> tuple[Optional[str], Optional[str]]:
    constraint: Optional[str] = None
    project = data.get("project") or {}
    if isinstance(project, dict):
        v = project.get("requires-python")
        if isinstance(v, str):
            constraint = v.strip()
    backend = (
        (data.get("build-system") or {}).get("build-backend")
        if isinstance(data.get("build-system"), dict) else None
    )
    if backend:
        return _backend_to_build_system(backend), constraint
    # Poetry is detectable from the [tool.poetry] table.
    if isinstance(data.get("tool"), dict) and "poetry" in data["tool"]:
        return "poetry-core", constraint
    # pyproject.toml with [project] but no build-system declared — defaults to setuptools
    # but only if a setup.py is present; otherwise unknown.
    if "project" in data:
        return "setuptools", constraint  # PEP 621 metadata only; assume setuptools
    return None, constraint


_BACKEND_TO_BUILD_SYSTEM = {
    "setuptools.build_meta":         "setuptools",
    "setuptools.build_meta:__legacy__":"setuptools",
    "hatchling.build":                "hatchling",
    "hatch":                          "hatchling",
    "poetry.core.masonry.api":        "poetry-core",
    "flit_core.buildapi":             "flit",
    "pdm.backend":                    "pdm",
    "scikit_build_core.build":        "scikit-build-core",
    "maturin":                        "maturin",
    "mesonpy":                        "mesonpy",
}


def _backend_to_build_system(backend: str) -> str:
    # Normalise for lookup.
    key = backend.strip().lower()
    if key in _BACKEND_TO_BUILD_SYSTEM:
        return _BACKEND_TO_BUILD_SYSTEM[key]
    # Fall back to the first dotted component (e.g. "mypackage.build" -> "mypackage")
    return key.split(".", 1)[0] or key


def _detect_layout(repo_root: Path, files: list[Path]) -> Optional[str]:
    """Detect src-layout vs flat-layout.

    src-layout: a `src/<pkgname>/__init__.py` directory beneath the root.
    flat-layout: `<pkgname>/__init__.py` directly under repo_root
                 (any depth ≥ 2, as long as parts[0] != "src").

    Examples:
        src/foo/__init__.py              → "src"
        src/foo/bar/__init__.py          → "src"
        pkg/__init__.py                  → "flat"
        pkg/sub/__init__.py              → "flat"
        __init__.py  (at root)           → ignored (single-file weirdness)
    """
    for p in files:
        if p.name == "__init__.py":
            try:
                rel = p.relative_to(repo_root)
            except ValueError:
                continue
            parts = rel.parts
            if len(parts) >= 2 and parts[0] == "src":
                return "src"
            if len(parts) == 2 and parts[1] == "__init__.py":
                return "flat"
            if len(parts) >= 3 and parts[0] != "src":
                # Nested package under flat-layout top-level package.
                return "flat"
    return None


def _detect_test_framework(
    *,
    repo_root: Path,
    pyproject_text: Optional[str],
    setup_cfg_text: Optional[str],
    files: list[Path],
) -> Optional[str]:
    # pyproject: [tool.pytest.ini_options] → pytest
    if pyproject_text:
        if "[tool.pytest.ini_options]" in pyproject_text:
            return "pytest"
        if "[tool.unittest]" in pyproject_text:
            return "unittest"
    # setup.cfg [tool:pytest] → pytest
    if setup_cfg_text and "[tool:pytest]" in setup_cfg_text:
        return "pytest"
    # tests/ directory with test_*.py / *_test.py → pytest by convention
    for p in files:
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            return "pytest"
    # pytest.ini / conftest.py
    if (repo_root / "pytest.ini").is_file() or (repo_root / "conftest.py").is_file():
        return "pytest"
    # tox.ini has pytest envs
    tox = repo_root / "tox.ini"
    if tox.is_file():
        txt = _safe_read_text(tox) or ""
        if "[pytest]" in txt or "[testenv]" in txt:
            return "pytest"
    return None


# ---------------------------------------------------------------------------
# Build strategy derivation
# ---------------------------------------------------------------------------

def _build_strategy(
    *,
    repo_root: Path,
    has_uv_lock: bool,
    has_poetry_lock: bool,
    has_pipfile: bool,
    has_pyproject: bool,
    has_requirements: bool,
    has_setup_py: bool,
    has_setup_cfg: bool,
    pyproject_text: Optional[str],
) -> BuildStrategy:
    """Pick one explicit strategy. Never fall through on failure.

    The runtime image installs `uv` only. Poetry and pipenv are NOT
    installed to keep the image small and reproducible. When the
    detected strategy requires Poetry or pipenv we return the
    `strategy=...` token with an empty `command` so the host sees
    `status=unsupported` with a clear message rather than a missing
    binary at exec time.
    """
    if has_uv_lock:
        # `uv sync --frozen` is non-mutating against the lockfile.
        return BuildStrategy(
            strategy="uv",
            command=["uv", "pip", "install", "--python", sys.executable, "-e", "."],
            setup=["uv", "sync", "--frozen"],
        )
    if has_poetry_lock:
        # Poetry is not installed in the image. Mark unsupported.
        return BuildStrategy(strategy="poetry", command=[])
    if has_pipfile:
        # MVP does not implement pipenv. Surface it explicitly.
        return BuildStrategy(strategy="pipenv", command=[])
    if has_pyproject:
        if _pyproject_uses_poetry(pyproject_text):
            # Poetry-style pyproject without a lockfile → also unsupported.
            return BuildStrategy(strategy="poetry", command=[])
        # Plain PEP 621 pyproject.toml — install with pip in editable mode.
        return BuildStrategy(
            strategy="pip",
            command=[sys.executable, "-m", "pip", "install", "-e", "."],
        )
    if has_requirements:
        req_files = sorted(
            str(p.relative_to(repo_root))
            for p in repo_root.iterdir()
            if p.is_file() and p.name.startswith("requirements")
        )
        target = req_files[0] if req_files else "requirements.txt"
        return BuildStrategy(
            strategy="pip",
            command=[sys.executable, "-m", "pip", "install", "-r", target],
        )
    if has_setup_py or has_setup_cfg:
        return BuildStrategy(
            strategy="setuptools",
            command=[sys.executable, "-m", "pip", "install", "-e", "."],
        )
    return BuildStrategy(strategy="none", command=[])


def _pyproject_uses_poetry(pyproject_text: Optional[str]) -> bool:
    if not pyproject_text or tomllib is None:
        return False
    try:
        data = tomllib.loads(pyproject_text)
    except tomllib.TOMLDecodeError:
        return False
    return isinstance(data.get("tool"), dict) and "poetry" in data["tool"]
