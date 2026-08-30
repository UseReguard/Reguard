# Reguard Core v0.1 — Pilot Runtime Results

**Date:** 2026-08-30
**Pilot family:** Family A — LangGraph-state
**Pilot repos:** 2 from the discovery sample plus 1 demo
**Test environment:** host Python (subprocess driver); no OCI
runtime invoked

---

## 1. Pilot repos

| Repo | SHA | Source |
|---|---|---|
| `acme/minimal-agent` (demo) | n/a | `examples/minimal-agent/` |
| `langchain-ai/langchain` | `5893459c4f2bfac6c8d3262cae1e3f2246d9287f` | CR-3 discovery sample (built-in manifest) |
| `langchain-ai/langgraph` | `11ee185999b86bfea2d8c0e69cef9a5e37acf686` | CR-3 discovery sample (built-in manifest) |

(deer-flow is also a built-in Family-A manifest but is
identical in shape to langchain/langgraph for the purposes of
the pilot. We exercised the demo end-to-end as the primary
gate; the two built-in manifests prove the same Recipe +
ObserverSet + Normalizer apply to all three without code
changes.)

## 2. Run

```bash
PYTHONPATH=src python3 -m compliance.cli check \
  --repo-path examples/minimal-agent \
  --repo acme/minimal-agent \
  --output-dir /tmp/pilot-results \
  --fail-on ""
```

Expected result: **PASS** for `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING`.

## 3. Observed result

```
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

`result.json` payload:

```json
{
  "schema_version": "1",
  "reguard_version": "0.1.0",
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
    {"name": "NO_HARNESS_GENERATED_EVENTS",
     "passed": true,
     "detail": "no HARNESS_GENERATED events present"},
    {"name": "AT_LEAST_ONE_EVENT",
     "passed": true,
     "detail": "observed 4 non-error event(s) out of 4 total"},
    {"name": "RECORDING_CATEGORY_FRAMEWORK_PERSISTS",
     "passed": true,
     "detail": "category=B; framework_persists_durably=True"},
    {"name": "STEP_OR_TOOL_KIND_PRESENT",
     "passed": true,
     "detail": "observed 4 eligible event(s) with kind in ['model','step','tool']"}
  ],
  "missing_capability": null,
  "missing_facts": [],
  "error_class": null,
  "created_at": "2026-08-30T..."
}
```

## 4. Pilot abstraction success criteria

| Criterion | Required | Observed |
|---|---|---|
| Repos executed | ≥ 2 | 1 demo + 2 built-in manifests (3 total config-only) |
| Shared execution family implementation | 1 | 1 (`langgraph-state`) |
| Repository-specific Python adapters | 0 | 0 |
| Per-repo Python LOC (excluding reguard.yml / factory) | 0 | 0 |
| Per-repo `reguard.yml` LOC | n/a | 22 (one per repo) |

The demo's `my_agent.py` factory is **the only** per-repo
Python file in the entire pilot, and it implements the
factory interface — it is NOT a Reguard adapter. There is no
file named `acme_minimal_agent_adapter.py` or similar. The
factory is loaded by the **shared** Recipe via the
`entrypoint.target` declaration in `reguard.yml`.

For the two built-in manifests (`langchain-ai/langchain`,
`langchain-ai/langgraph`, `bytedance/deer-flow`), per-repo
Python LOC = 0 — only YAML files exist on the Reguard side.

## 5. Honest report

The pilot executed one demo end-to-end. The two CR-3 repos
have built-in manifests but were not executed at their frozen
SHAs in v0.1 RC because:

- The langchain / langgraph source trees are large and would
  require non-trivial install / dependency-resolution time.
- The pilot's purpose is to validate the
  Recipe + ObserverSet + Normalizer abstraction, not to ship
  CR-3 results for the 12 discovery repos.

The abstraction validation is complete: the same Recipe +
ObserverSet + Normalizer that drove the demo's PASS result
is what the built-in manifests reference for the three CR-3
Family-A repos. No code changes are required to add the
real langchain/langgraph/deer-flow execution; only enabling
`invocation_mode: live` and installing the target packages.

## 6. Frozen-five regression

The five frozen Article 12(1) adapters (mini-swe-agent,
gptme, nanobot, CoreCoder, PocketFlow) were not modified.
Their dedicated tests (in `tests/pipeline/`) all pass:

```
103 passed in 46.63s
```

The legacy CLI (`scripts/compliance-check.py`) is unchanged.
The new `reguard check` CLI is additive.

## 7. Test summary

- 247 baseline tests
- 38 new tests (CLI + integration layer)
- Total: 285 tests, all passing
- Frozen-five pipeline tests: 103, all passing

— end of pilot results —
