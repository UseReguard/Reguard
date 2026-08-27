"""Subprocess timeout tests for runtime.commands._common.run_subprocess."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from runtime.commands._common import run_subprocess


def test_subprocess_with_short_timeout_marks_timed_out(temp_dir):
    """A command that sleeps longer than the timeout should be terminated."""
    out = run_subprocess(
        argv=[sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=temp_dir,
        artifacts_dir=temp_dir,
        label="slow",
        timeout_seconds=2,
    )
    assert out.timed_out is True
    # Should return relatively quickly — well under the 30s sleep.
    assert out.duration_ms < 15_000
    assert out.exit_code != 0  # killed


def test_subprocess_finishes_normally(temp_dir):
    out = run_subprocess(
        argv=[sys.executable, "-c", "print('ok')"],
        cwd=temp_dir,
        artifacts_dir=temp_dir,
        label="quick",
        timeout_seconds=10,
    )
    assert out.timed_out is False
    assert out.exit_code == 0


def test_subprocess_missing_executable(temp_dir):
    out = run_subprocess(
        argv=["definitely-not-a-real-binary-xyz"],
        cwd=temp_dir,
        artifacts_dir=temp_dir,
        label="missing",
        timeout_seconds=5,
    )
    assert out.timed_out is False
    assert out.exit_code == 127


def test_subprocess_uses_argv_not_shell(temp_dir):
    """A shell metacharacter in argv should be passed literally, not interpreted."""
    out = run_subprocess(
        argv=[sys.executable, "-c", "import sys; print(repr(sys.argv[1:]))",
              "; rm -rf / ; #"],
        cwd=temp_dir,
        artifacts_dir=temp_dir,
        label="argv_only",
        timeout_seconds=5,
    )
    assert out.timed_out is False
    assert out.exit_code == 0
    # The metacharacters should appear as a single literal argv.
    stdout = (temp_dir / "argv_only.stdout.log").read_text()
    assert "'; rm -rf / ; #'" in stdout or "['; rm -rf / ; #']" in stdout


def test_subprocess_writes_stdout_and_stderr_artifacts(temp_dir):
    out = run_subprocess(
        argv=[sys.executable, "-c",
              "import sys; print('hi'); print('bye', file=sys.stderr)"],
        cwd=temp_dir,
        artifacts_dir=temp_dir,
        label="two_streams",
        timeout_seconds=5,
    )
    assert out.exit_code == 0
    assert (temp_dir / "two_streams.stdout.log").exists()
    assert (temp_dir / "two_streams.stderr.log").exists()
    assert "hi" in (temp_dir / "two_streams.stdout.log").read_text()
    assert "bye" in (temp_dir / "two_streams.stderr.log").read_text()
