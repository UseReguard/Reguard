# Reguard Core v0.1.0rc1 — Remote Public-Artifact Smoke Plan

**Date:** 2026-08-30
**Status:** `PENDING_EXTERNAL_PUBLICATION`

This plan documents the **only** test that proves Reguard Core
v0.1.0rc1 works end-to-end against public artifacts. It cannot be
executed until PyPI and GHCR have been published.

---

## The test

The smoke test is run against a fresh repository that:

- Has NO relation to Reguard's own source tree.
- Uses only published artifacts.
- Tests every status (`PASS`, `FAIL`, `UNKNOWN`, `UNSUPPORTED`,
  `ERROR`).
- Tests provider-secret isolation.
- Verifies GitHub Action step summary, outputs, and
  artifact upload.

## Pre-requisites (publication gates that must complete first)

1. **PyPI publish**: `reguard==0.1.0rc1` wheel uploaded and visible
   on https://pypi.org/project/reguard/.
2. **GHCR publish**: `ghcr.io/reguard-core/reguard-runtime:0.1.0rc1`
   image pushed and visible.
3. **GitHub tag**: `Reguard-Core/reguard@v0.1.0-rc.1` tag pushed
   to GitHub.
4. **GitHub release**: `v0.1.0-rc.1` draft release created (if
   desired; not strictly required for the smoke).

## Test consumer repository

Create a fresh public repository, e.g.
`https://github.com/Reguard-Core/reguard-rc1-consumer-smoke`.
Its only contents are:

```yaml
# .github/workflows/reguard-rc1-smoke.yml
name: reguard-rc1-smoke
on:
  workflow_dispatch:
  push:

jobs:
  smoke-pass:
    name: PASS expected
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Add demo
        run: |
          git clone https://github.com/Reguard-Core/reguard
          cp -r reguard/examples/minimal-agent/* .
      - uses: Reguard-Core/reguard@v0.1.0-rc.1
        with:
          reguard-version: 0.1.0rc1
          fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED

  smoke-provider-secret-blocked:
    name: Provider-secret isolation expected
    runs-on: ubuntu-latest
    env:
      OPENAI_API_KEY: ${{ secrets.SHOULD_NOT_BE_USED }}
    steps:
      - uses: actions/checkout@v4
      - uses: Reguard-Core/reguard@v0.1.0-rc.1
        with:
          reguard-version: 0.1.0rc1
          fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED
        # Expected: ERROR with "env validation failed: forbidden env
        # var 'OPENAI_API_KEY' is set in the harness environment"
```

## Acceptance criteria

The smoke test is a PASS only when:

| Job | Expected outcome |
|---|---|
| `smoke-pass` | `PASS` for `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING` (contract v1.4.0); 4 events; 2 framework artifacts |
| `smoke-provider-secret-blocked` | `ERROR` with reason `env validation failed: forbidden env var 'OPENAI_API_KEY' is set in the harness environment; recipes must not run when a provider key is present` |

Additionally:

- `.reguard/results/<run-id>/result.json` is uploaded as an
  artifact.
- `.reguard/results/<run-id>/summary.md` is rendered in the
  GitHub step summary.
- The action's `outputs.status` equals `PASS` for `smoke-pass`
  and `ERROR` for `smoke-provider-secret-blocked`.

## What this proves

- `pip install reguard==0.1.0rc1` from PyPI installs a working
  wheel.
- The composite action `Reguard-Core/reguard@v0.1.0-rc.1` from
  GitHub resolves.
- The action's `reguard-version` input correctly triggers a
  PyPI install.
- `compliance/` resolves from `site-packages` (not from a local
  source checkout).
- The `fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED` policy fails the
  job when status is in that set.
- The provider-secret isolation works against a real GitHub
  runner environment.

## What this does NOT prove

- Native Windows or native macOS support (tested: NOT yet).
- Non-Linux container runtimes (e.g. Windows containers).
- Compliance with anything beyond Article 12(1) v1.4.0.

## Failure handling

If the smoke fails:

1. Read the action's step summary first.
2. Read `.reguard/results/<run-id>/summary.md`.
3. Read `.reguard/results/<run-id>/result.json`.
4. Read `.reguard/results/<run-id>/evidence.json`.
5. Determine whether the failure is:
   a. **Infrastructure** (PyPI unreachable, GHCR auth): fix the
      publication infrastructure and re-smoke.
   b. **Engine semantics** (wrong status, wrong events): fix in
      source, rebuild, restart from the RC's release-source
      commit, republish, re-smoke.
   c. **Action packaging** (bad install_cmd, missing artifact):
      fix `action.yml`, republish the tag, re-smoke.

Do **NOT** weaken the engine semantics to make the smoke pass.

## RC promotion gate

After at least one consumer-repo RC run PASSes:

- Tag `v0.1.0` from the same release-source commit.
- Publish `reguard==0.1.0` to PyPI.
- Republish the GHCR runtime image at `:0.1.0` and `:latest`.
- Update README and release notes to drop the `-rc.1` suffix.

Do **NOT** publish `v0.1.0` until at least one external consumer
has PASSed a remote smoke against `v0.1.0-rc.1`.

— end of remote consumer smoke plan —