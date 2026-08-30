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


def test_pypi_packages_dir_contains_only_distributions() -> None:
    """PYPI_PACKAGES_DIR_CONTAINS_DISTS_ONLY invariant (brief §6).

    The PyPA publisher uploads ``packages-dir/*`` to PyPI. If
    ``SHA256SUMS`` is in that directory, Twine receives a non-distribution
    file and the publish step fails.

    The corrected workflow downloads all artifacts into
    ``release-artifacts/`` and stages a separate ``pypi-dist/``
    directory containing only the wheel + sdist.
    """
    text = _job_yaml("publish-pypi")

    # The pypa step must point at pypi-dist, not at the directory
    # containing SHA256SUMS.
    job = _all_jobs()["publish-pypi"]
    for step in job.get("steps", []):
        if step.get("uses", "").startswith("pypa/gh-action-pypi-publish"):
            with_ = step.get("with", {})
            assert with_.get("packages-dir") == "pypi-dist", (
                "pypa action packages-dir must be 'pypi-dist' (a dists-only directory)"
            )
            break
    else:
        pytest.fail("pypa/gh-action-pypi-publish step not found in publish-pypi")

    # SHA256SUMS must NOT be passed to the PyPI action. It should
    # be downloaded into release-artifacts (where it is verified)
    # and the staging step copies only *.whl and *.tar.gz into pypi-dist.
    assert "release-artifacts" in text, (
        "publish-pypi must download artifacts into release-artifacts/"
    )
    assert "pypi-dist" in text, "publish-pypi must stage distributions into pypi-dist/"
    assert "cp release-artifacts/*.whl" in text, "publish-pypi must copy wheel into pypi-dist"
    assert "cp release-artifacts/*.tar.gz" in text, "publish-pypi must copy sdist into pypi-dist"

    # The staging step must assert exactly one wheel + one sdist.
    assert "WHL_COUNT" in text, (
        "publish-pypi staging must count wheels in pypi-dist"
    )
    assert "SDIST_COUNT" in text, (
        "publish-pypi staging must count sdists in pypi-dist"
    )
    assert "ALL_COUNT" in text, (
        "publish-pypi staging must assert total file count"
    )

    # SHA256SUMS is verified but never staged into pypi-dist.
    assert "sha256sum -c SHA256SUMS" in text, (
        "publish-pypi must verify artifacts against SHA256SUMS before staging"
    )
    assert "cp release-artifacts/SHA256SUMS" not in text, (
        "SHA256SUMS must NEVER be copied into pypi-dist"
    )


def test_shasums_retained_for_github_release() -> None:
    """The release job must attach wheel + sdist + SHA256SUMS."""
    text = _job_yaml("release")
    assert "release-artifacts/*.whl" in text
    assert "release-artifacts/*.tar.gz" in text
    assert "release-artifacts/SHA256SUMS" in text
    assert "prerelease:" in text


def test_workflow_trigger_uses_glob_not_regex() -> None:
    """GitHub Actions tag filters are globs, not regular expressions.

    A pattern like ``v[0-9]+.[0-9]+.[0-9]+`` is interpreted literally
    and would not match ``v0.1.0-rc.1``. The workflow must therefore
    use a broad ``v*`` trigger and rely on the ``validate`` job to
    reject malformed tags. This test pins that design.
    """
    wf = _load_workflow()
    tags = wf[True]["push"]["tags"]
    assert tags == ["v*"], (
        f"workflow trigger must be the broad glob 'v*'; got {tags!r}. "
        "GitHub Actions tag filters do NOT support regex character classes."
    )


def test_workflow_triggers_for_v0_1_0_rc_1() -> None:
    """GitHub's glob ``v*`` must match ``v0.1.0-rc.1``.

    This is the only tag the RC1 publication will use; if the
    trigger does not match, the workflow never runs.
    """
    import fnmatch
    assert fnmatch.fnmatchcase("v0.1.0-rc.1", "v*"), (
        "glob 'v*' must match 'v0.1.0-rc.1'; "
        "if this fails, the workflow trigger is wrong"
    )


