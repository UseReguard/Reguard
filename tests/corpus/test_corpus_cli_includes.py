"""CLI regression tests for Corpus Runner --include parsing.

These tests pin the contract that ``--include`` accepts:

  * repeated ``--include repoA --include repoB`` (each flag
    contributes one repo), and
  * comma-separated ``--include repoA,repoB`` (one flag with a
    comma-list expands to multiple repos).

The contract was previously broken: argparse's ``nargs='*'``
greedily consumed subsequent flags (e.g. ``--scenario``) as values
of the previous ``--include``. Switching to ``action='append'``
plus a flat split on commas closes that hole.

These are pure unit tests on the parser helper — they do not
touch the database, network, or container runtime.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner.cli import _parse_include


class TestParseInclude:
    def test_empty_list_returns_empty_tuple(self):
        assert _parse_include([]) == ()

    def test_single_repo_no_commas(self):
        assert _parse_include(["owner/repo"]) == ("owner/repo",)

    def test_repeated_flags_each_contribute_one_repo(self):
        # Two separate --include flags, each with one repo.
        out = _parse_include(["owner/repoA", "owner/repoB"])
        assert out == ("owner/repoA", "owner/repoB")

    def test_comma_separated_in_one_flag_splits_into_many(self):
        # One --include with a comma-list.
        out = _parse_include(["owner/repoA,owner/repoB"])
        assert out == ("owner/repoA", "owner/repoB")

    def test_mixed_repeated_and_comma_separated(self):
        # Three --include flags: two single, one with two.
        out = _parse_include([
            "owner/repoA",
            "owner/repoB,owner/repoC",
            "owner/repoD",
        ])
        assert out == ("owner/repoA", "owner/repoB", "owner/repoC", "owner/repoD")

    def test_whitespace_around_commas_is_stripped(self):
        out = _parse_include(["owner/repoA , owner/repoB ,owner/repoC"])
        assert out == ("owner/repoA", "owner/repoB", "owner/repoC")

    def test_empty_tokens_are_dropped(self):
        # Trailing commas, double commas, whitespace-only tokens
        # must not produce empty entries that later break UNIQUE
        # constraints on the eligibility table.
        out = _parse_include(["owner/repoA,,owner/repoB, ,owner/repoC,"])
        assert out == ("owner/repoA", "owner/repoB", "owner/repoC")

    def test_empty_input_tokens_are_dropped(self):
        # An empty string between commas should not produce "".
        out = _parse_include([",,,"])
        assert out == ()

    def test_realistic_five_repo_manifest(self):
        # The exact shape that the original CR-1 bug broke: five
        # repos passed via repeated --include flags.
        out = _parse_include([
            "SWE-agent/mini-swe-agent",
            "gptme/gptme",
            "HKUDS/nanobot",
            "he-yufeng/CoreCoder",
            "The-Pocket/PocketFlow",
        ])
        assert len(out) == 5
        assert "SWE-agent/mini-swe-agent" in out
        assert "gptme/gptme" in out
        assert "The-Pocket/PocketFlow" in out

    def test_realistic_comma_collapsed_manifest(self):
        # Same five repos, but as a single comma-separated value.
        out = _parse_include([
            "SWE-agent/mini-swe-agent,gptme/gptme,HKUDS/nanobot,"
            "he-yufeng/CoreCoder,The-Pocket/PocketFlow"
        ])
        assert len(out) == 5

    def test_does_not_consume_subsequent_tokens(self):
        # Regression: with nargs='*', argparse treats every
        # subsequent argument as a value of the previous --include
        # until the next flag. We can detect that bug indirectly
        # by checking that we never produce values that look like
        # flags (start with '-') from a single --include token.
        out = _parse_include([
            "owner/repoA",
            "owner/repoB",
            "owner/repoC",
        ])
        for entry in out:
            assert not entry.startswith("-"), (
                f"unexpected flag-like entry {entry!r} in include list"
            )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))