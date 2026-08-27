"""Schema validation tests — the JSON contract compliance tooling will rely on."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.models import (
    SCHEMA_VERSION, Artifact, CommandRecord, Detection, Environment,
    NetworkPolicy, RepoInfo, Result, Status, validate_dict,
)


def _example_result():
    return Result(
        schema_version=SCHEMA_VERSION,
        runtime_version="0.1.0",
        mode="inspect",
        status=Status.SUCCESS,
        repo=RepoInfo(sha="abc123", path="/input"),
        environment=Environment(
            python_version="3.12.4",
            network_policy=NetworkPolicy.NONE,
        ),
        detection=Detection(
            package_manager="uv",
            build_system="hatchling",
            test_framework="pytest",
            layout="src",
            has_pyproject=True,
            has_setup_py=False,
            has_setup_cfg=False,
            has_requirements=False,
            has_uv_lock=True,
            has_poetry_lock=False,
            has_pipfile=False,
            python_version_constraint=">=3.10",
            files_inspected=42,
            python_files=17,
        ),
        commands=[
            CommandRecord(
                argv=["python", "-m", "pytest"],
                cwd="/workspace/repo",
                exit_code=0,
                duration_ms=1234,
                timed_out=False,
                stdout_artifact="00_pytest.stdout.log",
                stderr_artifact="00_pytest.stderr.log",
            ),
        ],
        artifacts=[
            Artifact(path="python_files.json", description="py index", bytes=1234),
        ],
        duration_ms=5678,
        exit_code=0,
        error=None,
    )


def test_result_round_trips_through_json():
    r = _example_result()
    doc = r.to_dict()
    blob = r.to_json(indent=2)
    parsed = json.loads(blob)
    assert parsed == doc


def test_result_dict_passes_schema_validation():
    r = _example_result()
    validate_dict(r.to_dict())


def test_validate_dict_rejects_missing_keys():
    doc = _example_result().to_dict()
    doc.pop("repo")
    with pytest.raises(Exception) as exc:
        validate_dict(doc)
    assert "repo" in str(exc.value)


def test_validate_dict_rejects_invalid_status():
    doc = _example_result().to_dict()
    doc["status"] = "PASS"   # not a runtime status
    with pytest.raises(Exception) as exc:
        validate_dict(doc)
    assert "status" in str(exc.value)


def test_validate_dict_rejects_schema_version_mismatch():
    doc = _example_result().to_dict()
    doc["schema_version"] = "99"
    with pytest.raises(Exception) as exc:
        validate_dict(doc)
    assert "schema_version" in str(exc.value)


def test_validate_dict_rejects_command_missing_argv():
    doc = _example_result().to_dict()
    doc["commands"][0].pop("argv")
    with pytest.raises(Exception) as exc:
        validate_dict(doc)
    assert "argv" in str(exc.value)


def test_validate_dict_rejects_unknown_keys():
    doc = _example_result().to_dict()
    doc["smuggled"] = "should fail"
    with pytest.raises(Exception) as exc:
        validate_dict(doc)
    assert "smuggled" in str(exc.value)


def test_status_enum_values_are_locked():
    # Locked set. Adding a new value requires bumping SCHEMA_VERSION.
    assert {s.value for s in Status} == {
        "success", "failed", "unsupported", "timeout", "error",
    }


def test_network_policy_enum_values_are_locked():
    assert {n.value for n in NetworkPolicy} == {"none", "enabled"}


def test_status_serializes_as_string_not_object():
    r = _example_result()
    doc = r.to_dict()
    assert doc["status"] == "success"
    assert isinstance(doc["status"], str)


def test_detection_python_files_equals_python_files_in_inventory(fixtures_map, temp_dir):
    """The detection.python_files count must equal the AST inventory size."""
    from runtime.commands import inspect as inspect_cmd
    repo_root = fixtures_map["07-pytest"]
    result = inspect_cmd.run(
        repo_path=repo_root,
        artifacts_dir=temp_dir / "art",
        timeout_seconds=30,
        repo_sha="",
    )
    inventory = json.loads((temp_dir / "art" / "python_files.json").read_text())
    assert result.detection.python_files == len(inventory)