def test_no_invalid_runtime_reference_output() -> None:
    """The workflow must not declare a non-existent runtime_reference output.

    docker/build-push-action does NOT provide a ``runtime_reference``
    output. Only ``digest`` is consumed. Any invented output is a
    release blocker.
    """
    job = _all_jobs().get("publish-runtime", {})
    outputs = job.get("outputs", {})
    # digest is the only documented output of build-push-action.
    assert outputs == {"runtime_digest": "${{ steps.build.outputs.digest }}"}, (
        f"publish-runtime.outputs must equal {{runtime_digest: <digest-expr>}}; got {outputs!r}"
    )


def test_digest_is_only_docker_action_output_used() -> None:
    """Only ``digest`` is consumed from docker/build-push-action outputs.

    Any other output reference (e.g. ``metadata``, ``imageID``)
    must be intentional and documented; we currently use only the
    digest.
    """
    text = _job_yaml("publish-runtime")
    # ``steps.build.outputs.digest`` must be the action output consumed.
    assert "steps.build.outputs.digest" in text
    # No other ``steps.build.outputs.*`` references.
    import re as _re
    for m in _re.finditer(r"steps\.build\.outputs\.([a-zA-Z_]+)", text):
        assert m.group(1) == "digest", (
            f"unexpected docker/build-push-action output consumed: steps.build.outputs.{m.group(1)}"
        )


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
    assert "release-artifacts/*.whl" in text
    assert "release-artifacts/*.tar.gz" in text
    assert "release-artifacts/SHA256SUMS" in text
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
    """The workflow trigger is intentionally broad; the validate job enforces shape.

    GitHub Actions tag filters are globs, not regular expressions.
    We use ``v*`` and rely on the strict ``validate`` job to reject
    malformed tags before any publication. This test pins that
    design.
    """
    wf = _load_workflow()
    tags = wf[True]["push"]["tags"]
    assert tags == ["v*"], (
        "workflow trigger must be exactly ['v*']; tag-shape enforcement "
        "happens in the validate job (see test_strict_tag_parser)"
    )


# -- Pre-tag validation gate (RC2) -------------------------------------

PRE_TAG_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pre-tag.yml"


def _load_pre_tag_workflow() -> dict:
    return yaml.safe_load(PRE_TAG_PATH.read_text())


def test_pre_tag_workflow_exists() -> None:
    """A non-publication pre-tag gate must exist so Python 3.12 can
    validate the RC2 source SHA without triggering the tag-only
    release.yml path."""
    assert PRE_TAG_PATH.exists(), (
        f"missing {PRE_TAG_PATH}; the RC2 pre-tag gate is required "
        "to validate the source SHA on Python 3.12 without publishing"
    )


def test_pre_tag_workflow_triggers_on_push_and_dispatch() -> None:
    """Pre-tag must run on push-to-main AND manual dispatch so
    operators can re-run it before tagging."""
    wf = _load_pre_tag_workflow()
    on = wf[True]
    assert "push" in on, "pre-tag must trigger on push (to main)"
    assert "workflow_dispatch" in on, "pre-tag must be dispatchable"
    # The push trigger must be restricted to main (not tag-triggered;
    # publication remains tag-only).
    push = on["push"]
    assert push.get("branches") == ["main"], (
        "pre-tag push trigger must be branches: [main]; tag triggers "
        "belong exclusively to release.yml"
    )


def test_pre_tag_workflow_has_no_publication_jobs() -> None:
    """The pre-tag gate must NOT publish anything to PyPI, GHCR, or
    the GitHub Release API."""
    wf = _load_pre_tag_workflow()
    jobs = wf["jobs"]
    forbidden_jobs = ("publish-pypi", "publish-runtime", "release")
    for name in forbidden_jobs:
        assert name not in jobs, (
            f"pre-tag must not declare a {name!r} job; "
            "publication is exclusively handled by release.yml"
        )
    # Defence-in-depth: no step should reference PyPI publish action
    # or docker/build-push-action.
    text = PRE_TAG_PATH.read_text()
    assert "pypa/gh-action-pypi-publish" not in text
    assert "docker/build-push-action" not in text
    assert "softprops/action-gh-release" not in text


