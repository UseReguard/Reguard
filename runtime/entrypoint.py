#!/usr/bin/env python3
"""CLI dispatcher for the repo-runtime container.

Usage:

    repo-runtime inspect --repo-sha <sha> --output /artifacts/result.json
    repo-runtime build   --repo-sha <sha> --output /artifacts/result.json
    repo-runtime test    --repo-sha <sha> --output /artifacts/result.json \\
                         [--command "pytest tests/unit"]

The runtime expects:
    /input      — read-only bind mount of the host checkout
    /artifacts  — writable bind mount for result.json + per-command logs

The runtime does NOT know about GitHub URLs, the corpus database, or
any compliance rules. It only inspects / builds / tests the tree
under /input.

The runtime writes `result.json` even on failure (best-effort).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Allow `python runtime/entrypoint.py ...` from a host checkout as well.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent))

from runtime.commands import build as build_cmd
from runtime.commands import inspect as inspect_cmd
from runtime.commands import test as test_cmd
from runtime.models import NetworkPolicy, Status   # noqa: E402


log = logging.getLogger("repo-runtime")


REPO_PATH_DEFAULT    = Path("/input")
ARTIFACTS_DIR_DEFAULT = Path("/artifacts")
RESULT_FILENAME       = "result.json"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-runtime",
        description="Inspect / build / test a Python repository checkout.",
    )
    parser.add_argument("--log-level", default="INFO",
                        choices=("DEBUG", "INFO", "WARNING", "ERROR"))

    sub = parser.add_subparsers(dest="mode", required=True)

    # Common args shared by every subcommand. `--network` lives here so
    # argparse sees it as a subcommand flag (top-level parser flags
    # conflict with subparsers).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo-path", type=Path, default=REPO_PATH_DEFAULT,
                        help="Path to the repo checkout (default: /input)")
    common.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR_DEFAULT,
                        help="Writable directory for outputs (default: /artifacts)")
    common.add_argument("--repo-sha", default="",
                        help="Host-supplied SHA identifying the checkout")
    common.add_argument("--timeout-seconds", type=int, default=600,
                        help="Hard timeout per mode (default: 600)")
    common.add_argument("--network", choices=("none", "enabled"),
                        default="none",
                        help="Network policy. Build defaults to 'enabled'; "
                             "inspect/test default to 'none'.")
    common.add_argument("--output", type=Path, default=None,
                        help=f"Where to write {RESULT_FILENAME} "
                             f"(default: <artifacts-dir>/{RESULT_FILENAME})")

    sub.add_parser("inspect", parents=[common],
                   help="Static inventory of /input — never executes repo code.")
    sub.add_parser("build", parents=[common],
                   help="Install dependencies and prepare a usable environment.")
    test_p = sub.add_parser("test", parents=[common],
                            help="Run the test suite.")
    test_p.add_argument("--command", default=None,
                        help="Explicit test command (whitespace-split). "
                             "Treated as trusted orchestration configuration.")
    test_p.add_argument("--auto-setup", dest="auto_setup",
                        action=argparse.BooleanOptionalAction, default=True,
                        help="Run minimal deterministic environment setup "
                             "(detect+install) before the test command. "
                             "Default: enabled. Disable with --no-auto-setup "
                             "if the host already prepared the environment.")

    return parser


def _split_command(s: Optional[str]) -> Optional[list[str]]:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    # Simple whitespace split — the runtime avoids shlex so that
    # host-supplied commands don't accidentally inherit shell parsing
    # semantics. If the user really needs a shell metacharacter they
    # can use argv via a future --command-json option.
    return s.split()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _default_output(args: argparse.Namespace) -> Path:
    if getattr(args, "output", None):
        return Path(args.output)
    return Path(args.artifacts_dir) / RESULT_FILENAME


def _network_policy_for(mode: str, override: str) -> NetworkPolicy:
    if override == "enabled":
        return NetworkPolicy.ENABLED
    # mode-specific default
    if mode == "build":
        return NetworkPolicy.ENABLED
    return NetworkPolicy.NONE


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    output_path = _default_output(args)
    net = _network_policy_for(args.mode, args.network)

    repo_path = Path(args.repo_path)
    artifacts_dir = Path(args.artifacts_dir)
    started = time.monotonic()

    log.info("mode=%s repo=%s sha=%s timeout=%ds network=%s",
             args.mode, repo_path, args.repo_sha, args.timeout_seconds,
             net.value)

    try:
        if args.mode == "inspect":
            result = inspect_cmd.run(
                repo_path=repo_path,
                artifacts_dir=artifacts_dir,
                timeout_seconds=args.timeout_seconds,
                repo_sha=args.repo_sha,
                output_path=output_path,
                network_policy=net,
            )
        elif args.mode == "build":
            result = build_cmd.run(
                repo_path=repo_path,
                artifacts_dir=artifacts_dir,
                timeout_seconds=args.timeout_seconds,
                repo_sha=args.repo_sha,
                output_path=output_path,
                network_policy=net,
            )
        elif args.mode == "test":
            result = test_cmd.run(
                repo_path=repo_path,
                artifacts_dir=artifacts_dir,
                timeout_seconds=args.timeout_seconds,
                repo_sha=args.repo_sha,
                output_path=output_path,
                network_policy=net,
                command=_split_command(getattr(args, "command", None)),
                auto_setup=getattr(args, "auto_setup", True),
            )
        else:  # pragma: no cover — argparse `required=True` prevents this
            raise SystemExit(f"unknown mode: {args.mode}")
    except Exception as exc:  # noqa: BLE001 — write a structured error result
        log.exception("unhandled error in mode %s", args.mode)
        # Best-effort error result so the host always gets a parseable file.
        try:
            from runtime.models import (
                Detection, Environment, RepoInfo, Result,
            )
            err_result = Result(
                schema_version="1",
                runtime_version="0.1.0",
                mode=args.mode,
                status=Status.ERROR,
                repo=RepoInfo(sha=args.repo_sha, path=str(repo_path)),
                environment=Environment(
                    python_version="",
                    network_policy=net,
                ),
                detection=Detection(),
                commands=[],
                artifacts=[],
                duration_ms=int((time.monotonic() - started) * 1000),
                exit_code=1,
                error=f"{type(exc).__name__}: {exc}",
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            err_result.write(str(output_path))
        except Exception:  # pragma: no cover
            log.exception("failed to write error result")
        return 2

    log.info("status=%s duration_ms=%d exit_code=%d",
             result.status.value, result.duration_ms, result.exit_code)

    # The container's exit code is the `runtime` exit, not the compliance
    # verdict. Use the structured result for verdict logic.
    if result.status in (Status.SUCCESS, Status.UNSUPPORTED):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
