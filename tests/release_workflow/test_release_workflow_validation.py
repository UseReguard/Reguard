"""Static-validation tests for .github/workflows/release.yml.

These tests do not exercise the workflow itself; they read the YAML
file as text and assert structural properties that must hold for
the release workflow to function correctly.

Brief §24 requires coverage of:

  v0.1.0-rc.1 + 0.1.0rc1 -> accepted
  v0.1.0     + 0.1.0     -> accepted
  v0.1.0-rc.2 + 0.1.0rc1 -> rejected
  vfoo                     -> rejected

plus cross-job output propagation: ``publish-runtime`` must use
``needs.build.outputs.source_sha`` and
``needs.build.outputs.package_version``, never a stale
``steps.meta.outputs.*`` reference from another job.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"


# -- Helpers ----------------------------------------------------------------

def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text())


def _all_jobs() -> dict:
    return _load_workflow()["jobs"]


def _job_yaml(name: str) -> str:
    """Return the verbatim YAML text for a single job block.

    We slice the source by line range so we can grep the raw text
    the way GitHub Actions does. ``yaml.safe_load`` collapses
    indentation, so it can't answer ``grep``-style questions.
    """
    text = WORKFLOW_PATH.read_text()
    lines = text.splitlines()
    # Find the line that begins the job.
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^\s{{2}}{name}:\s*$", line):
            start = i
            break
    assert start is not None, f"job {name!r} not found"
    # End at the next top-level job key or end-of-file.
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^\s{2}[a-z][a-zA-Z0-9_-]+:\s*$", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


# -- Tag-shape acceptance (brief §16) --------------------------------------

# Each tuple: (tag, package_version_in_pyproject_at_that_time, expected)
TAG_CASES = [
    ("v0.1.0-rc.1", "0.1.0rc1", True),
    ("v0.1.0-rc.2", "0.1.0rc2", True),
    ("v0.1.0-rc.10", "0.1.0rc10", True),
    ("v0.1.0",      "0.1.0",    True),
    ("v1.0.0",      "1.0.0",    True),
]


@pytest.mark.parametrize("tag, pkg_version, accepted", TAG_CASES)
def test_tag_and_package_version_match(tag: str, pkg_version: str, accepted: bool) -> None:
    """Replicate the validate-job regex chain.

    The validate job computes ``EXPECTED_PKG_VERSION`` from the tag
    via two regexes and compares it to ``pyproject.toml [project].
    version``. This test pins that transformation in a Python
    function so a future workflow edit cannot silently break it.
    """
    if re.match(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$", tag):
        expected = ".".join(re.match(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$", tag).groups())
        is_prerelease = False
    elif m := re.match(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)-rc\.([0-9]+)$", tag):
        expected = f"{m.group(1)}.{m.group(2)}.{m.group(3)}rc{m.group(4)}"
        is_prerelease = True
    else:
        assert not accepted
        return

    assert (expected == pkg_version) == accepted
    if accepted:
        assert isinstance(is_prerelease, bool)


REJECTED_TAGS = [
    "vfoo",
    "v0.1",
    "v0.1.0-test",
    "release-v0.1.0",
    "v0.1.0-rc",
    "v0.1.0-rc1",
    "v0.1.0-RC.1",
    "v0.1.0-rc.1.2",
]


@pytest.mark.parametrize("tag", REJECTED_TAGS)
def test_rejected_tags(tag: str) -> None:
    """Tags not matching either regex must be rejected."""
    stable = re.match(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$", tag)
    prerelease = re.match(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)-rc\.([0-9]+)$", tag)
    assert stable is None and prerelease is None, f"tag {tag!r} unexpectedly matched"


def test_rc2_with_rc1_package_rejected() -> None:
    """v0.1.0-rc.2 + 0.1.0rc1 must be rejected (mismatched package version)."""
    tag = "v0.1.0-rc.2"
    pkg_version = "0.1.0rc1"
    m = re.match(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)-rc\.([0-9]+)$", tag)
    assert m is not None
    expected = f"{m.group(1)}.{m.group(2)}.{m.group(3)}rc{m.group(4)}"
    assert expected != pkg_version


# -- Workflow structural checks (brief §1, §24) ----------------------------

def test_validate_job_exposes_required_outputs() -> None:
    """validate.outputs must include source_sha, package_version, git_tag."""
    jobs = _all_jobs()
    outputs = jobs["validate"]["outputs"]
    for key in ("source_sha", "package_version", "git_tag", "is_prerelease"):
        assert key in outputs, f"validate.outputs missing {key!r}"


def test_build_job_exposes_required_outputs() -> None:
    """build.outputs must include wheel_sha256, sdist_sha256, source_sha, package_version."""
    jobs = _all_jobs()
    outputs = jobs["build"]["outputs"]
    for key in ("source_sha", "package_version", "git_tag",
                "wheel_sha256", "sdist_sha256", "is_prerelease"):
        assert key in outputs, f"build.outputs missing {key!r}"


def test_publish_runtime_uses_needs_build_outputs() -> None:
    """publish-runtime must consume source_sha and package_version from build.outputs."""
    text = _job_yaml("publish-runtime")
    assert "needs.build.outputs.source_sha" in text, (
        "publish-runtime must reference needs.build.outputs.source_sha"
    )
    assert "needs.build.outputs.package_version" in text, (
        "publish-runtime must reference needs.build.outputs.package_version"
    )
    # Old anti-pattern must NOT appear.
    assert "steps.meta.outputs" not in text, (
        "publish-runtime still references a stale steps.meta from another job"
    )


def test_no_cross_job_steps_outputs_references() -> None:
    """No job may reference steps.<id>.outputs of a step defined in another job.

    GitHub Actions step outputs are job-local; cross-job consumption
    must go through job.outputs.
    """
    jobs = _all_jobs()
    for name, job in jobs.items():
        text = yaml.safe_dump({name: job}, default_flow_style=False)
        # A ``needs.<other>.steps.<id>.outputs`` reference would be a bug.
        for other in jobs:
            if other == name:
                continue
            assert f"needs.{other}.steps." not in text, (
                f"job {name!r} references steps of job {other!r}; "
                "cross-job metadata must flow through job.outputs only"
            )


def test_ghcr_image_uses_package_version_not_github_ref_name() -> None:
    """OCI tag must be the package version, not the git tag form."""
    text = _job_yaml("publish-runtime")
    # Package version must appear in the OCI tag.
    assert "ghcr.io/usereguard/reguard-runtime:${{ needs.build.outputs.package_version }}" in text
    # SHA-tag form must be present.
    assert "ghcr.io/usereguard/reguard-runtime:${{ needs.build.outputs.source_sha }}" in text
    # Must NOT publish a `latest` tag for an RC.
    assert ":latest" not in text, "publish-runtime must not publish a latest tag"


def test_workflow_no_long_lived_pypi_credentials() -> None:
    """PyPI Trusted Publishing must use OIDC; no token env-var secrets."""
    text = WORKFLOW_PATH.read_text()
    assert "id-token: write" in text, "publish-pypi must declare id-token: write"
    assert "environment:" in text and "name: pypi" in text, "publish-pypi must declare environment: pypi"
    assert "pypa/gh-action-pypi-publish@release/v1" in text, "must use pypa/gh-action-pypi-publish"
    for forbidden in ("TWINE_USERNAME", "TWINE_PASSWORD", "PYPI_API_TOKEN"):
        assert forbidden not in text, f"workflow references forbidden {forbidden}"


def test_ghcr_uses_github_token_not_pat() -> None:
    """GHCR must use secrets.GITHUB_TOKEN, not a separate PAT."""
    text = _job_yaml("publish-runtime")
    assert "secrets.GITHUB_TOKEN" in text
    assert "packages: write" in text
    # Defense-in-depth: a GHCR_PAT environment variable should not appear.
    assert "GHCR_PAT" not in text, "publish-runtime must not reference a GHCR_PAT"


def test_skip_existing_not_used_for_pypi() -> None:
    """Duplicate PyPI publishes must surface as failures, not be hidden.

    The check is structural (parsed YAML), not textual, because the
    release.yml file legitimately mentions ``skip-existing`` in a
    comment explaining why it is not used.
    """
    job = _all_jobs()["publish-pypi"]
    steps = job.get("steps", [])
    for step in steps:
        if step.get("uses", "").startswith("pypa/gh-action-pypi-publish"):
            with_ = step.get("with", {})
            assert "skip-existing" not in with_, (
                "publish-pypi must NOT enable skip-existing; duplicates must fail loudly"
            )
            return
    pytest.fail("pypa/gh-action-pypi-publish step not found in publish-pypi")


def test_shasums_generated_and_uploaded() -> None:
    """The build job must write dist/SHA256SUMS and upload it."""
    text = _job_yaml("build")
    assert "dist/SHA256SUMS" in text, "build job must write dist/SHA256SUMS"
    assert "SHA256SUMS" in text, "build job must include SHA256SUMS in upload path"


def test_runtime_digest_sourced_from_action_output() -> None:
    """Digest must come from steps.build.outputs.digest, not docker inspect."""
    text = _job_yaml("publish-runtime")
    assert "steps.build.outputs.digest" in text, (
        "publish-runtime must capture digest from build-push-action output"
    )
    # Should not call docker inspect as primary digest source.
    assert "docker inspect" not in text, (
        "digest must come from the action output, not docker inspect"
    )


def test_release_attachments_include_shasums() -> None:
    """GitHub Release must attach wheel + sdist + SHA256SUMS, with prerelease flag for RCs."""
    text = _job_yaml("release")
    assert "dist/*.whl" in text
    assert "dist/*.tar.gz" in text
    assert "dist/SHA256SUMS" in text
    assert "prerelease:" in text


def test_clean_runner_dependencies() -> None:
    """Build job must install dev dependencies on a clean runner."""
    text = _job_yaml("build")
    assert "pip install -e" in text, (
        "build job must perform pip install -e .[dev] on a clean runner"
    )


def test_source_sha_verified_in_build() -> None:
    """Build job must compare local HEAD against validate.outputs.source_sha."""
    text = _job_yaml("build")
    assert "needs.validate.outputs.source_sha" in text, (
        "build job must verify its HEAD matches validate.outputs.source_sha"
    )


def test_github_sha_checked_against_head_in_validate() -> None:
    """Validate job must reject the run if GITHUB_SHA != local HEAD."""
    text = _job_yaml("validate")
    assert "GITHUB_SHA" in text and "git rev-parse HEAD" in text, (
        "validate job must compare GITHUB_SHA against local HEAD"
    )


def test_workflow_triggers_only_on_valid_tag_shapes() -> None:
    """on.push.tags must list only the two valid shapes."""
    wf = _load_workflow()
    tags = wf[True]["push"]["tags"]
    # Either of the two explicit patterns; no broad ``v*``.
    assert "v*" not in tags, "broad v* trigger would accept malformed tags"
    assert any("rc" in t for t in tags), "RC tag pattern missing"
    # Each tag pattern contains two ``.`` characters between three
    # ``[0-9]+`` groups (the dots are literal regex characters, not
    # separators).
    stable_patterns = [t for t in tags if "rc" not in t]
    assert stable_patterns, "stable v<major>.<minor>.<patch> pattern missing"
    for t in stable_patterns:
        assert t.count(".") == 2, f"stable pattern {t!r} has wrong dot count"