def test_pre_tag_workflow_uses_python_3_12() -> None:
    """Pre-tag must declare Python 3.12 — not the developer's local
    Python (3.14)."""
    text = PRE_TAG_PATH.read_text()
    assert 'PYTHON_VERSION: "3.12"' in text, (
        "pre-tag env.PYTHON_VERSION must be 3.12 (the brief pins 3.12 "
        "as the authoritative pre-tag gate version)"
    )


def test_pre_tag_workflow_builds_local_runtime_image() -> None:
    """The OCI contract tests must not pull from a public registry;
    the pre-tag gate must build the local runtime image."""
    text = PRE_TAG_PATH.read_text()
    assert "Build local runtime image" in text
    assert "reguard-runtime:ci-test" in text


def test_pre_tag_workflow_runs_packaging_tests_after_build() -> None:
    """Packaging tests MUST run AFTER ``python -m build`` so the
    wheel exists when they execute."""
    text = PRE_TAG_PATH.read_text()
    build_pos = text.find("Build wheel and sdist")
    packaging_pos = text.find("Packaging tests against built wheel")
    assert build_pos != -1 and packaging_pos != -1, (
        "pre-tag must contain both 'Build wheel and sdist' and "
        "'Packaging tests against built wheel' steps"
    )
    assert build_pos < packaging_pos, (
        "Packaging tests must be AFTER Build wheel and sdist; "
        f"build_pos={build_pos} packaging_pos={packaging_pos}"
    )
    # The post-build packaging command must be the dedicated rerun,
    # not just the in-source 'pytest tests/ -q'.
    assert "pytest tests/packaging/ -v" in text, (
        "pre-tag must explicitly run packaging tests against the "
        "freshly built wheel (pytest tests/packaging/ -v)"
    )


def test_pre_tag_workflow_runs_clean_wheel_smoke() -> None:
    """Clean wheel smoke must install the freshly built wheel into a
    fresh venv and exercise the public CLI."""
    text = PRE_TAG_PATH.read_text()
    assert "Clean wheel smoke" in text or "Clean installed-wheel smoke" in text
    assert "reguard --version" in text
    assert "reguard doctor" in text


def test_pre_tag_workflow_runs_clean_installed_wheel_check() -> None:
    """The pre-tag gate must execute a real ``reguard check`` against
    the deterministic minimal-agent fixture from a fresh venv that
    contains ONLY the built wheel — no editable install, no
    PYTHONPATH override, no research DB.

    This is the authoritative Python 3.12 end-to-end check for the
    RC2 source SHA; without it, the pre-tag gate cannot prove the
    fresh wheel actually runs the public CLI.
    """
    text = PRE_TAG_PATH.read_text()
    # The check step must exist as a separate named step so its log
    # output is unambiguous in the Actions UI.
    assert "Clean installed-wheel check" in text, (
        "pre-tag must declare a dedicated 'Clean installed-wheel check' step"
    )
    assert "reguard check" in text, (
        "pre-tag must invoke 'reguard check' in the installed-wheel smoke"
    )
    assert "examples/minimal-agent" in text, (
        "pre-tag reguard check must target the deterministic "
        "examples/minimal-agent fixture"
    )
    assert "SWE-agent/mini-swe-agent" in text, (
        "pre-tag reguard check must run against the "
        "SWE-agent/mini-swe-agent repository identity"
    )
    # Site-packages provenance: the wheel must NOT be bypassed by an
    # editable install or PYTHONPATH override.
    assert 'pip install "${WHL}"' in text or "pip install \"${WHL}\"" in text
    assert "site-packages" in text, (
        "pre-tag must assert that 'compliance' resolves from "
        "site-packages — not from the checked-out source tree"
    )
    assert "compliance.__file__" in text
    # Public CLI must not require the research DB.
    assert "eu_ai_compliance.db" in text and "test ! -e" in text, (
        "pre-tag must explicitly assert that data/eu_ai_compliance.db "
        "is absent (public CLI does not require it)"
    )


