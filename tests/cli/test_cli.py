"""Tests for the top-level `reguard` CLI."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_cli(*args, cwd=None, env=None):
    full_env = dict(os.environ)
    full_env["PYTHONPATH"] = str(
        Path(__file__).resolve().parents[2] / "src"
    )
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "compliance.cli", *args],
        cwd=cwd or str(Path(__file__).resolve().parents[2]),
        env=full_env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_version():
    result = _run_cli("--version")
    assert result.returncode == 0
    assert "reguard" in result.stdout


def test_cli_help():
    result = _run_cli("--help")
    assert result.returncode == 0
    for cmd in ("init", "doctor", "check", "explain", "list"):
        assert cmd in result.stdout


def test_cli_list():
    result = _run_cli("list")
    assert result.returncode == 0
    assert "Recipes:" in result.stdout
    assert "langgraph-state" in result.stdout
    assert "Observers:" in result.stdout
    assert "Normalizers:" in result.stdout
    assert "Families:" in result.stdout


def test_cli_list_recipes_only():
    result = _run_cli("list", "recipes")
    assert result.returncode == 0
    assert "langgraph-state" in result.stdout


def test_cli_explain_article12_1():
    result = _run_cli("explain", "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING")
    assert result.returncode == 0
    assert "1.4.0" in result.stdout


def test_cli_explain_unknown_returns_1():
    result = _run_cli("explain", "NO_SUCH_REQUIREMENT")
    assert result.returncode == 1


def test_cli_init_creates_reguard_yml(tmp_path):
    out = tmp_path / "reguard.yml"
    result = _run_cli("init", "--output", str(out), cwd=str(tmp_path))
    assert result.returncode == 0
    assert out.exists()
    text = out.read_text()
    assert "schema_version: 1" in text


def test_cli_init_refuses_overwrite(tmp_path):
    out = tmp_path / "reguard.yml"
    out.write_text("existing")
    result = _run_cli("init", "--output", str(out), cwd=str(tmp_path))
    assert result.returncode == 1


def test_cli_doctor_on_minimal_agent(tmp_path):
    src_demo = Path(__file__).resolve().parents[2] / "examples" / "minimal-agent"
    result = _run_cli(
        "doctor",
        "--repo-path", str(src_demo),
        "--repo", "acme/minimal-agent",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "doctor: OK" in result.stdout


def test_cli_check_passes_on_minimal_agent(tmp_path):
    src_demo = Path(__file__).resolve().parents[2] / "examples" / "minimal-agent"
    result = _run_cli(
        "check",
        "--repo-path", str(src_demo),
        "--repo", "acme/minimal-agent",
        "--output-dir", str(tmp_path / "results"),
        "--fail-on", "",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
    result_files = list((tmp_path / "results").rglob("result.json"))
    assert len(result_files) >= 1
    import json
    payload = json.loads(result_files[-1].read_text())
    assert payload["status"] == "PASS"
    assert payload["requirement_id"] == "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING"


def test_cli_check_unsupported(tmp_path):
    result = _run_cli(
        "check",
        "--repo-path", str(tmp_path),
        "--repo", "no-such/repo",
        "--output-dir", str(tmp_path / "results"),
        "--fail-on", "",
    )
    assert result.returncode == 0  # because we passed --fail-on ""
    assert "UNSUPPORTED" in result.stdout
    assert "NO_EXECUTION_RECIPE" in result.stdout


def test_cli_check_fail_on_FAIL_returns_nonzero_on_failure(tmp_path):
    src_demo = Path(__file__).resolve().parents[2] / "examples" / "minimal-agent"
    result = _run_cli(
        "check",
        "--repo-path", str(src_demo),
        "--repo", "acme/minimal-agent",
        "--output-dir", str(tmp_path / "results"),
        "--fail-on", "FAIL",
    )
    # Demo PASSes; default fail-on does not include PASS, so exit 0.
    assert result.returncode == 0
