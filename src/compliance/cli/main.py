"""Top-level CLI entry point.

Argparse-based subcommands. Subcommand implementations live in
`commands_*.py` modules next to this one.
"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .commands_init import cmd_init
from .commands_doctor import cmd_doctor
from .commands_check import cmd_check
from .commands_explain import cmd_explain
from .commands_list import cmd_list


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reguard",
        description=(
            "Reguard Core v0.1 — deterministic technical-control "
            "checks for AI agents."
        ),
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print Reguard version and exit",
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="create a reguard.yml template")
    p_init.add_argument(
        "--output", default="reguard.yml",
        help="output path (default: reguard.yml)",
    )

    p_doctor = sub.add_parser(
        "doctor",
        help="check host environment, config validity, and integration resolution",
    )
    p_doctor.add_argument(
        "--repo", default=None,
        help="owner/name (e.g. SWE-agent/mini-swe-agent)",
    )
    p_doctor.add_argument(
        "--config", default=None,
        help="explicit reguard.yml path",
    )
    p_doctor.add_argument(
        "--repo-path", default=None,
        help="repository-local working directory",
    )

    p_check = sub.add_parser(
        "check", help="run a deterministic compliance check",
    )
    p_check.add_argument(
        "--repo", default=None,
        help="owner/name (defaults to local repository inference)",
    )
    p_check.add_argument(
        "--config", default=None,
        help="explicit reguard.yml path (overrides repo-local)",
    )
    p_check.add_argument(
        "--repo-path", default=".",
        help="path to the repository working directory",
    )
    p_check.add_argument(
        "--requirement",
        default="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        help="requirement_id to test (default: Article 12(1))",
    )
    p_check.add_argument(
        "--output-dir", default=".reguard/results",
        help="directory for result artefacts",
    )
    p_check.add_argument(
        "--fail-on",
        default="FAIL,ERROR",
        help="comma-separated statuses that cause non-zero exit",
    )

    p_explain = sub.add_parser(
        "explain", help="explain a requirement test",
    )
    p_explain.add_argument(
        "requirement_id",
        help="requirement_id (e.g. AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING)",
    )

    p_list = sub.add_parser(
        "list",
        help="list requirements / recipes / observers / normalizers / families",
    )
    p_list.add_argument(
        "what",
        nargs="?",
        default="all",
        choices=(
            "all", "requirements", "recipes", "observers",
            "normalizers", "families", "integrations",
        ),
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from .. import __version__
        print(f"reguard {__version__}")
        return 0

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        return cmd_init(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "explain":
        return cmd_explain(args)
    if args.command == "list":
        return cmd_list(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