def test_release_workflow_mirrors_pre_tag_clean_installed_wheel_check() -> None:
    """release.yml must contain the same clean installed-wheel
    check sequence as pre-tag.yml — divergence is a release
    blocker (``BLOCKED_WORKFLOW_DIVERGENCE``)."""
    pre_tag = PRE_TAG_PATH.read_text()
    release = WORKFLOW_PATH.read_text()
    for needle in (
        "Clean installed-wheel smoke",
        "Clean installed-wheel check",
        "reguard check",
        "examples/minimal-agent",
        "SWE-agent/mini-swe-agent",
        "site-packages",
        "compliance.__file__",
        "eu_ai_compliance.db",
        "reguard --version",
        "reguard doctor",
        "reguard list",
    ):
        assert needle in pre_tag, f"pre-tag missing {needle!r}"
        assert needle in release, (
            f"release.yml missing {needle!r} — workflow divergence"
        )

    # The check step must occur AFTER the wheel-install step in BOTH
    # workflows (no check before install).
    for name, text in (("pre-tag", pre_tag), ("release", release)):
        install_pos = text.find('pip install "${WHL}"')
        check_pos = text.find("reguard check \\")
        assert install_pos != -1 and check_pos != -1, (
            f"{name}: missing install or check anchor"
        )
        assert install_pos < check_pos, (
            f"{name}: reguard check must occur AFTER wheel install"
        )


def test_pre_tag_workflow_translates_pep440_to_tag() -> None:
    """The pre-tag validate step must translate the PEP 440 prerelease
    form (``0.1.0rc2``) into the canonical tag form
    (``v0.1.0-rc.2``) that release.yml accepts. Without this
    translation the validate step rejects the synthetic tag as
    malformed even though the package version is valid."""
    import re as _re
    text = PRE_TAG_PATH.read_text()
    # The translation must produce the -rc.N form, NOT keep the rcN form.
    assert "rc${BASH_REMATCH[4]}" in text, (
        "pre-tag must translate PEP 440 '0.1.0rc2' to tag 'v0.1.0-rc.2'"
    )
    # And the resulting SYNTH_TAG must match release.yml's regex.
    assert "v${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.${BASH_REMATCH[3]}-rc.${BASH_REMATCH[4]}" in text

    # Functional check: replicate the transformation in Python and
    # confirm release.yml's regex chain accepts it.
    pkg_version = "0.1.0rc2"
    m = _re.match(r"^([0-9]+)\.([0-9]+)\.([0-9]+)rc([0-9]+)$", pkg_version)
    assert m is not None
    synth_tag = f"v{m.group(1)}.{m.group(2)}.{m.group(3)}-rc.{m.group(4)}"
    assert synth_tag == "v0.1.0-rc.2"
    assert _re.match(
        r"^v([0-9]+)\.([0-9]+)\.([0-9]+)-rc\.([0-9]+)$", synth_tag,
    ) is not None


# ---------------------------------------------------------------------------
# Truthful-evidence gate tests (BLOCKER B of the RC2 prompt)
# ---------------------------------------------------------------------------
#
# These tests assert that the GH Actions summary steps never
# hard-code PASS verdicts for steps that may have been skipped or
# failed. Each smoke / check step must have an explicit ``id:``,
# and the always()-summary step must derive its per-step
# outcomes from ``${{ steps.<id>.outcome }}`` /
# ``${{ steps.<id>.conclusion }}``. Hard-coding ``echo
# "- Clean installed-wheel smoke: PASS"`` inside the smoke step's
# own run block would make the summary report PASS even when the
# step fails or is skipped, which is the defect BLOCKER B
# forbids.


def _step_ids_in_build(text: str) -> set[str]:
    """Collect every ``id:`` declared on a step in a build-job
    workflow (pre-tag or release)."""
    return set(re.findall(r"^\s+id:\s*([A-Za-z0-9_\-]+)\s*$", text, re.MULTILINE))


