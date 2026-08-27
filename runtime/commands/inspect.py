"""Static inspection of a checked-out Python repository.

SECURITY: this function MUST NOT execute repository code. Specifically:

    * No `import` of repo Python modules (no `importlib`, no `runpy`).
    * No `python setup.py` execution.
    * No `pip install` of repo dependencies.
    * No arbitrary subprocess of repo-supplied files.
    * No parsing by executing the file (TOML/YAML/JSON are parsed with
      stdlib parsers; Python files are AST-parsed only).

The contract is: produce a deterministic, sorted JSON inventory of
the repository's Python packaging facts.
"""
from __future__ import annotations

import ast
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from ..detect import detect
from ..models import (
    Artifact, Detection, Environment, NetworkPolicy, RepoInfo, Result, Status,
)
from ._common import (
    WORKSPACE_REPO, log_artifacts, python_version_string, write_result_atomic,
)


log = logging.getLogger(__name__)


# Patterns that, if present in a file's *contents*, hint at what the file
# does. We collect them for compliance later; this is just inventory.
_SUSPICIOUS_PYTHON_NAMES = {
    "setup.py",     # legacy build; never executed by inspect
    "conftest.py",  # pytest plugin loader; never executed by inspect
    "pytest.ini",
}


@dataclass(frozen=True)
class PythonFileFacts:
    path: str                       # relative to /input
    size_bytes: int
    parse_ok: bool
    syntax_error: Optional[str] = None
    top_level_defs: list[str] = field(default_factory=list)   # function/class names
    imports: list[str] = field(default_factory=list)          # raw module names (deduped, sorted)


def run(
    *,
    repo_path: Path,
    artifacts_dir: Path,
    timeout_seconds: int,
    repo_sha: str = "",
    output_path: Optional[Path] = None,
    network_policy: NetworkPolicy = NetworkPolicy.NONE,
) -> Result:
    """Run static inspection. See module docstring for security model."""
    started = time.monotonic()
    detection, _ = detect(repo_path)

    python_files: list[PythonFileFacts] = []
    text_files:   list[str] = []
    config_files: list[str] = []

    # Walk only paths the detector already enumerated (deterministic + bounded).
    for p in _iter_inspect_paths(repo_path):
        rel = str(p.relative_to(repo_path))
        if p.suffix == ".py":
            python_files.append(_inspect_python_file(p, rel))
        elif p.suffix in (".toml", ".cfg", ".ini", ".yaml", ".yml", ".json"):
            config_files.append(rel)
        elif p.is_file():
            # Plain text-ish files; we record the relative path only.
            try:
                if _looks_text(p):
                    text_files.append(rel)
            except OSError:
                continue

    python_files.sort(key=lambda f: f.path)

    artifacts: list[Artifact] = []
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Persist the python-file inventory as a separate artifact so downstream
    # compliance tooling doesn't have to re-walk the repo.
    py_index_path = artifacts_dir / "python_files.json"
    py_index_path.write_text(json.dumps(
        [asdict(f) for f in python_files],
        indent=2, sort_keys=False,
    ), encoding="utf-8")
    # `log_artifacts(artifacts_dir)` is called once at the end of `run`
    # and is the canonical inventory — don't duplicate entries here.

    env = Environment(
        python_version=python_version_string(),
        network_policy=network_policy,
    )

    extra = {
        "text_files":      sorted(text_files),
        "config_files":    sorted(config_files),
        "suspicious_files": sorted(rel for rel, _ in (
            (str(p.relative_to(repo_path)), p.name)
            for p in _iter_inspect_paths(repo_path)
        ) if _ in _SUSPICIOUS_PYTHON_NAMES),
    }

    result = Result(
        schema_version="1",
        runtime_version="0.1.0",
        mode="inspect",
        status=Status.SUCCESS,
        repo=RepoInfo(sha=repo_sha, path=str(repo_path)),
        environment=env,
        detection=detection,
        commands=[],                # inspect never runs subprocesses
        artifacts=artifacts,
        duration_ms=int((time.monotonic() - started) * 1000),
        exit_code=0,
        error=None,
        extra=extra,
    )

    artifacts.extend(log_artifacts(artifacts_dir))
    if output_path is not None:
        write_result_atomic(result, output_path)
    return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

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
_MAX_FILE_BYTES = 5 * 1024 * 1024   # 5 MiB per file for AST/heuristic parsing


def _iter_inspect_paths(repo_root: Path):
    import os
    for dirpath, dirnames, filenames in os.walk(repo_root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in _PRUNE_DIRS)
        for fn in sorted(filenames):
            yield Path(dirpath) / fn


def _inspect_python_file(path: Path, rel: str) -> PythonFileFacts:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return PythonFileFacts(path=rel, size_bytes=0, parse_ok=False,
                               syntax_error=f"stat failed: {exc}")
    if size > _MAX_FILE_BYTES:
        return PythonFileFacts(
            path=rel, size_bytes=size, parse_ok=False,
            syntax_error=f"skipped: file > {_MAX_FILE_BYTES} bytes",
        )
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return PythonFileFacts(path=rel, size_bytes=size, parse_ok=False,
                               syntax_error=f"read failed: {exc}")

    try:
        tree = ast.parse(src, filename=rel, mode="exec")
    except SyntaxError as exc:
        return PythonFileFacts(
            path=rel, size_bytes=size, parse_ok=False,
            syntax_error=f"{exc.msg} at line {exc.lineno}",
        )

    defs: list[str] = []
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".", 1)[0])
    return PythonFileFacts(
        path=rel, size_bytes=size, parse_ok=True,
        top_level_defs=sorted(defs),
        imports=sorted(imports),
    )


_TEXT_HEURISTIC_BYTES = 4096
def _looks_text(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            chunk = fh.read(_TEXT_HEURISTIC_BYTES)
    except OSError:
        return False
    if not chunk:
        return True
    if b"\x00" in chunk:
        return False
    return True
