# Reguard Core v0.1 — Public Artifact Inventory

**Date:** 2026-08-30

Each public artifact is marked READY / NOT READY / NOT
APPLICABLE.

---

## 1. Distribution

| Artefact | Path | Status |
|---|---|---|
| Python wheel | `dist/reguard-0.1.0rc1-py3-none-any.whl` | READY |
| Python sdist | `dist/reguard-0.1.0rc1.tar.gz` | READY |
| PyPI publication | n/a | NOT READY (not yet published; brief says "do NOT publish automatically") |
| Distribution name | `Reguard` (PEP 503 normalized → `reguard`) | READY |

## 2. Runtime image

| Artefact | Status |
|---|---|
| Public OCI runtime image (e.g. `ghcr.io/reguard-core/reguard-runtime:0.1.0-rc.1`) | NOT READY (not yet published; brief says "do NOT publish automatically") |
| Local Docker image (legacy) | NOT APPLICABLE |
| OCI invocation driver | READY (Recipe-side support shipped; not exercised in v0.1) |

The v0.1 RC does NOT block on a public OCI image: the
subprocess driver is the default and the demo PASSes
end-to-end without OCI.

## 3. GitHub Action

| Artefact | Status |
|---|---|
| `action.yml` | READY |
| Composite-action contract | READY |
| Inputs (7) | READY |
| Outputs (7) | READY |
| Step summary | READY |
| Status-policy matrix | READY |
| Provider-key clearing | READY |
| Failure-policy decoupled from engine verdict | READY |
| External consumer (`uses: reguard-core/reguard@v0.1.0`) | READY (with documented `install-command`) |

## 4. Documentation

| Artefact | Status |
|---|---|
| `README.md` | READY |
| `SECURITY.md` | READY |
| `CONTRIBUTING.md` | READY |
| `CODE_OF_CONDUCT.md` | READY |
| `docs/integrations.md` | READY |
| `examples/minimal-agent/README.md` | READY |

## 5. Integration

| Artefact | Status |
|---|---|
| `integrations/langchain-ai__langchain.yml` | READY |
| `integrations/langchain-ai__langgraph.yml` | READY |
| `integrations/bytedance__deer-flow.yml` | READY |
| `examples/minimal-agent/` | READY |

## 6. Result schema

| Artefact | Status |
|---|---|
| `result.json` schema (v1) | READY |
| `evidence.json` schema (v2) | READY |
| `summary.md` template | READY |

## 7. Frozen requirement

| Artefact | Status |
|---|---|
| Article 12(1) v1.4.0 requirement test | READY |
| Five frozen adapters (`mini-swe-agent`, `gptme`, `nanobot`, `CoreCoder`, `PocketFlow`) | READY (unchanged) |

## 8. CLI

| Artefact | Status |
|---|---|
| `reguard --version` | READY |
| `reguard init` | READY |
| `reguard doctor` | READY |
| `reguard check` | READY |
| `reguard explain` | READY |
| `reguard list` | READY |

## 9. Tests

| Artefact | Status |
|---|---|
| Test suite (285 tests) | READY |
| Frozen-five regression (`tests/pipeline/`) | READY (103 passed) |
| Pilot + CLI tests (`tests/integrations/`, `tests/cli/`) | READY (38 passed) |
| Clean-room demo | READY |

## 10. Release-tag strategy

| Tag | Status |
|---|---|
| `v0.1.0-rc.1` (recommended) | NOT READY (not yet pushed; brief says "do NOT push release tags automatically") |
| `0.1.0rc1` (Python packaging) | READY (in wheel + sdist metadata) |

## 11. Summary

Of 11 categories:

- **READY:** 9 (distribution, Action, docs, integration, schema,
  requirement, CLI, tests, release-tag-strategy documented)
- **NOT READY:** 2 (PyPI publication, public OCI image; both
  explicitly excluded by the brief)
- **NOT APPLICABLE:** 0

**No ambiguous release dependencies.** The two NOT READY items
are clearly NOT READY for one reason: the brief forbids
auto-publication.

— end of public artifact inventory —