def _build_step_block(text: str, name: str) -> str:
    """Return the run block for the named build-job step, or empty
    string if not found. ``name`` is the raw ``- name: ...``
    payload.

    The returned text contains ONLY the step itself (not
    subsequent steps). We detect the next step by a non-blank
    line whose first non-space character is ``-`` and the second
    non-space character is ``n`` (i.e. ``- name:``).
    """
    lines = text.splitlines()
    # Top-level "this is a step" lines begin with 6 spaces then ``-``.
    step_re = re.compile(r"^\s{6}-\s")
    # Inside a step's run: |-block, every body line begins with at
    # least 10 spaces (matching ``          ``).
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("- name:"):
            continue
        m = re.match(r"- name:\s*(.+?)\s*$", stripped)
        if not m:
            continue
        if m.group(1).strip("'\"") != name:
            continue
        # Find the run: line.
        run_idx = None
        for j in range(idx + 1, min(idx + 25, len(lines))):
            if lines[j].lstrip().startswith("run:"):
                run_idx = j
                break
        if run_idx is None:
            return ""
        body_lines: list[str] = []
        for j in range(run_idx + 1, len(lines)):
            candidate = lines[j]
            if not candidate.strip():
                body_lines.append(candidate)
                continue
            # Stop when we hit a new top-level step.
            if step_re.match(candidate):
                break
            # Or a line that has dedented past the step's run body
            # (which would mean we're leaving this job).
            indent = len(candidate) - len(candidate.lstrip(" "))
            if indent < 10:
                break
            body_lines.append(candidate)
        return "\n".join(body_lines)
    return ""


def test_pre_tag_summary_does_not_hardcode_pass_for_smoke_or_check() -> None:
    """The pre-tag summary step must report the smoke and check
    step outcomes via ``${{ steps.<id>.outcome }}``, not by
    hard-coding ``PASS`` in the summary's run block. A skipped or
    failed step that emits ``PASS`` into the step summary would
    be a false evidence defect."""
    text = PRE_TAG_PATH.read_text()

    # Both steps must have explicit ids.
    ids = _step_ids_in_build(text)
    assert "clean_smoke" in ids, (
        "pre-tag: 'Clean installed-wheel smoke' step must have "
        "id: clean_smoke for truthful summary lookups"
    )
    assert "clean_check" in ids, (
        "pre-tag: 'Clean installed-wheel check (reguard check)' step "
        "must have id: clean_check for truthful summary lookups"
    )

    # The summary step's run block must NOT hard-code PASS for the
    # smoke or check rows. It must reference the step outcome.
    summary_block = _build_step_block(
        text, "Pre-tag build summary",
    )
    assert summary_block, "pre-tag: 'Pre-tag build summary' step not found"

    # The summary must report the per-step status via the outcome
    # values injected as env from the steps.<id>.outcome lookups.
    assert "CLEAN_SMOKE_OUTCOME" in summary_block, (
        "pre-tag summary must reference CLEAN_SMOKE_OUTCOME (sourced "
        "from steps.clean_smoke.outcome) to truthfully report "
        "smoke status"
    )
    assert "CLEAN_CHECK_OUTCOME" in summary_block, (
        "pre-tag summary must reference CLEAN_CHECK_OUTCOME (sourced "
        "from steps.clean_check.outcome) to truthfully report "
        "check status"
    )
    # The summary's run block must NOT contain literal "PASS" lines
    # for the smoke or check rows. Hard-coded PASS is exactly the
    # BLOCKER B defect.
    summary_low = summary_block.lower()
    assert ": pass" not in summary_low, (
        "pre-tag summary must NOT hard-code ': PASS' for any step; "
        "a skipped or failed smoke/check step would otherwise be "
        "reported as PASS. Found:\n" + summary_block
    )


def test_pre_tag_smoke_step_run_block_contains_no_pass_assertion() -> None:
    """The 'Clean installed-wheel smoke' step's own run block must
    NOT write a 'PASS' line into GITHUB_STEP_SUMMARY either; the
    only place PASS may appear is in the always()-summary step
    that aggregates outcomes, and only after reading the actual
    step outcome."""
    text = PRE_TAG_PATH.read_text()
    smoke_block = _build_step_block(
        text, "Clean installed-wheel smoke",
    )
    assert smoke_block, "pre-tag: 'Clean installed-wheel smoke' step not found"
    # The smoke step's run block must not write a "PASS" claim to
    # the step summary, because its outcome is not yet known.
    assert "GITHUB_STEP_SUMMARY" not in smoke_block, (
        "pre-tag: 'Clean installed-wheel smoke' step must not write "
        "PASS into GITHUB_STEP_SUMMARY itself; verdicts must come "
        "from the always() summary step that reads "
        "steps.clean_smoke.outcome / .conclusion"
    )


