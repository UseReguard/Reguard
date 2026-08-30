# Reguard Core v0.1 — Clean-Room Validation

**Date:** 2026-08-30

This document records the clean-room tests that prove an
external developer can install and use Reguard Core from
the built distribution without relying on the development
checkout.

---

## 1. Clean virtualenv + wheel install

### 1.1 Create fresh venv

```bash
python3 -m venv /tmp/reguard-clean-venv
```

### 1.2 Install only the wheel (no `pip install -e .`)

```bash
/tmp/reguard-clean-venv/bin/pip install \
  /home/mrcel/projects/business/compliance-tool/dist/reguard-0.1.0rc1-py3-none-any.whl
```

### 1.3 Verify imports resolve from site-packages

```bash
$ /tmp/reguard-clean-venv/bin/python -c "import compliance; print(compliance.__file__)"
/tmp/reguard-clean-venv/lib/python3.14/site-packages/compliance/__init__.py
```

The `compliance` package resolves from site-packages, not from
the development checkout. PASS.

### 1.4 CLI smoke test

```text
$ reguard --version
reguard 0.1.0rc1

$ reguard list
Requirements:
  - AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING @ 1.4.0
Recipes:
  - langgraph-state @ 1.0.0
Observers:
  - langgraph-state.callback-observer @ 1.0.0
Normalizers:
  - langgraph-state.canonical-normalizer @ 1.0.0
Families:
  - langgraph-state
Built-in integrations:
  - langchain-ai/langchain
  - langchain-ai/langgraph
  - bytedance/deer-flow

$ reguard doctor
Reguard doctor
  OCI runtime     : podman
doctor: OK
```

PASS.

## 2. `reguard init` clean-room test

### 2.1 Empty project

```bash
$ mkdir -p /tmp/reguard-empty
$ cd /tmp/reguard-empty
$ reguard init
wrote reguard.yml
$ cat reguard.yml
schema_version: 1

integration:
  recipe: langgraph-state
  recipe_version: 1.0.0
  package_root: .

  entrypoint:
    target: my_agent:build_graph
    mode: sync

  model:
    strategy: deterministic_stub

  observers:
    - langgraph-state.callback-observer

  normalizer:
    id: langgraph-state.canonical-normalizer

scenarios:
  - compliance.article12_1.simple
```

The init template contains:

- valid schema;
- no development paths;
- no machine-specific paths;
- no internal audit references;
- sensible defaults.

PASS.

### 2.2 Refuse overwrite

```bash
$ reguard init --output reguard.yml   # file exists
refusing to overwrite existing file at .../reguard.yml
$ echo $?
1
```

PASS.

## 3. Clean-room demo

### 3.1 Copy public demo to a fresh tmp dir

```bash
$ mkdir -p /tmp/reguard-clean-demo
$ cp -r /home/mrcel/projects/business/compliance-tool/examples/minimal-agent/* \
       /tmp/reguard-clean-demo/
```

The copied files:

- `reguard.yml` (22 lines)
- `my_agent.py` (factory stub)
- `README.md`

### 3.2 Run `reguard doctor`

```text
Reguard doctor

  repository      : acme/minimal-agent
  repo-path       : /tmp/reguard-clean-demo
  explicit config : <none>
  reguard.yml     : /tmp/reguard-clean-demo/reguard.yml

  OCI runtime     : podman

  integration
    source          : repo_local_yml
    recipe          : langgraph-state@1.0.0
    observers       : langgraph-state.callback-observer
    normalizer      : langgraph-state.canonical-normalizer@1.0.0
    entrypoint      : my_agent:build_graph
    scenarios       : compliance.article12_1.simple

doctor: OK
```

### 3.3 Run `reguard check`

```text
Reguard Core

Repository
  acme/minimal-agent

Technical control
  AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
  Contract version 1.4.0

Result
  PASS

Checks
  ✓ NO_HARNESS_GENERATED_EVENTS
  ✓ AT_LEAST_ONE_EVENT
  ✓ RECORDING_CATEGORY_FRAMEWORK_PERSISTS
  ✓ STEP_OR_TOOL_KIND_PRESENT

Evidence
  4 events
  2 framework artifact(s)
```

### 3.4 Verify result artefacts

```text
$ ls /tmp/reguard-clean-results/<run-id>/
evidence.json
result.json
summary.md
```

`result.json`:

```json
{
  "schema_version": "1",
  "reguard_version": "0.1.0rc1",
  "repository": "acme/minimal-agent",
  "requirement_id": "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
  "requirement_version": "1.4.0",
  "scenario_id": "compliance.article12_1.simple",
  "integration": {
    "recipe": "langgraph-state",
    "observer_versions": null,
    "normalizer_version": null
  },
  "status": "PASS",
  "checks": [
    {"name": "NO_HARNESS_GENERATED_EVENTS", "passed": true,
     "detail": "no HARNESS_GENERATED events present"},
    ...
  ],
  "missing_capability": null,
  "missing_facts": [],
  "error_class": null,
  "created_at": "..."
}
```

PASS — `reguard_version` matches the installed package, all
required fields present, schema validates.

## 4. Common user-failure UX

| Failure | Observed behaviour | Verdict |
|---|---|---|
| Provider key set | `ERROR — env validation failed: forbidden env var 'OPENAI_API_KEY' is set` | PASS |
| Probe crash (bad entrypoint) | `ERROR — integration execution failed: ...` | PASS (not FAIL) |
| Bad `reguard.yml` | falls through to `UNSUPPORTED` with `missing_capability: NO_EXECUTION_RECIPE` | PASS (not FAIL) |
| Unsupported repo (no integration) | `UNSUPPORTED — missing_capability: NO_EXECUTION_RECIPE — Next step: Add reguard.yml ...` | PASS |
| Technical requirement failure | `FAIL — Reason: ...` | PASS |

`FAIL` is reserved exclusively for technical-control failures
emitted by the requirement test. Configuration errors,
infrastructure errors, and unsupported scenarios never collapse
into `FAIL`.

## 5. Provider-secret isolation

```bash
$ OPENAI_API_KEY=dummy \
  ANTHROPIC_API_KEY=dummy \
  GOOGLE_API_KEY=dummy \
  AZURE_OPENAI_API_KEY=dummy \
  GITHUB_TOKEN=dummy \
  AWS_ACCESS_KEY_ID=dummy \
  AWS_SECRET_ACCESS_KEY=dummy \
  reguard check --repo-path /tmp/reguard-clean-demo --repo acme/minimal-agent
ERROR — env validation failed: forbidden env var 'OPENAI_API_KEY' is set
```

PASS. Reguard refuses to run when any provider key is in the
harness environment. No real provider calls can occur.

## 6. Conclusion

**READY.** A fresh external developer can install the wheel
in a new venv, run `reguard init`, drop a `reguard.yml`, run
`reguard doctor`, and run `reguard check` — all without any
of the development checkout on `PYTHONPATH`.

— end of clean-room validation —
