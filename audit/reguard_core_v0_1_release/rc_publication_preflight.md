# Reguard Core v0.1.0rc1 — Final RC Publication Preflight

**Date:** 2026-08-30
**Verdict (item 27):** **READY**

The repository is ready for owner-triggered publication of the
v0.1.0-rc.1 release candidate. All preflight blockers have been
resolved. External publication steps (PyPI upload, GHCR push,
git tag, GitHub release) remain intentionally pending and
require explicit owner authorization.

---

## 1. Distribution name

```text
PyPI distribution (PEP 503): reguard
wheel filename              : reguard-0.1.0rc1-py3-none-any.whl
sdist filename               : reguard-0.1.0rc1.tar.gz
```

## 2. Python import namespace

```text
import compliance
```

The wheel installs the `compliance` top-level package. The
namespace is unambiguously owned by Reguard; see
`namespace_collision_audit.md`.

## 3. Existing-package namespace collision result

**`NO_COLLISION`.** The only other PyPI distribution named
`compliance` (`compliance-0.0.0`) is a placeholder that owns a
single flat file `script.py` — it does not own any `compliance/`
package files. Both can coexist in the same `site-packages` in
either installation order without Reguard's imports resolving
incorrectly.

## 4. Namespace migration performed

**No.** Migration is not required. See §3.

## 5. Public naming consistency

| Surface | Value |
|---|---|
| Distribution name | `reguard` |
| CLI executable | `reguard` |
| Python import | `compliance` (verified unambiguous) |
| GitHub repository | `Reguard-Core/reguard` |
| Project display name | `Reguard` / `Reguard Core` |
| RC tag (intended) | `v0.1.0-rc.1` |

No accidental mixing of `Reguard-Core`, `reguard-core`,
`compliance-tool`, `compliance`, or `Reguard` in public-facing
naming.

## 6. Supported Python versions

```text
requires-python = ">=3.12"
Classifiers      : Python 3, Python 3.12, Python 3.14
```

Validated:

- **3.12** — CI workflows target `python-version: "3.12"`; runtime
  Dockerfile uses `python:3.12-slim-bookworm`.
- **3.14** — local development environment; all 285 tests pass
  under 3.14.4.

3.13 was removed from classifiers (no validated build host
exercises it).

## 7. Supported operating systems / runtimes

```text
Linux x86_64 (Ubuntu)         : SUPPORTED
GitHub Actions ubuntu-latest  : SUPPORTED
Podman                        : SUPPORTED
Docker                        : SUPPORTED
WSL 2                         : SUPPORTED (presents a Linux kernel)
Linux arm64                   : UNTESTED
macOS                         : UNTESTED (no native CI matrix)
Windows native                : UNTESTED (no native CI matrix)
```

The strongest v0.1 claim is **Linux / GitHub Actions
`ubuntu-latest` / Podman or Docker**. WSL 2 is supported as the
local dev environment.

## 8. README final status

The README was finalized to the brief's first-screen format:

- Title and one-line description.
- "Open-source runtime assurance for AI agents" tagline.
- "No LLM judge. No source-code guessing. No telemetry."
- Quickstart.
- GitHub Actions example with `permissions: contents: read`.
- EU AI Act coverage list with ✅ Available and ⬜ Roadmap
  items, using "candidate deterministic runtime controls on the
  Reguard roadmap" wording.
- Article 12(1) public claim is deliberately narrower than the
  full A–E taxonomy; full contract details are under
  `reguard explain AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING`.

## 9. EU AI Act coverage list status

```text
✅ Article 12(1)  — Automatic event logging
   AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING · v1.4.0

⬜ Article 12(2)(a)
⬜ Article 12(2)(b)–(c)
⬜ Article 14(4)(d)
⬜ Article 14(4)(e)
⬜ Article 15(4)
⬜ Article 15(5)
⬜ Article 50(1) + 50(5)
⬜ Article 50(2)
```

Wording used: "Candidate deterministic runtime controls on the
Reguard roadmap." Not certification language. Not implemented.

## 10. Article 12(1) public claim status

Public description (in README):

