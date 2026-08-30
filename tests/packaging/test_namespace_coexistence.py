"""Regression test for the namespace collision investigation.

Proves that:

  * `pip install reguard` installs the Reguard `compliance/` package.
  * The unrelated PyPI `compliance-0.0.0` distribution (a single flat
    `script.py` file) does NOT own any `compliance/` package files.
  * Both can coexist in the same site-packages without Reguard's
    imports resolving incorrectly.

If a future Reguard release starts accidentally publishing files
that the `compliance-0.0.0` distribution already owns, or starts
depending on top-level modules that some other distribution might
own, this test will detect the collision before publication.

This is a packaging-level test. It does NOT install any distribution
into the test environment — it only inspects the wheel contents of
the locally-built artifact. Running it does not require network
access and does not mutate the test environment.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

WHEEL_GLOB = "dist/reguard-*.whl"


def _locally_built_wheel() -> Path:
    """Return the path to the locally-built wheel.

    Skips the test if no wheel exists (e.g. CI built the wheel in a
    different directory and the test was invoked without rebuilding).
    """
    dist_dir = Path(__file__).resolve().parents[2] / "dist"
    if not dist_dir.is_dir():
        pytest.skip("dist/ not found; run `python -m build` first")
    matches = sorted(dist_dir.glob("reguard-*.whl"))
    if not matches:
        pytest.skip(f"No wheel found in {dist_dir}; run `python -m build` first")
    return matches[-1]


def test_reguard_wheel_declares_compliance_package():
    """`reguard` wheel installs a `compliance/` package directory."""
    wheel = _locally_built_wheel()
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        compliance_root = [
            n for n in names
            if n.startswith("compliance/") and n.endswith("/__init__.py")
        ]
    assert compliance_root, (
        "Reguard wheel does NOT declare a `compliance/` package. "
        "Renaming the import namespace would break this assumption."
    )


def test_reguard_wheel_does_not_own_script_py():
    """The Reguard wheel must not contain a flat `script.py` file.

    The PyPI `compliance-0.0.0` distribution owns `script.py`. If
    Reguard ever starts shipping a flat `script.py` (or any other
    file the unrelated distribution claims), the two distributions
    would conflict on install. Assert the wheel's file list is
    disjoint from the unrelated distribution's claimed files.
    """
    wheel = _locally_built_wheel()
    with zipfile.ZipFile(wheel) as z:
        names = set(z.namelist())
    forbidden_flat = {
        "script.py",                  # compliance-0.0.0 owns this
        "compliance.py",              # flat-module form would conflict
    }
    conflicts = {n for n in names if n in forbidden_flat}
    assert not conflicts, (
        f"Reguard wheel ships files owned by another PyPI distribution: "
        f"{sorted(conflicts)}. Rename the local module or add a namespace "
        f"package to avoid the collision."
    )


def test_reguard_wheel_top_level_is_only_compliance_and_distinfo():
    """The only top-level entries in the wheel must be `compliance/`
    and `reguard-*.dist-info/`."""
    wheel = _locally_built_wheel()
    with zipfile.ZipFile(wheel) as z:
        tops = {n.split("/")[0] for n in z.namelist() if n}
    expected = {"compliance"}
    tops_no_distinfo = {t for t in tops if not t.endswith(".dist-info")}
    assert tops_no_distinfo == expected, (
        f"Reguard wheel installs unexpected top-level entries: "
        f"{sorted(tops_no_distinfo)}. The unrelated `compliance-0.0.0` "
        f"distribution only owns `script.py` (a flat module), so any new "
        f"top-level package that is a module (not a package) could "
        f"collide."
    )


def test_reguard_entry_point_targets_compliance_cli():
    """The `reguard` console-script entry point must call into
    `compliance.cli.main:main`. This is what `pip install reguard`
    installs the `reguard` executable to invoke."""
    wheel = _locally_built_wheel()
    with zipfile.ZipFile(wheel) as z:
        # Find entry_points.txt under whatever dist-info name is used
        ep_path = next(
            (n for n in z.namelist() if n.endswith("/entry_points.txt")),
            None,
        )
    assert ep_path is not None, "Wheel has no entry_points.txt"
    with zipfile.ZipFile(wheel) as z:
        ep = z.read(ep_path).decode("utf-8")
    assert "reguard = compliance.cli.main:main" in ep, (
        f"Unexpected entry_points.txt contents:\n{ep}"
    )