---
title: Reguard Core v0.1
study: Reguard
status: release-candidate validation complete; READY
date: 2026-08-30
phase: post-discovery v0.1 productization
artifacts:
  - README.md
  - SECURITY.md
  - CONTRIBUTING.md
  - docs/integrations.md
  - action.yml
  - examples/minimal-agent/
  - integrations/
  - src/compliance/integrations/
  - src/compliance/cli/
  - tests/integrations/
  - tests/cli/
  - audit/reguard_core_v0_1/architecture.md
  - audit/reguard_core_v0_1/pilot_results.md
  - audit/reguard_core_v0_1/github_action_validation.md
  - audit/reguard_core_v0_1/release_candidate_report.md
tags: [study, reguard-core, v0.1, release-candidate, recipe-observer-normalizer, family-A, github-action]
---

# Reguard Core v0.1

Reguard Core v0.1 productization. Three-abstraction integration
model + CLI + GitHub Action + demo + docs + frozen-five
regression preserved.

## Headline result

**READY** for v0.1 release-candidate.

- 285 tests passing (247 baseline + 38 new).
- One pilot execution family (Family A — LangGraph-state).
- 0 repository-specific Python adapters.
- GitHub Action contract defined.
- No provider key, no telemetry, no cloud required.

## Architecture summary

```
RepositoryIntegration
    ↓
ExecutionRecipe     # what to run + how to invoke it
    ↓
ObserverSet         # what native observations to capture
    ↓
Normalizer          # how to translate native observations into Reguard Evidence
```

The integration layer contains NO Article 12(1) verdict logic.
Requirement tests (out of the integration layer) decide
PASS / FAIL.

## Pilot family

**Family A — LangGraph-state.**
Members: `langchain-ai/langchain`, `langchain-ai/langgraph`,
`bytedance/deer-flow`.

Shared Recipe: `langgraph-state@1.0.0`
Shared Observer: `langgraph-state.callback-observer@1.0.0`
Shared Normalizer: `langgraph-state.canonical-normalizer@1.0.0`

Per-repo differences are entirely declarative (`entrypoint.target`,
`package_root`).

## CLI surface

```
reguard init      # create reguard.yml
reguard doctor    # host + config + integration resolution
reguard check     # run a deterministic compliance check
reguard explain   # show what a requirement test actually tests
reguard list      # enumerate recipes / observers / normalizers / families / integrations
```

Exit codes: `PASS=0`, `FAIL=1`, `UNKNOWN=2`, `UNSUPPORTED=3`,
`ERROR=4`. UNKNOWN and UNSUPPORTED are NEVER collapsed into FAIL.

## `reguard.yml` schema

Schema version 1. Strict validation. Rejects unknown recipes,
unknown observers, unknown normalizers, provider-key model
strategies, and forbidden env vars.

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
    strategy: deterministic_stub
  observers:
    - langgraph-state.callback-observer
  normalizer:
    id: langgraph-state.canonical-normalizer

scenarios:
  - compliance.article12_1.simple
```

## Pilot results

Demo end-to-end (`acme/minimal-agent`):

```
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

## Frozen-five regression

`tests/pipeline/`: 103 passed. The five frozen adapters
(mini-swe-agent, gptme, nanobot, CoreCoder, PocketFlow) were
not modified. The legacy CLI (`scripts/compliance-check.py`)
is unchanged.

## Hard constraints honoured

- No Article 12(1) v1.4.0 semantic change
- No production-adapter rewrite
- No LLM judge
- No telemetry
- No cloud / billing
- No provider API keys required
- No framework-family auto-detection
- No Article 12(2)
- No another corpus scale gate

## Links

- [[Corpus Runner v1 Implemented]] — prior state
- [[Repository Integration Architecture]] — discovery
  phase that produced the READY verdict
- `audit/integration_discovery/final_25_item_report.md` —
  upstream discovery final report
- `audit/reguard_core_v0_1/release_candidate_report.md` —
  v0.1 RC final report (25 items)
- `audit/reguard_core_v0_1/architecture.md` — integration
  architecture document
- `audit/reguard_core_v0_1/pilot_results.md` — pilot
  runtime results
- `audit/reguard_core_v0_1/github_action_validation.md` —
  Action contract and failure policy

## Final verdict

**READY** for Reguard Core v0.1 release-candidate.
Implementation is complete to the v0.1 RC scope defined in
the brief. v0.2+ work (additional families, public OCI
runtime image, dogfood workflow on every PR) is explicitly
out of scope.