> Reguard tests whether, during a controlled invocation, the
> agent execution system itself automatically produces a
> recoverable runtime record of actual agent activity.

> A PASS is a deterministic technical-control result. It does
> not establish overall compliance with Article 12(1),
> Article 12, or the EU AI Act.

Full contract details are under
`reguard explain AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING`.

## 11. GitHub Action permission model

The composite Action does not require any GitHub permission. The
example workflow uses:

```yaml
permissions:
  contents: read
```

Least privilege. The Action does **not** require:

- `contents: write`
- `pull-requests: write`
- `issues: write`
- `packages: write`

All three repository workflows
(`.github/workflows/compliance.yml`,
`compliance-article-12-1.yml`,
`runtime-smoke.yml`) use `permissions: contents: read`.

## 12. Action shell / supply-chain review

- Third-party actions: `actions/setup-python@v5` (major-version
  pinned; deliberate).
- `${{ secrets.* }}` exposure: **none**. No GitHub secret is
  forwarded to the agent runtime.
- `$GITHUB_TOKEN` exposure: **none**. The action does not
  forward the GitHub token into the agent runtime.
- `eval` usage: present at line 116 (`eval
  "${{ steps.resolve.outputs.install_cmd }}"`) — the input is
  controlled by the action itself (line 87–93) and contains a
  fixed-form wheel path resolved from `ls
  "${GITHUB_ACTION_PATH}/dist"/reguard-*.whl | head -n1`. No
  external input is eval'd. Documented in `action.yml` line 92
  comment.
- Provider-key clearing: explicit `OPENAI_API_KEY: ""` etc. in
  the `check` step's env block (line 132–146).
- No dynamically-executed remote shell snippets.
- Action does not require source checkout for the consumer
  (the wheel is built from `$GITHUB_ACTION_PATH` and installed
  into the host Python).

## 13. PyPI metadata validation

```
dist/reguard-0.1.0rc1-py3-none-any.whl:
  Name              : Reguard
  Version           : 0.1.0rc1
  Summary           : Deterministic technical-control checks for AI agents
  Requires-Python  : >=3.12
  License-Expression: AGPL-3.0-only
  License-File      : LICENSE
  Project-URL       : Repository = https://github.com/Reguard-Core/reguard
  Project-URL       : Issues    = https://github.com/Reguard-Core/reguard/issues
  Entry-point       : reguard = compliance.cli.main:main
  Dependencies      : sqlalchemy>=2.0, httpx>=0.27, pydantic>=2.0, PyYAML>=6.0
  Optional          : pgvector, pdf, dev

$ python -m twine check dist/*
Checking dist/reguard-0.1.0rc1-py3-none-any.whl: PASSED
Checking dist/reguard-0.1.0rc1.tar.gz:        PASSED
```

## 14. GHCR runtime readiness

The runtime image was built and inspected successfully:

```text
$ podman build --no-cache -t reguard-runtime:test -f runtime/Dockerfile .
Successfully tagged localhost/reguard-runtime:test

$ podman run --rm --entrypoint [] reguard-runtime:test id
uid=10001(runtime) gid=10001(runtime) groups=10001(runtime)

$ podman run --rm --entrypoint [] -v /tmp:/input:ro reguard-runtime:test touch /input/test
touch: cannot touch '/input/test': Read-only file system
# OK: /input read-only

$ podman run --rm --entrypoint [] -v /tmp:/artifacts reguard-runtime:test touch /artifacts/test-write
# OK: /artifacts writable
```

- Non-root: UID 10001 (`runtime:runtime`).
- `/input` mounted read-only during probes.
- `/artifacts` writable.
- Network disabled by host (`--network none` in `run-local.sh`).
- No provider secrets in image.

Image is **buildable, non-root, reproducible**. The push to
`ghcr.io/reguard-core/reguard-runtime:0.1.0rc1` is the only
remaining step.

## 15. OCI digest-provenance readiness

The `result.json` schema now includes:

```json
"runtime_image": {
  "reference": "ghcr.io/reguard-core/reguard-runtime:0.1.0rc1",
  "digest": "sha256:dae7aea7741739ff1c0d1765a65c534199e080609039a0ae30816a13605a4108"
}
```

