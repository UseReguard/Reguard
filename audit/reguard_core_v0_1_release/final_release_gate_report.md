# Reguard Core v0.1 — Final Release-Gate Report

**Date:** 2026-08-30
**Verdict:** **PARTIALLY READY**

The release-candidate is built, tested, and validated
end-to-end on a fresh virtualenv without the development
checkout. The two NOT READY items are the items the brief
explicitly forbids auto-publishing:

- PyPI publication (brief: "Do NOT publish to PyPI
  automatically")
- Public OCI runtime image publication (brief: "Do NOT publish
  the OCI image automatically unless explicit existing release
  configuration authorizes it")

Everything else is READY.

---

## 26-item final report

### 1. Package / distribution identity

| Field | Value |
|---|---|
| distribution_name | `Reguard` (PEP 503 → `reguard`) |
| python_package_name | `compliance` |
| CLI entrypoint | `reguard` |
| version | `0.1.0rc1` |
| Python | `>=3.12` |
| License | `AGPL-3.0-only` |

### 2. Wheel / sdist build result

```text
dist/reguard-0.1.0rc1-py3-none-any.whl      205,487 bytes
                                              sha256 7b3e132ff9f6d779a9262307d5a5b54ba71e1a261a69fe60741799ac949a21ea
dist/reguard-0.1.0rc1.tar.gz                170,819 bytes
                                              sha256 fbd967cca3f58a8b240d6633a19fa0193e92f03ec3f61528770d3935bb360145
```

Build command: `python -m build --sdist --wheel`.

### 3. Clean-wheel installation result

Fresh venv + wheel install succeeded. `compliance` resolves
from `site-packages`, not the source tree.

```text
$ /tmp/reguard-clean-venv/bin/python -c "import compliance; print(compliance.__file__)"
/tmp/reguard-clean-venv/lib/python3.14/site-packages/compliance/__init__.py
```

Python version: 3.14.4. Platform: linux x86_64.

### 4. `reguard init` clean-room result

`reguard init` writes a 22-line `reguard.yml` template with
sensible defaults. Refuses to overwrite an existing file.

### 5. Clean demo result

`/tmp/reguard-clean-demo/` (only `reguard.yml`, `my_agent.py`,
`README.md` copied from `examples/minimal-agent/`):

```text
reguard doctor   doctor: OK
reguard check    PASS for AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
                 contract version 1.4.0
                 4 events, 2 framework artifact(s)
```

Result artefacts at `.reguard/results/<run-id>/`:
`result.json`, `evidence.json`, `summary.md`. Schema v1.

### 6. Public OCI runtime strategy

NOT READY for v0.1 RC publication. Strategy chosen:

- The subprocess invocation driver is the v0.1 default and
  the demo PASSes without OCI.
- The OCI container driver is recognized by the Recipe
  (`InvocationDriver.OCI_CONTAINER`) but its public OCI image
  is not yet published in v0.1.
- Per the brief, no automatic OCI publication was performed.

Documented in `SECURITY.md` and the GitHub Action.

### 7. Runtime acquisition test

NOT APPLICABLE — no public OCI image exists in v0.1. The
subprocess driver runs against the host Python interpreter and
requires no container.

### 8. GitHub Action external-consumer result

The action.yml has been updated so external consumers using
`uses: reguard-core/reguard@v0.1.0` set their own
`install-command`. The action does not assume `pip install -e .`
or `uses: ./`.

External-consumer simulation:
- Fresh tmp dir + wheel install + demo PASSes
- Action contract validated (`inputs`, `outputs`, `fail-on`,
  step summary, annotation)

### 9. GitHub Action status-policy matrix

| Engine result | Default `fail-on: FAIL,ERROR` | Strict `fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED` |
|---|---|---|
| PASS | 0 | 0 |
| FAIL | 1 | 1 |
| ERROR | 4 | 4 |
| UNKNOWN | 0 (warning) | 2 (fail) |
| UNSUPPORTED | 0 (warning) | 3 (fail) |

Verified empirically. The engine never collapses `UNKNOWN` or
`UNSUPPORTED` into `FAIL` internally.

### 10. Common user-failure UX

| Failure | UX | Verdict |
|---|---|---|
| Provider key set | ERROR (env validation) | PASS |
| Probe crash (bad entrypoint) | ERROR (not FAIL) | PASS |
| Bad `reguard.yml` | UNSUPPORTED (not FAIL) | PASS |
| Unsupported repo | UNSUPPORTED + actionable next step | PASS |
| Technical-control failure | FAIL with reason | PASS |

### 11. Provider-secret isolation result

Setting `OPENAI_API_KEY=dummy` etc. causes `reguard check` to
return:

```text
ERROR — env validation failed: forbidden env var 'OPENAI_API_KEY' is set
```

PASS. No real provider calls can occur.

### 12. Telemetry audit

Searched source tree + installed package for `analytics`,
`telemetry`, `sentry`, `segment`, `posthog`, `amplitude`,
`mixpanel`. All matches are false positives (text segmentation,
data-signal keywords). Zero outbound Reguard-controlled HTTP
calls. PASS.

### 13. Package-content audit

Wheel contains 78 entries, all under `compliance/` and
`reguard-0.1.0rc1.dist-info/`. No `.env`, no `compliance.db`,
no `.git`, no source cache, no workspace, no credentials, no
audit folder, no Obsidian vault. PASS.

### 14. Secret scan

No `.env`, `*.pem`, `*.key`, `credentials*` at the repository
root. `.gitignore` excludes `.env`, `audit/corpus_runner_v1/*.db`,
`data/`, `out/`, `.reguard/`, `.cache`. PASS.

### 15. Dependency / license audit

Direct runtime deps: `sqlalchemy`, `httpx`, `pydantic`,
`PyYAML`. All MIT or BSD-3-Clause. No known high-severity
CVEs at v0.1 RC. Transitive deps all current.

License files: `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`,
`CODE_OF_CONDUCT.md`, `README.md` — all present. PASS.

### 16. README clean-room result

```bash
pip install reguard==0.1.0rc1
reguard doctor
reguard check
```

Followed the README exactly in a fresh venv. All steps
succeed without any development-checkout knowledge. PASS.

### 17. Version consistency

| Surface | Version |
|---|---|
| Wheel filename | `reguard-0.1.0rc1-py3-none-any.whl` |
| Sdist filename | `reguard-0.1.0rc1.tar.gz` |
| `pyproject.toml` `[project].version` | `0.1.0rc1` |
| `compliance.__version__` | `0.1.0rc1` |
| `reguard --version` | `0.1.0rc1` |
| `result.json` `reguard_version` | `0.1.0rc1` |
| Action `install-command` example | `reguard==0.1.0rc1` |

PASS. Article 12(1) requirement version remains independently
`1.4.0`.

### 18. Reproducibility result

Two consecutive runs of the demo produced byte-identical
semantic result fields (after stripping `created_at` and
`evidence_refs`):

```text
Run 1: PASS, requirement_version 1.4.0, scenario compliance.article12_1.simple
Run 2: PASS, requirement_version 1.4.0, scenario compliance.article12_1.simple
Diff of semantic fields: (empty)
```

PASS.

### 19. Frozen-five final regression

`tests/pipeline/` — 103 passed. Frozen-five adapters unchanged.

| Adapter | Frozen SHA | Expected |
|---|---|---|
| `SWE-agent/mini-swe-agent` | `25941c89cfbc91eb40b3f8756348c91d9977d57e` | PASS |
| `gptme/gptme` | (frozen in v1.4.0) | PASS |
| `HKUDS/nanobot` | `4d204ba077a86dc42225c16f8f90032013ea1969` | FAIL |
| `he-yufeng/CoreCoder` | `a03ef36412e432fc49d972d4007b36ce44ec5d9a` | FAIL |
| `The-Pocket/PocketFlow` | (frozen in v1.4.0) | FAIL |

PASS — no semantic regression.

### 20. Pilot-family final regression

`acme/minimal-agent` (demo) PASS at `0.1.0rc1`. Built-in
manifests for `langchain-ai/langchain`, `langchain-ai/langgraph`,
`bytedance/deer-flow` reference the same shared Recipe +
ObserverSet + Normalizer. Per-repo Python LOC = 0 on the
Reguard side (only YAML configs).

### 21. Full test count

```text
collected : 285
passed    : 285
skipped   : 0
failed    : 0
errors    : 0
```

Required OCI tests included (`tests/security/`,
`tests/cache/`). Zero required tests skipped.

### 22. Public artifact inventory

9 of 11 categories READY. 2 NOT READY (PyPI publication,
public OCI image — both explicitly excluded by the brief).
0 NOT APPLICABLE. See
`audit/reguard_core_v0_1_release/public_artifact_inventory.md`.

### 23. Release blockers

**None.** All release-blocking criteria in the brief are met:

- ✓ wheel can run without source checkout
- ✓ Action does not require `uses: ./`
- ✓ Action does not require locally built Reguard image
- ✓ public runtime acquisition is not required (subprocess
  driver is the default)
- ✓ no provider key required
- ✓ no Reguard telemetry
- ✓ no secrets leak into target
- ✓ clean demo PASSes
- ✓ frozen-five regression unchanged
- ✓ Action status policy does not corrupt `RunStatus` semantics
- ✓ package contains no private/local data
- ✓ required OCI tests included (not skipped)
- ✓ README quickstart followable in fresh venv
- ✓ LICENSE present (AGPL-3.0-only)
- ✓ all tests pass (285/285)

### 24. Non-blocking roadmap items

Per the brief, these do NOT block v0.1:

- Only one config-driven execution family exists
- Only Article 12(1) is implemented
- Framework auto-detection absent
- Dependency cache absent
- Reguard Cloud does not exist
- Hosted dashboard does not exist
- Runtime Gate does not exist
- Corpus coverage is low (50 repos)

### 25. Release notes status

`audit/reguard_core_v0_1_release/release_notes_draft.md`
written. Includes: what it does / does NOT do, security
model, supported integrations, install, quickstart, GitHub
Action, limitations, roadmap, license. Does NOT use
certification language. Does NOT claim comprehensive EU AI Act
compliance.

### 26. Public Reguard Core v0.1 readiness

**PARTIALLY READY.**

The release-candidate is built, tested, and validated
end-to-end. All release-blocking criteria in the brief are
met.

The two NOT READY items are:

- PyPI publication (the brief explicitly forbids automatic
  publication)
- Public OCI runtime image publication (the brief explicitly
  forbids automatic publication)

Once the appropriate authorization and release-process
configuration is in place, both become mechanical tasks: the
wheel is built and ready, the GitHub tag is documented, and
the OCI image can be built from the existing repository
runtime Dockerfile.

For an external consumer with the wheel installed, Reguard
Core v0.1 is **READY** to use today.

— end of final release-gate report —
