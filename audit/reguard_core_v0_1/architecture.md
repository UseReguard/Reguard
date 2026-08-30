# Reguard Core v0.1 — Architecture

**Date:** 2026-08-30
**Phase:** v0.1 productization (post-discovery)
**Status:** Release-candidate validation

---

## 1. Goal

Convert the integration-pattern discovery READY verdict
(`audit/integration_discovery/final_25_item_report.md`) into a
shippable Reguard Core v0.1 release candidate that:

- Implements the three-abstraction integration model
  (`ExecutionRecipe` + `ObserverSet` + `Normalizer`) as
  first-class reusable components
- Ships a polished top-level CLI (`reguard init/doctor/check/
  explain/list`)
- Ships a reusable GitHub Action
- Includes a deterministic no-network demo
- Includes versioned result and `reguard.yml` schemas
- Preserves the frozen Article 12(1) v1.4.0 contract and the
  five frozen adapters unchanged
- Is local-first, open-source, telemetry-free, key-free

## 2. Three-abstraction model

The integration layer in `src/compliance/integrations/` exposes
three protocols and three registries:

### 2.1 `ExecutionRecipe`

A named, versioned Python class. Each recipe declares:

- `recipe_id`, `recipe_version`
- `supported_scenarios`
- A `resolve(RecipeConfig) → RecipeResolution` step
- A `run(RecipeResolution, Scenario) → opaque_output` step
  that the ObserverSet consumes

The recipe contains NO Article-number logic. It does NOT
return PASS/FAIL. It does NOT invent events. It only drives
the target framework with a deterministic stub model.

### 2.2 `ObserverSet`

A named, versioned Python class that:

- `prepare(context)` — attach to the framework
- `observe(context)` — return observations so far
- `finalize(context)` — tear down

Observers emit `NativeObservation` records with a free-form
`producer` string that the Normalizer maps to a canonical
`EvidenceOrigin`. Observers never decide provenance eligibility.

### 2.3 `Normalizer`

A named, versioned Python class that:

- `normalize(observations, *, recipe_id, recipe_version) → NormalizerResult`
- Translates native observations into canonical Reguard event
  dicts (each with `kind`, `origin`, `ts`, `name`, `content`)
- Computes `framework_persists_durably`,
  `framework_artifact_paths`, `harness_artifact_paths`
- Computes the A/B/C/D/E `recording_category` for the
  requirement test to consume

Normalizers never return PASS/FAIL. They never invent events.

## 3. Pilot family — langgraph-state

**Why Family A (LangGraph-state)?**

| Criterion | Family A |
|---|---|
| ≥ 2 previously UNSUPPORTED repos | 3 (langchain, langgraph, deer-flow) |
| High reuse potential | Single `CompiledStateGraph` shape with checkpointer |
| Deterministic stub-model feasible | In-process fake model already exists in langchain tests; Recipe can wire its own stub |
| Low external-service dependence | Pure Python in-process state graph; persistence opt-in via checkpointer |
| OCI-sandbox compatible | Pure Python |
| Clear runtime observation surface | LangChain `BaseCallbackHandler` and `get_state_history()` |
| Minimal repository-specific code | All three use `create_agent` or `StateGraph().compile()` |

Family B (single-agent toolkit: agentscope, agno) is also
config-only but has slightly more variation between members
and a less mature callback surface. Family A is the safer
first pilot.

## 4. `reguard.yml` schema

Schema version: **1**.

```yaml
schema_version: 1

integration:
  recipe: langgraph-state
  recipe_version: 1.0.0
  package_root: .
  entrypoint:
    target: my_agent:build_graph
    mode: sync
  model:
    strategy: deterministic_stub   # ONLY supported value in v0.1
  observers:
    - langgraph-state.callback-observer
  normalizer:
    id: langgraph-state.canonical-normalizer
  params:
    invocation_mode: live          # or 'dry-run'

scenarios:
  - compliance.article12_1.simple
```

Validation is strict:

- Unknown schema versions → reject
- Unknown recipe / observer / normalizer ids → reject
- Unsupported scenarios → reject
- Provider-key model strategies → reject
- Forbidden env vars present in harness → reject
- Per-repo `params` recipe-specific keys are passed verbatim

## 5. Integration resolution order

`reguard check` resolves a target in this order:

1. `--config <path>` (explicit override)
2. `<repo_path>/reguard.yml`
3. Built-in integration manifest (`integrations/<repo>.yml`)
4. Legacy `RepoAdapter` fallback (frozen-five only)
5. `UNSUPPORTED`

The legacy adapter fallback is a deliberate bridge for the
five frozen repositories. New repositories should ship a
`reguard.yml`.

## 6. CLI surface

```
reguard init      # create reguard.yml
reguard doctor    # host + config + integration resolution check
reguard check     # run a deterministic compliance check
reguard explain   # show what a requirement test actually tests
reguard list      # enumerate recipes / observers / normalizers / families / integrations
```

Exit codes (for `reguard check`):

| Status | Exit |
|---|---:|
| PASS | 0 |
| FAIL | 1 |
| UNKNOWN | 2 |
| UNSUPPORTED | 3 |
| ERROR | 4 |

`UNKNOWN` and `UNSUPPORTED` are NEVER collapsed into `FAIL`.
The `--fail-on` argument is CI policy only; it does not change
the engine's verdict.

## 7. GitHub Action

`action.yml` is a **composite** action (not a Docker Action)
because Reguard itself needs access to the host OCI runtime
when a recipe uses `OCI_CONTAINER`. The Action:

- Installs Reguard into the host Python (`pip install -e .[yaml]`)
- Resolves the repository SHA
- Clears all provider keys from the harness environment
- Runs `reguard check` with `--fail-on ""` (so the engine's
  exit code does not affect the step)
- Applies the configurable CI failure policy separately
- Writes a polished `GITHUB_STEP_SUMMARY`
- Exposes outputs: `status`, `requirement-id`,
  `requirement-version`, `result-json`, `summary-file`,
  `repo-sha`, `missing-capability`

## 8. Result schema

```json
{
  "schema_version": "1",
  "reguard_version": "0.1.0",
  "repository": "owner/repo",
  "repo_sha": "abc123...",
  "requirement_id": "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
  "requirement_version": "1.4.0",
  "scenario_id": "compliance.article12_1.simple",
  "integration": {
    "recipe": "langgraph-state",
    "observer_versions": ["langgraph-state.callback-observer@1.0.0"],
    "normalizer_version": "langgraph-state.canonical-normalizer@1.0.0"
  },
  "status": "PASS",
  "reason": "...",
  "checks": [
    {"name": "NO_HARNESS_GENERATED_EVENTS",
     "passed": true,
     "detail": "no HARNESS_GENERATED events present"}
  ],
  "missing_capability": null,
  "missing_facts": [],
  "error_class": null,
  "evidence_refs": [".reguard/results/<run-id>/evidence.json"],
  "created_at": "2026-08-30T..."
}
```

Stable fields; no SQLite IDs in the public API.

## 9. Hard constraints honoured

- Did NOT modify Article 12(1) v1.4.0 semantics
- Did NOT modify the frozen five adapters
- Did NOT add an LLM judge
- Did NOT add telemetry
- Did NOT add accounts / billing / hosted dashboard
- Did NOT start Article 12(2)
- Did NOT implement framework-family auto-detection
- Did NOT run another corpus scale gate

— end of architecture document —