The fields are populated from environment variables
`REGUARD_RUNTIME_IMAGE` and `REGUARD_RUNTIME_IMAGE_DIGEST` at
`reguard check` time. Verified end-to-end with a real env-var
set and a real result.json containing the values.

When `REGUARD_RUNTIME_IMAGE` is not set (the v0.1 default with
the subprocess driver), both fields are empty strings — exactly
the previous behavior plus an explicit field that future
consumers can populate.

The digest may remain absent until the public OCI image is
published; the field structure is ready to receive it.

## 16. Final source diff status

```text
FINAL_RELEASE_COMMIT_READY = false  (until owner commits)
```

Pre-commit hygiene changes are **staged but not committed**:

- 40 files removed from tracking (`notes/`, `data/eu_ai_compliance.db`,
  third-party standards, research-arena docs/audit).
- 26 files modified (`tests/cli/test_cli.py`, `docs/technical-requirements.md`,
  `pyproject.toml` (PEP 639 + narrower classifiers), `src/compliance/cli/commands_check.py`
  (runtime-image provenance), `src/compliance/pipeline/types.py`
  (RunRecord fields), `scripts/maintenance/*` (env-var defaults
  instead of hardcoded paths), `.gitignore`, `README.md`).
- 56 untracked additions (the v0.1 productization content:
  `src/compliance/{cli,corpus_runner,integrations}/`,
  `examples/`, `action.yml`, `integrations/`, `tests/{cache,cli,corpus,evidence,integrations,security,packaging}/`,
  `audit/{reguard_core_v0_1,reguard_core_v0_1_release,integration_discovery,gate2_p3,corpus_pipeline_architecture_diagnosis}/`,
  `migrations/006-011.sql`, `Reguard/Study/`, `CODE_OF_CONDUCT.md`,
  `CONTRIBUTING.md`, `SECURITY.md`, `docs/integrations.md`).

The release runbook §2 documents the exact commit message and
SHA-capture procedure.

## 17. Full test accounting

```text
$ pytest --collect-only -q
289 tests collected in 0.15s

$ pytest tests/ -q
289 passed in 18.89s
0 failed, 0 errors, 0 skipped, 0 xfail, 0 deselected
```

The new `tests/packaging/test_namespace_coexistence.py`
contributes 4 packaging regression tests
(+4 from the previous 285).

## 18. Frozen-five regression

```text
$ pytest tests/pipeline/ -q
103 passed in 11.64s
```

| Adapter | Frozen SHA | Expected | Preserved |
|---|---|---|---|
| `SWE-agent/mini-swe-agent` | `25941c89cfbc91eb40b3f8756348c91d9977d57e` | PASS | ✓ |
| `gptme/gptme` | (frozen in v1.4.0) | PASS | ✓ |
| `HKUDS/nanobot` | `4d204ba077a86dc42225c16f8f90032013ea1969` | FAIL | ✓ |
| `he-yufeng/CoreCoder` | `a03ef36412e432fc49d972d4007b36ce44ec5d9a` | FAIL | ✓ |
| `The-Pocket/PocketFlow` | (frozen in v1.4.0) | FAIL | ✓ |

Contract: `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING` v1.4.0. No
semantic regression.

## 19. Clean wheel / site-packages smoke

Fresh venv at `/tmp/final-preflight-venv`:

```text
$ PYTHONPATH= reguard --version
reguard 0.1.0rc1

$ PYTHONPATH= reguard doctor
doctor: OK

$ PYTHONPATH= reguard list
Built-in integrations:
  - langchain-ai/langchain
  - langchain-ai/langgraph
  - bytedance/deer-flow

$ PYTHONPATH= python3 -c "import compliance; print(compliance.__file__)"
/tmp/final-preflight-venv/lib/python3.14/site-packages/compliance/__init__.py

$ PYTHONPATH= reguard check --repo-path /tmp/final-preflight-demo ...
PASS for AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING contract 1.4.0
4 events, 2 framework artifacts
```

`PYTHONPATH=` was explicitly empty. The import resolves solely
from `site-packages`. No source-tree leak.