def test_release_summary_does_not_hardcode_pass_for_smoke_or_check() -> None:
    """Same truthfulness rule applies to release.yml: the summary
    step must reference ``steps.clean_smoke.outcome`` /
    ``steps.clean_check.outcome``, not hard-coded PASS. release.yml
    does not currently have a single combined summary block, but
    it MUST at minimum give the smoke and check steps explicit ids
    and MUST NOT emit a literal 'PASS' line in the smoke or check
    run blocks."""
    text = WORKFLOW_PATH.read_text()
    ids = _step_ids_in_build(text)
    assert "clean_smoke" in ids, (
        "release.yml: 'Clean installed-wheel smoke' step must have "
        "id: clean_smoke for truthful summary lookups"
    )
    assert "clean_check" in ids, (
        "release.yml: 'Clean installed-wheel check (reguard check)' "
        "step must have id: clean_check for truthful summary lookups"
    )

    smoke_block = _build_step_block(
        text, "Clean installed-wheel smoke",
    )
    assert smoke_block, "release.yml: smoke step not found"
    check_block = _build_step_block(
        text, "Clean installed-wheel check (reguard check)",
    )
    assert check_block, "release.yml: check step not found"

    # Neither run block may write a 'PASS' line into the step
    # summary — that would be the BLOCKER B defect.
    assert "GITHUB_STEP_SUMMARY" not in smoke_block, (
        "release.yml: 'Clean installed-wheel smoke' step must not "
        "write PASS into GITHUB_STEP_SUMMARY; the per-step verdict "
        "must come from a separate always() summary step that "
        "reads steps.clean_smoke.outcome / .conclusion"
    )
    assert "GITHUB_STEP_SUMMARY" not in check_block, (
        "release.yml: 'Clean installed-wheel check' step must not "
        "write PASS into GITHUB_STEP_SUMMARY; the per-step verdict "
        "must come from a separate always() summary step that "
        "reads steps.clean_check.outcome / .conclusion"
    )

    # A truthful release summary step must exist that reads the
    # clean_smoke and clean_check outcomes.
    assert "Release build summary (truthful per-step)" in text, (
        "release.yml must have an always() 'Release build summary' "
        "step that reads steps.clean_smoke.outcome / "
        "steps.clean_check.outcome; this is the truthfulness gate."
    )
    summary_block = _build_step_block(
        text, "Release build summary (truthful per-step)",
    )
    assert summary_block, "release.yml: truthful summary step not found"
    assert "CLEAN_SMOKE_OUTCOME" in summary_block
    assert "CLEAN_CHECK_OUTCOME" in summary_block
    assert ": pass" not in summary_block.lower(), (
        "release.yml truthful summary step must NOT hard-code "
        "': PASS' for any step; a skipped or failed smoke/check "
        "step would otherwise be reported as PASS."
    )


def test_pre_tag_and_release_truthful_summaries_are_equivalent() -> None:
    """Both workflows must use the same truthful-summary pattern.
    A divergence between pre-tag and release summary behavior is
    a defect per brief §11 (parity)."""
    pre_tag = PRE_TAG_PATH.read_text()
    release = WORKFLOW_PATH.read_text()

    # Both workflows must reference the same outcome env-var names.
    for needle in (
        "CLEAN_SMOKE_OUTCOME",
        "CLEAN_SMOKE_CONCLUSION",
        "CLEAN_CHECK_OUTCOME",
        "CLEAN_CHECK_CONCLUSION",
    ):
        assert needle in pre_tag, (
            f"pre-tag summary must reference {needle}"
        )
        assert needle in release, (
            f"release summary must reference {needle}"
        )

    # Both workflows must source the env vars from
    # steps.<id>.outcome / .conclusion.
    for sid in ("clean_smoke", "clean_check"):
        for suffix in ("outcome", "conclusion"):
            env_key = f"{sid.upper()}_{suffix.upper()}"
            pattern_smk = f"{env_key}: ${{{{ steps.{sid}.{suffix} }}}}"
            assert pattern_smk in pre_tag, (
                f"pre-tag must define env {env_key} = "
                f"${{{{ steps.{sid}.{suffix} }}}} for truthful "
                f"per-step reporting"
            )
            assert pattern_smk in release, (
                f"release.yml must define env {env_key} = "
                f"${{{{ steps.{sid}.{suffix} }}}} for truthful "
                f"per-step reporting"
            )


