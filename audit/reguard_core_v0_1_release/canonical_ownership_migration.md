# Canonical Ownership Migration — UseReguard/Reguard

**Date:** 2026-08-30
**From:** `Reguard-Core/reguard` (and the prior `m-urculu/Reguard` clone origin)
**To:** `UseReguard/Reguard`
**Scope:** owner identity normalization for v0.1.0rc1 publication

This document records the canonical-owner migration applied in
this phase. Historical audit evidence referencing prior owner
identities is preserved verbatim below — only active public
references were rewritten.

---

## 1. Canonical identity

| Surface | Value |
|---|---|
| GitHub organization | `UseReguard` |
| GitHub repository | `UseReguard/Reguard` |
| Composite Action | `UseReguard/Reguard@v0.1.0-rc.1` |
| PyPI distribution | `reguard` |
| PyPI project URLs | `https://github.com/UseReguard/Reguard`, `https://github.com/UseReguard/Reguard/issues` |
| GHCR namespace | `ghcr.io/usereguard/` |
| Runtime image | `ghcr.io/usereguard/reguard-runtime:0.1.0rc1` |
| Python package version | `0.1.0rc1` |
| Git tag | `v0.1.0-rc.1` |
| License | `AGPL-3.0-only` |

GitHub capitalization is canonicalized to `UseReguard/Reguard`;
GHCR namespaces are lowercase (`usereguard`).

---

## 2. Git remote update

```text
before : https://github.com/m-urculu/Reguard.git
after  : https://github.com/UseReguard/Reguard.git
```

Commands:

```bash
git remote set-url origin https://github.com/UseReguard/Reguard.git
git fetch origin --no-tags
git remote -v
git branch -vv
```

The local `main` is ahead of `origin/main` by one commit (the
release-source commit that landed in the prior phase). The
preparation commit in this phase will close that gap before the
final tag push.

---

## 3. Stale owner references — classification and disposition

A `git grep -nE 'm-urculu|Reguard-Core|reguard-core|UseReguard|github\.com/.*/Reguard|ghcr\.io/'`
across the tracked tree returned the matches below.

### 3.1 PUBLIC_ACTIVE — rewritten

| File | Lines | Reason |
|---|---|---|
| `README.md` | 81, 119 | First-screen examples (clone URL, Action slug) |
| `pyproject.toml` | 45, 46 | `[project.urls]` Repository + Issues |
| `runtime/Dockerfile` | (new labels block) | OCI source/url labels |
| `audit/reguard_core_v0_1_release/rc_release_notes.md` | 63, 86 | User-facing release notes (clone + Action) |
| `audit/reguard_core_v0_1_release/remote_consumer_smoke_plan.md` | 28, 30, 38, 56, 58, 70, 100 | Consumer-facing smoke plan |
| `audit/reguard_core_v0_1_release/release_artifact_manifest.json` | 142 | `oci_runtime_image.public_image_reference_pending` |
| `audit/reguard_core_v0_1_release/publication_runbook.md` | 136, 143, 144, 151, 174, 228, 308 | Release-facing runbook |

### 3.2 HISTORICAL_AUDIT — preserved verbatim

These documents record what was true at a prior point in time.
Rewriting them would destroy the audit trail.

| File | Lines | Reason |
|---|---|---|
| `audit/article_12_1_github_actions_run.md` | 7, 13, 14, 15 | Records prior Actions run URLs (`m-urculu/compliance-tool/actions/runs/...`) — these are immutable external references to past runs |
| `audit/reguard_core_v0_1_release/final_prepublication_report.md` | 581 | Contains `<actual-owner>` placeholder documenting the pre-migration open question |
| `audit/reguard_core_v0_1_release/final_release_gate_report.md` | 99 | Historical release-gate report uses `reguard-core/reguard@v0.1.0` as an example slug |
| `audit/reguard_core_v0_1_release/github_action_clean_room.md` | 151 | Same — historical clean-room example |
| `audit/reguard_core_v0_1_release/pre_publication_correction_report.md` | 77, 78 | Records the prior typo fix `reguard-core` → `reguard` |
| `audit/reguard_core_v0_1_release/public_artifact_inventory.md` | 23, 43 | Historical artifact inventory |
| `audit/reguard_core_v0_1_release/rc_publication_preflight.md` | 52, 56, 198, 199, 235, 244 | Records the pre-migration preflight state (`Reguard-Core/reguard`, `ghcr.io/reguard-core/reguard-runtime`). The summary verdict ("READY") is preserved as the historical record; the actual publication step was stopped cleanly and the new manifest replaces the prior `ghcr.io/reguard-core/reguard-runtime` reference for active publication. |

