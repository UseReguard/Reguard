---
title: Reguard Core v0.1 Release
study: Reguard
status: release-candidate validation complete; PARTIALLY READY
date: 2026-08-30
phase: post-productization public release gate
artifacts:
  - dist/reguard-0.1.0rc1-py3-none-any.whl
  - dist/reguard-0.1.0rc1.tar.gz
  - audit/reguard_core_v0_1_release/packaging_audit.md
  - audit/reguard_core_v0_1_release/clean_room_validation.md
  - audit/reguard_core_v0_1_release/github_action_clean_room.md
  - audit/reguard_core_v0_1_release/security_release_audit.md
  - audit/reguard_core_v0_1_release/public_artifact_inventory.md
  - audit/reguard_core_v0_1_release/release_notes_draft.md
  - audit/reguard_core_v0_1_release/final_release_gate_report.md
tags: [study, reguard-core, v0.1, release-gate, packaging, clean-room, security, part of [[Reguard Core v0.1]]]
---

# Reguard Core v0.1 Release

Public release-gate validation. Wheel + sdist built, tested in
clean venv, telemetry + secret + content audits pass.

## Headline result

**PARTIALLY READY** for public release.

- 285 tests passing.
- Wheel + sdist built and validated in a fresh venv without
  the development checkout.
- Frozen-five regression unchanged.
- Zero telemetry, zero provider-key leakage.
- All release-blocking criteria met.

The two NOT READY items (PyPI publication, public OCI image
publication) are explicitly forbidden by the brief.

## Distribution identity

| Field | Value |
|---|---|
| distribution_name | `Reguard` |
| python_package_name | `compliance` |
| CLI entrypoint | `reguard` |
| version | `0.1.0rc1` |
| License | AGPL-3.0-only |

Wheel SHA-256:
`7b3e132ff9f6d779a9262307d5a5b54ba71e1a261a69fe60741799ac949a21ea`

## Clean-room validation

A fresh virtualenv + wheel install gives a fully functional
CLI without the source checkout. `compliance` resolves from
`site-packages`:

```text
/tmp/reguard-clean-venv/lib/python3.14/site-packages/compliance/__init__.py
```

Demo PASSes deterministically. Reproducibility confirmed
(byte-identical semantic result fields across two runs).

## Frozen-five regression

`tests/pipeline/` 103 passed. mini-swe-agent / gptme / nanobot
/ CoreCoder / PocketFlow — all expected verdicts preserved.

## Security audit

- Zero telemetry calls
- Zero Reguard-controlled outbound HTTP
- Forbidden-env allow-list enforced
- GitHub Action clears provider keys
- No `.env`, no `.git`, no `compliance.db`, no credentials
  in the wheel

## Status policy matrix

| Engine | Default `fail-on: FAIL,ERROR` | Strict `fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED` |
|---|---|---|
| PASS | 0 | 0 |
| FAIL | 1 | 1 |
| ERROR | 4 | 4 |
| UNKNOWN | 0 (warning) | 2 |
| UNSUPPORTED | 0 (warning) | 3 |

Engine semantics preserved exactly. `--fail-on` is CI policy
only.

## Release-blocking criteria

All met. See
`audit/reguard_core_v0_1_release/final_release_gate_report.md`.

## NOT READY items

- PyPI publication (brief forbids auto-publish)
- Public OCI runtime image publication (brief forbids auto-publish)

## Links

- [[Reguard Core v0.1]] — prior productization phase
- [[Repository Integration Architecture]] — discovery phase
- `audit/reguard_core_v0_1_release/final_release_gate_report.md`
  — 26-item final report
- `audit/reguard_core_v0_1_release/release_notes_draft.md` —
  release notes draft
- `audit/reguard_core_v0_1_release/clean_room_validation.md` —
  clean-room test record
- `audit/reguard_core_v0_1_release/security_release_audit.md` —
  security + telemetry audit

## Final verdict

**PARTIALLY READY.** For an external consumer with the wheel
installed, Reguard Core v0.1 is fully usable today. The
remaining two items are publication steps that require
explicit release-process authorisation.