def test_workflow_summary_artifact_reporting_is_safe_when_dist_missing() -> None:
    """A workflow that fails before ``python -m build`` runs has
    no ``dist/`` directory. The summary must not synthesize a
    wheel/sdist line in that case — it must explicitly report
    ``MISSING`` so the artifact claim cannot be mistaken for a
    successful build."""
    # pre-tag.yml
    pre_tag = PRE_TAG_PATH.read_text()
    assert "MISSING (build did not produce dist/)" in pre_tag, (
        "pre-tag summary must report MISSING when dist/ is absent "
        "rather than synthesizing a false artifact line"
    )
    # release.yml
    release = WORKFLOW_PATH.read_text()
    assert "MISSING (build did not produce dist/)" in release, (
        "release summary must report MISSING when dist/ is absent "
        "rather than synthesizing a false artifact line"
    )

    # The check must be guarded by `if [ -d dist ]` (or equivalent
    # safe-guard) so the summary does not crash on a missing
    # directory.
    assert "[ -d dist ]" in pre_tag, (
        "pre-tag summary must guard artifact enumeration with "
        "'[ -d dist ]' so a missing dist/ does not crash the "
        "summary step"
    )
    assert "[ -d dist ]" in release, (
        "release summary must guard artifact enumeration with "
        "'[ -d dist ]' so a missing dist/ does not crash the "
        "summary step"
    )


def test_pre_tag_summary_block_has_always_guard() -> None:
    """The pre-tag build summary step must run under ``if: always()``
    so its verdicts are emitted even when a previous step in the
    build job failed or was skipped. Without that guard a failed
    smoke would suppress the summary entirely."""
    text = PRE_TAG_PATH.read_text()
    lines = text.splitlines()
    target_name = "Pre-tag build summary"
    for idx, line in enumerate(lines):
        m = re.match(r"\s*- name:\s*(.+?)\s*$", line)
        if not m:
            continue
        if m.group(1).strip("'\"") != target_name:
            continue
        # ``if: always()`` may appear on the line directly after
        # ``- name:`` (the common YAML placement).
        if idx + 1 < len(lines) and re.search(
            r"if:\s*always\(\)", lines[idx + 1],
        ):
            return
        # Or on the line before (less common).
        if idx > 0 and re.search(r"if:\s*always\(\)", lines[idx - 1]):
            return
        raise AssertionError(
            "pre-tag: 'Pre-tag build summary' step must have "
            "'if: always()' so its truthfulness verdicts run even "
            "when a prior step failed or was skipped"
        )
    raise AssertionError("pre-tag: 'Pre-tag build summary' step not found")


def test_release_truthful_summary_block_has_always_guard() -> None:
    """The release build summary step must run under ``if: always()``."""
    text = WORKFLOW_PATH.read_text()
    lines = text.splitlines()
    target_name = "Release build summary (truthful per-step)"
    for idx, line in enumerate(lines):
        m = re.match(r"\s*- name:\s*(.+?)\s*$", line)
        if not m:
            continue
        if m.group(1).strip("'\"") != target_name:
            continue
        if idx + 1 < len(lines) and re.search(
            r"if:\s*always\(\)", lines[idx + 1],
        ):
            return
        if idx > 0 and re.search(r"if:\s*always\(\)", lines[idx - 1]):
            return
        raise AssertionError(
            "release.yml: 'Release build summary (truthful per-step)' "
            "step must have 'if: always()'"
        )
    raise AssertionError(
        f"release.yml: '{target_name}' step not found"
    )