### 3.3 TEST_FIXTURE / INTERNAL — preserved

| File | Lines | Reason |
|---|---|---|
| `Reguard/Study/Reguard Core v0.1*.md` | 17, 23 | Obsidian note tags containing `reguard-core` are an internal taxonomy tag, not an owner slug |

### 3.4 IRRELEVANT — preserved

| File | Lines | Reason |
|---|---|---|
| `audit/2026-08-28-readmes.json` | 573 | Snippet from a third-party README (`ghcr.io/open-webui/open-terminal`); not a Reguard reference |
| `src/compliance/pipeline/types.py` | 166 | Docstring example `ghcr.io/.../reguard-runtime` — illustrative, not a deployed reference |
| `src/compliance/cli/commands_check.py` | 280, 340 | `runtime_version` field built as `reguard-core/<version>` — this is an internal runtime identifier in `result.json`, not a GitHub/GHCR owner |

---

## 4. PyPI metadata

`pyproject.toml [project.urls]` updated to:

```toml
[project.urls]
Homepage   = "https://github.com/UseReguard/Reguard"
Repository = "https://github.com/UseReguard/Reguard"
Issues     = "https://github.com/UseReguard/Reguard/issues"
```

`name`, `version`, and `license` were not modified (already
canonical).

---

## 5. OCI source metadata

`runtime/Dockerfile` now declares:

```dockerfile
LABEL org.opencontainers.image.title="reguard-runtime" \
      org.opencontainers.image.description="Deterministic runtime probe for Reguard Core technical-control checks." \
      org.opencontainers.image.source="https://github.com/UseReguard/Reguard" \
      org.opencontainers.image.url="https://github.com/UseReguard/Reguard" \
      org.opencontainers.image.vendor="UseReguard" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${REGUARD_SOURCE_REVISION}" \
      org.opencontainers.image.version="${REGUARD_SOURCE_VERSION}"
```

The two revision/version labels are populated by the release
workflow at build time via `--build-arg`:

```text
REGUARD_SOURCE_REVISION = <exact release commit SHA>
REGUARD_SOURCE_VERSION  = <exact release tag, e.g. v0.1.0-rc.1>
```

---

## 6. Active reference rewrite summary

| Surface | Old | New |
|---|---|---|
| README clone URL | `https://github.com/Reguard-Core/reguard` | `https://github.com/UseReguard/Reguard` |
| README Action slug | `Reguard-Core/reguard@v0.1.0-rc.1` | `UseReguard/Reguard@v0.1.0-rc.1` |
| pyproject Repository | `https://github.com/Reguard-Core/reguard` | `https://github.com/UseReguard/Reguard` |
| pyproject Issues | `https://github.com/Reguard-Core/reguard/issues` | `https://github.com/UseReguard/Reguard/issues` |
| GHCR target | `ghcr.io/reguard-core/reguard-runtime` | `ghcr.io/usereguard/reguard-runtime` |
| Runtime image tag (rc1) | `ghcr.io/reguard-core/reguard-runtime:0.1.0rc1` | `ghcr.io/usereguard/reguard-runtime:0.1.0rc1` |
| Runtime Dockerfile source label | (absent) | `org.opencontainers.image.source=https://github.com/UseReguard/Reguard` |

All release-facing audit documents have been updated where the
reference is part of an active instruction. Documents that
record prior state (HISTORICAL_AUDIT) are preserved verbatim.

— end of canonical ownership migration —