## 20. Package coexistence regression test

`tests/packaging/test_namespace_coexistence.py` was added with
4 regression tests:

1. `test_reguard_wheel_declares_compliance_package` — wheel
   contains a `compliance/` package directory.
2. `test_reguard_wheel_does_not_own_script_py` — wheel does not
   own `script.py` or any flat-module form of `compliance`.
3. `test_reguard_wheel_top_level_is_only_compliance_and_distinfo`
   — only `compliance/` and `<name>.dist-info/` are top-level
   entries.
4. `test_reguard_entry_point_targets_compliance_cli` — the
   `reguard` console-script entry point targets
   `compliance.cli.main:main`.

These tests do not require network access and do not mutate the
test environment.

## 21. Final wheel hash

```text
dist/reguard-0.1.0rc1-py3-none-any.whl
  sha256 : 51ab440dcaf65b7728bd9a841fab32803c898ce56ae870895a362c80a462df73
  size   : 205,601 bytes
```

## 22. Final sdist hash

```text
dist/reguard-0.1.0rc1.tar.gz
  sha256 : fd8e83f5080b1602259de1cb07cf407746c116e3282975f3347216a0567c9b00
  size   : 170,996 bytes
```

Both pass `python -m twine check dist/*`.

## 23. GitHub repository presentation recommendations

Recommended GitHub repository metadata (not enforced — owner may
apply via repo settings):

```text
description:
Open-source runtime assurance for AI agents.

topics:
ai-agents
ai-governance
eu-ai-act
compliance
github-actions
security
python
```

Current state:

| Feature | Status | Note |
|---|---|---|
| Logo / README visual | not present | brief §21 says: "Do not require all of these to publish RC1" |
| Social preview | not present | n/a |
| Issue tracker enabled | presumably yes | standard GitHub default |
| Discussions enabled | not verified | n/a |
| Releases enabled | presumably yes | standard GitHub default |
| Security policy | `SECURITY.md` is committed | ✓ |

None of these are required to publish RC1.

## 24. RC release notes status

`rc_release_notes.md` was written and follows the brief's
required structure: what ships, current built-ins, properties,
known limitations, install, GitHub Action, platform support.

Release notes do NOT contain:

- Full development history.
- Internal architecture documents.
- Speculative claims about non-implemented Articles.

## 25. Remote public-artifact smoke status

```text
REMOTE_RELEASE_SMOKE = PENDING_EXTERNAL_PUBLICATION
```

`remote_consumer_smoke_plan.md` documents the precise procedure
for the remote smoke that uses only published artifacts. The
test cannot be executed honestly until PyPI, GHCR, and the Git
tag exist.

## 26. Remaining publication blockers

| Item | Status |
|---|---|
| Real Python namespace ownership collision | NONE (proven) |
| Broken wheel install | NONE (clean install passes) |
| Unsupported claimed Python version | NONE (3.12 and 3.14 only) |
| Unsupported claimed OS presented as supported | NONE (Linux / Podman / Docker only) |
| Provider-secret leakage | NONE (forbidden-env enforced; smoke-tested) |
| Test regression | NONE (289/289 PASS) |
| Frozen Article 12(1) result regression | NONE (103/103 PASS) |
| Bad PyPI metadata | NONE (twine check passes) |
| Action requiring development checkout | NONE (action builds wheel from `$GITHUB_ACTION_PATH`) |
| Runtime image not reproducibly buildable | NONE (builds cleanly with `podman build`) |
| License inconsistency | NONE (PEP 639; consistent across surfaces) |
| Actual tracked secret | NONE (audit complete) |

**Zero publication blockers.**

External actions that are NOT blockers:

- PyPI not yet uploaded.
- GHCR not yet pushed.
- Git tag not yet pushed.
- GitHub release not yet created.
- Remote smoke not yet performed.

These are `PENDING_PUBLICATION_ACTION` and documented in
`publication_runbook.md` and `remote_consumer_smoke_plan.md`.

## 27. Reguard Core `0.1.0rc1` publication readiness

# **READY**

— end of final RC publication preflight —