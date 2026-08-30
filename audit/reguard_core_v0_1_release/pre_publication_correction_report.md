# Reguard Core v0.1 — Pre-Publication Correction Report

**Date:** 2026-08-30
**Scope:** Final correction pass on Reguard Core v0.1.0rc1 after the
prior release-gate. Fixes PEP 639 license metadata, stale `.[yaml]`
doc references, the wrong repo URL, and an action.yml install-command
defect discovered during external-consumer simulation. Re-validates
clean-room install, frozen-five regression, telemetry/secret audits,
and an external-action smoke test.

## Headline result

**READY** (with the same two brief-forbidden publication steps still
explicitly excluded: PyPI and public OCI image).

| Item | Status |
|---|---|
| PEP 639 license metadata | READY (License-Expression + License-File) |
| Stale `.[yaml]` / wrong repo URL doc references | READY (fixed in README) |
| Composite action for external consumers | READY (with one install-cmd fix below) |
| External-action smoke test | READY (consumer dir is separate, install resolves from site-packages, demo PASS) |
| Clean-room wheel install in fresh venv | READY |
| Frozen-five regression | READY (103/103 in `tests/pipeline/`) |
| Full test suite | READY (285/285) |
| Telemetry + secret audits | READY (zero telemetry, forbidden-env enforced) |
| PyPI publication | NOT READY (brief forbids auto-publish) |
| Public OCI image publication | NOT READY (brief forbids auto-publish) |

## What changed since the prior release-gate report

### 1. PEP 639 license metadata migration

`pyproject.toml` now declares the license via PEP 639 syntax:

```toml
[project]
license = "AGPL-3.0-only"

[build-system]
requires = ["setuptools>=77", "wheel"]

[tool.setuptools]
license-files = ["LICENSE"]
```

The legacy `"License :: OSI Approved :: ..."` classifier was
**removed** — PEP 639 supersedes it and `setuptools>=77` errors
out if both are present.

Wheel `METADATA` now contains:

```
License-Expression: AGPL-3.0-only
License-File: LICENSE
```

`License-File: LICENSE` is the PEP 639 way to embed the license
text; the file lives at `reguard-0.1.0rc1.dist-info/licenses/LICENSE`
(35,331 bytes).

Verified:

```bash
$ python -c "import zipfile; z=zipfile.ZipFile('dist/reguard-0.1.0rc1-py3-none-any.whl');
... print(z.read('reguard-0.1.0rc1.dist-info/METADATA').decode())" | grep -E 'License-(Expression|File)'
License-Expression: AGPL-3.0-only
License-File: LICENSE
$ # Has License classifier: False (correctly absent)
```

`python -m twine check dist/*` passes for both wheel and sdist.

### 2. Stale doc references fixed

- README quickstart: `pip install -e ".[yaml]"` →
  `pip install reguard==0.1.0rc1`
- README repo URL: `https://github.com/Reguard-Core/reguard-core` →
  `https://github.com/Reguard-Core/reguard` (matches
  `pyproject.toml [project.urls].Repository`)

### 3. action.yml rewritten for external-consumer use

The composite action's "resolve install source" step now:

1. Resolves the wheel path with `ls ... | head -n1` so the glob
   expands **at the resolve step** rather than at the eval'd
   install step.
2. Emits the exact wheel path into `$GITHUB_OUTPUT` as
   `install_cmd=python -m pip install <wheel>`.

The previously stored install command used the literal
`${GITHUB_ACTION_PATH}/dist/reguard-*.whl` pattern. When the install
step ran `eval "$install_cmd"`, the eval'd command expanded the
env-var but the bash glob inside the double-quoted string did **not**
re-expand. The literal `*` was passed to pip, which then failed
with `ERROR: Invalid wheel filename (wrong number of parts):
'reguard-.*'`.

The fix is documented inline in `action.yml`:

```
# Resolve the wheel path NOW (shell glob expands here, not at
# eval time). Globbing inside an eval'd command does NOT happen
# reliably across runners; emit the exact filename so pip never
# sees a literal `*`.
```

In addition, the `pip_index` branch now uses
`python -m pip install reguard==<version>` (matching the
`build_from_source` branch) for consistency.

### 4. Fresh rebuild

```text
dist/reguard-0.1.0rc1-py3-none-any.whl      205,601 bytes
                                              sha256 457bc18f2d01f0d2f5757d63c024063598eaa9471106c4ec218e6d58092e2646
dist/reguard-0.1.0rc1.tar.gz                170,996 bytes
                                              sha256 979ee1b3db16c9bef480e4c2029480f166782c5c2ab19b8b08856888e481f2bc
```

`twine check` PASS for both.

### 5. External-action smoke test

Since GitHub-hosted execution cannot be reproduced locally, the
action was simulated in a way that mirrors the runtime separation
between the consumer workspace and the action checkout:

| Variable | Real GitHub | Local simulation |
|---|---|---|
| `GITHUB_WORKSPACE` | consumer repo | `/tmp/reguard-consumer-test` |
| `GITHUB_ACTION_PATH` | action checkout | `/tmp/reguard-action-dir` |
| Workspace content | consumer-only | `reguard.yml`, `my_agent.py`, `README.md` |
| Action checkout content | full Reguard source | full Reguard source |
| Shell | `bash --noprofile --norc -eo pipefail` | identical flags |

Both directories were created outside the Reguard repository
(`/tmp/...`); no source-tree path leaked into the installed
package:

```text
$ python -c "import compliance; print(compliance.__file__)"
/tmp/reguard-action-venv/lib/python3.14/site-packages/compliance/__init__.py
$ python -c "import importlib.util; print(importlib.util.find_spec('compliance.cli.main').origin)"
/tmp/reguard-action-venv/lib/python3.14/site-packages/compliance/cli/main.py
```

