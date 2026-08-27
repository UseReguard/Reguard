"""Stable JSON result schema for repo-runtime.

Every mode produces a `Result` instance that serializes to a
machine-readable JSON document. The schema is a contract that future
compliance tooling will depend on, so changes must be deliberate and
versioned.

Status values (locked, do not extend without bumping SCHEMA_VERSION):

    success     — operation completed as intended
    failed      — operation ran but exited non-zero / returned bad data
    unsupported — operation could not determine a safe strategy
    timeout     — operation exceeded the timeout
    error       — operation could not even be attempted

Do NOT use PASS / FAIL here. Those terms belong to compliance rules.
"""
from __future__ import annotations

import dataclasses
import enum
import json
from dataclasses import dataclass, field
from typing import Any, Optional


SCHEMA_VERSION: str = "1"
RUNTIME_VERSION: str = "0.1.0"


class Status(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    ERROR = "error"


class NetworkPolicy(str, enum.Enum):
    NONE = "none"
    ENABLED = "enabled"


@dataclass(frozen=True)
class RepoInfo:
    """The host-provided identity of the checked-out repository."""
    sha: str
    path: str  # absolute path inside the container, e.g. "/input"


@dataclass(frozen=True)
class Environment:
    python_version: str
    network_policy: NetworkPolicy


@dataclass(frozen=True)
class Detection:
    """Statically detected facts. Values may be None when undetectable."""
    package_manager: Optional[str] = None   # uv / poetry / pip / None
    build_system: Optional[str] = None     # hatchling / poetry-core / setuptools / None
    test_framework: Optional[str] = None   # pytest / unittest / None
    layout: Optional[str] = None           # src / flat / None
    has_pyproject: bool = False
    has_setup_py: bool = False
    has_setup_cfg: bool = False
    has_requirements: bool = False
    has_uv_lock: bool = False
    has_poetry_lock: bool = False
    has_pipfile: bool = False
    python_version_constraint: Optional[str] = None  # raw string from pyproject.toml / setup.cfg
    files_inspected: int = 0
    python_files: int = 0


@dataclass(frozen=True)
class CommandRecord:
    """One subprocess invocation. argv is preferred over shell strings."""
    argv: list[str]
    cwd: str
    exit_code: int
    duration_ms: int
    timed_out: bool
    label: str = ""                       # e.g. "01_install", "02_pytest"
    stdout_artifact: Optional[str] = None  # path under /artifacts
    stderr_artifact: Optional[str] = None


@dataclass(frozen=True)
class Artifact:
    path: str             # path under /artifacts (relative)
    description: str
    bytes: Optional[int] = None


@dataclass
class Result:
    """The single contract that leaves the runtime container."""
    schema_version: str
    runtime_version: str
    mode: str                       # "inspect" / "build" / "test"
    status: Status
    repo: RepoInfo
    environment: Environment
    detection: Detection
    commands: list[CommandRecord] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    duration_ms: int = 0
    exit_code: int = 0
    error: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    # ---- (de)serialisation -------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["status"] = self.status.value
        d["environment"]["network_policy"] = self.environment.network_policy.value
        return d

    def to_json(self, *, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False,
                          ensure_ascii=False)

    def write(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_json(indent=2))
            fh.write("\n")


# ---------------------------------------------------------------------------
# Schema validation (used by tests, optional at runtime)
# ---------------------------------------------------------------------------

_REQUIRED_RESULT_KEYS = {
    "schema_version", "runtime_version", "mode", "status", "repo",
    "environment", "detection", "commands", "artifacts",
    "duration_ms", "exit_code", "error", "extra",
}

_REQUIRED_REPO_KEYS = {"sha", "path"}
_REQUIRED_ENV_KEYS = {"python_version", "network_policy"}
_REQUIRED_DETECTION_KEYS = {
    "package_manager", "build_system", "test_framework", "layout",
    "has_pyproject", "has_setup_py", "has_setup_cfg", "has_requirements",
    "has_uv_lock", "has_poetry_lock", "has_pipfile",
    "python_version_constraint", "files_inspected", "python_files",
}
_REQUIRED_COMMAND_KEYS = {
    "argv", "cwd", "exit_code", "duration_ms", "timed_out",
    "label", "stdout_artifact", "stderr_artifact",
}


class SchemaError(ValueError):
    """Raised when a dict does not match the Result schema."""


def validate_dict(doc: dict[str, Any]) -> None:
    """Lightweight structural validation — no external schema lib needed."""
    extra = set(doc) - _REQUIRED_RESULT_KEYS
    missing = _REQUIRED_RESULT_KEYS - set(doc)
    if missing:
        raise SchemaError(f"missing keys: {sorted(missing)}")
    if extra:
        raise SchemaError(f"unknown keys: {sorted(extra)}")
    if doc["status"] not in {s.value for s in Status}:
        raise SchemaError(f"invalid status: {doc['status']!r}")
    if doc["schema_version"] != SCHEMA_VERSION:
        raise SchemaError(
            f"schema_version mismatch: got {doc['schema_version']!r}, "
            f"expected {SCHEMA_VERSION!r}"
        )
    repo = doc["repo"]
    miss_repo = _REQUIRED_REPO_KEYS - set(repo)
    if miss_repo:
        raise SchemaError(f"repo missing keys: {sorted(miss_repo)}")
    env = doc["environment"]
    miss_env = _REQUIRED_ENV_KEYS - set(env)
    if miss_env:
        raise SchemaError(f"environment missing keys: {sorted(miss_env)}")
    det = doc["detection"]
    miss_det = _REQUIRED_DETECTION_KEYS - set(det)
    if miss_det:
        raise SchemaError(f"detection missing keys: {sorted(miss_det)}")
    for i, cmd in enumerate(doc["commands"]):
        miss_cmd = _REQUIRED_COMMAND_KEYS - set(cmd)
        if miss_cmd:
            raise SchemaError(f"commands[{i}] missing keys: {sorted(miss_cmd)}")