Both files resolve from `/tmp/reguard-action-venv/lib/...` (the
fresh virtualenv), never from `/tmp/reguard-action-dir/src/...`
or `/home/mrcel/projects/business/compliance-tool/...`.

Smoke-test results:

| Step | Result |
|---|---|
| `reguard --version` | `reguard 0.1.0rc1` |
| `reguard doctor --repo-path <consumer>` | `doctor: OK` |
| `reguard check --repo-path <consumer>` | PASS for AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING (contract 1.4.0) — 4 events, 2 framework artifacts |
| `OPENAI_API_KEY=...` set in harness | ERROR with `env validation failed: forbidden env var 'OPENAI_API_KEY' is set in the harness environment` |
| Result artefact | `/tmp/reguard-consumer-test/.reguard/results/<run-id>/{result.json,evidence.json,summary.md}` |

### 6. Status-policy matrix (re-verified)

The post-check `Apply CI failure policy` step uses the exact same
case-pattern as the prior release-gate:

| Engine status | Default `fail-on: FAIL,ERROR` | Strict `fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED` |
|---|---|---|
| PASS | 0 | 0 |
| FAIL | 1 | 1 |
| ERROR | 1 | 1 |
| UNKNOWN | 0 | 1 |
| UNSUPPORTED | 0 | 1 |

All 10 combinations PASS. The engine never collapses `UNKNOWN` or
`UNSUPPORTED` into `FAIL` internally; `--fail-on` is CI policy only.

### 7. Clean-room install in fresh venv (re-verified)

```bash
rm -rf /tmp/reguard-verify-venv2
python3 -m venv /tmp/reguard-verify-venv2
/tmp/reguard-verify-venv2/bin/pip install /home/mrcel/projects/business/compliance-tool/dist/reguard-0.1.0rc1-py3-none-any.whl
/tmp/reguard-verify-venv2/bin/reguard --version    # → reguard 0.1.0rc1
/tmp/reguard-verify-venv2/bin/reguard doctor       # → doctor: OK
```

`compliance.__file__` resolves from
`/tmp/reguard-verify-venv2/lib/python3.14/site-packages/compliance/__init__.py`.

### 8. Frozen-five regression (re-verified)

```text
$ python -m pytest tests/pipeline/ -q --no-header
........................................................................ [ 69%]
...............................                                          [100%]
103 passed in 20.08s
```

mini-swe-agent / gptme / nanobot / CoreCoder / PocketFlow — all
expected verdicts preserved. Article 12(1) semantics unchanged.

### 9. Full regression (re-verified)

```text
$ python -m pytest tests/ -q --no-header
........................................................................ [ 25%]
........................................................................ [ 50%]
........................................................................ [ 75%]
.....................................................................    [100%]
285 passed in 33.74s
```

### 10. Telemetry + secret audits (re-verified)

- Zero telemetry calls in source or installed package.
- Zero Reguard-controlled outbound HTTP.
- Forbidden-env allow-list enforced (`OPENAI_API_KEY` etc.
  trigger `ERROR`).
- Composite action clears provider keys before running
  `reguard check`.
- No `.env`, `compliance.db`, `.git`, credentials, audit/, or
  Obsidian vault in the wheel (78 RECORD entries, all under
  `compliance/` and `reguard-0.1.0rc1.dist-info/`).

## Distribution identity (final)

| Field | Value |
|---|---|
| `distribution_name` | `Reguard` (PEP 503 → `reguard`) |
| `python_package_name` | `compliance` |
| CLI entrypoint | `reguard` |
| Version | `0.1.0rc1` |
| Python | `>=3.12` |
| License | `AGPL-3.0-only` (PEP 639) |

## Hashes (final)

```text
dist/reguard-0.1.0rc1-py3-none-any.whl
  sha256 : 457bc18f2d01f0d2f5757d63c024063598eaa9471106c4ec218e6d58092e2646
  size   : 205,601 bytes

dist/reguard-0.1.0rc1.tar.gz
  sha256 : 979ee1b3db16c9bef480e4c2029480f166782c5c2ab19b8b08856888e481f2bc
  size   : 170,996 bytes
```

## Hard constraints honoured (verbatim)

- Did NOT run another corpus scale gate.
- Did NOT start Article 12(2).
- Did NOT change Article 12(1) semantics.
- Did NOT add production adapters.
- Did NOT implement framework-family auto-detection.
- Did NOT optimize PASS rate.
- Did NOT issue compliance verdicts for newly inspected
  repositories.
- Did NOT modify third-party repositories.
- Did NOT change the runtime security boundary.
- Did NOT publish to PyPI.
- Did NOT push a Git tag.
- Did NOT create a GitHub release.
- Did NOT publish an OCI image.

## Authorized artefacts (this pass)

- `pyproject.toml` — PEP 639 migration
- `README.md` — `.[yaml]` and repo URL fixes
- `action.yml` — install-cmd glob fix + external-consumer rewrite
- `dist/reguard-0.1.0rc1-py3-none-any.whl` — rebuilt
- `dist/reguard-0.1.0rc1.tar.gz` — rebuilt
- `audit/reguard_core_v0_1_release/pre_publication_correction_report.md`
  — this report

## Final verdict

**READY** for external-consumer use. All release-blocking criteria
from the brief are met. The two NOT READY items (PyPI publication,
public OCI image publication) are explicitly forbidden by the
brief and require explicit release-process authorisation before
they can be carried out.

— end of pre-publication correction report —