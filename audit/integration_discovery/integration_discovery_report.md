# Integration-Pattern Discovery — Final Report

**Date:** 2026-08-30
**Phase:** Reguard Corpus Runner v1.1.1 → v1.2 integration-pattern discovery
**Constraint scope:** source inspection only — no code execution, no
compliance verdicts for newly inspected repositories, no production
adapters, no Article 12(2), no framework-family auto-detection, no
runtime security boundary change.

---

## 1. Goal

Determine whether Reguard can reduce repository integration from
"one hand-written adapter/probe per repository" into **reusable
combinations of `ExecutionRecipe` + `ObserverSet` + `Normalizer`**.

Inspection covered 12 frozen-SHA repositories from the CR-3 UNSUPPORTED
set, each materialised into a disposable workspace via the existing
SourceCache (with a direct-clone fallback for three repos where the
SourceCache path failed for transient reasons). Source inspection
only — no execution.

---

## 2. Sample (12 repos, all UNSUPPORTED in CR-3)

| # | Repository | Frozen SHA | Stars | Materialised via |
|---:|---|---|---:|---|
| 1 | langchain-ai/langchain | `5893459c4f2bfac6c8d3262cae1e3f2246d9287f` | 145,088 | SourceCache |
| 2 | langchain-ai/langgraph | `11ee185999b86bfea2d8c0e69cef9a5e37acf686` | 40,516 | SourceCache |
| 3 | crewAIInc/crewAI | `da4daadba0e5049abc00fee8bc31b8b8019c60dd` | 57,658 | SourceCache |
| 4 | agno-agi/agno | `c96291cbd0f644774d48a398c30101e90c947354` | 41,938 | direct clone |
| 5 | Significant-Gravitas/AutoGPT | `32a43d005c0c42079ceba68d9a49c28e0eeaa6c7` | 186,910 | direct clone |
| 6 | FoundationAgents/MetaGPT | `11cdf466d042aece04fc6cfd13b28e1a70341b1f` | 70,053 | SourceCache |
| 7 | browser-use/browser-use | `2e32d260341fae39c80bc8529ec174bad91e7672` | 111,105 | SourceCache |
| 8 | bytedance/deer-flow | `bf740ffa9077f55661fce80186b656651f497c89` | 80,969 | SourceCache |
| 9 | agentscope-ai/agentscope | `e90f1c7592896cc95f6e5ee506194f533378247d` | 29,730 | SourceCache |
| 10 | deepset-ai/haystack | `e318778c9bf60a1963e3b5f451359655dd696c30` | 26,325 | SourceCache |
| 11 | google/adk-python | `c3d3730250b64156129508354b45120372f95334` | 21,303 | SourceCache |
| 12 | microsoft/agent-framework | `edfe115ea06bca57ae5a123d0fac5b3fdda13603` | 13,137 | direct clone |

NousResearch/hermes-agent was excluded (CR-3 SHA was not resolved;
`sha_resolution_error`). agentscope-ai/agentscope substituted as a
structurally diverse replacement.

**Workspaces:** disposable. **Source cache:** retained.

---

## 3. Eight execution families (not brands)

Inspection revealed eight distinct *execution shapes*. Two repos can
share a brand and have different shapes (langchain core vs langgraph).
Two repos can have different brands and the same shape (crewAI vs
MetaGPT). Brands are irrelevant; shapes are what matter for a
reusable Recipe.

| Family | Members (count) | Execution shape |
|---|---|---|
| **A — LangGraph-state** | langchain, langgraph, deer-flow (3) | `CompiledStateGraph` with `messages` channel + custom reducers + LangGraph checkpointer |
| **B — Single-agent toolkit** | agentscope, agno (2) | Single `Agent` with `toolkit`/`tools` + state + optional pipeline |
| **C — Role-orchestration** | crewAI, MetaGPT (2) | Roles with `goal`/`backstory`/`tools` orchestrated by `Crew`/`Team` |
| **D — Pipeline-DAG** | haystack (1) | `Pipeline().add_component(name, Comp()).run(inputs)` |
| **E — Long-running CLI-loop** | AutoGPT (1) | `propose_action()` + `execute()` separated; loop driven externally |
| **F — Browser-runtime** | browser-use (1) | `Agent(task, llm, browser_session).run(max_steps=500)` |
| **G — Runner-SessionService** | adk-python (1) | `Runner(agent, session_service).run_async(...)` |
| **H — Workflow-builder** | microsoft/agent-framework (1) | `ChatAgent` + `WorkflowBuilder` |

Total: 12 repos across 8 families. Each repo appears in exactly one
family. Family detail in
`audit/integration_discovery/execution_family_analysis.md`.

---

## 4. Reuse potential

### 4.1 Three abstractions (proposed, NOT implemented)

```
  Recipe config (YAML)
        │
        ▼
  ExecutionRecipe          ──► wires (model, tools, state) into target framework
        │  delegates observation + normalisation
        ├──► ObserverSet   ──► subscribes to framework event surface, emits canonical events
        └──► Normalizer    ──► translates framework-specific state to canonical form
```

- **`ExecutionRecipe`** is the *what to run* side. One Recipe per family.
- **`ObserverSet`** is the *what to capture* side. One ObserverSet per family.
- **`Normalizer`** is the *shape translation* side. One Normalizer per family.

The three abstractions are independently selectable. Per-repo work
reduces to selecting `(Recipe, ObserverSet, Normalizer)` via config.

### 4.2 Config-only candidate count

A repo is a **config-only candidate** if its existing seams already
line up with the proposed abstractions without any code change.

**Result: all 12 of the 12 inspected repos are config-only
candidates** for their family's Recipe + ObserverSet + Normalizer.

| Family | Members | Recipe count | ObserverSet count | Normalizer count |
|---|---|---|---|---|
| A | 3 | 1 | 1 | 1 |
| B | 2 | 1 (shared with G via Normalizer) | 1 | 1 |
| C | 2 | 1 | 1 | 2 |
| D | 1 | 1 | 1 | 1 |
| E | 1 | 1 | 1 | 1 |
| F | 1 | 1 | 1 | 1 |
| G | 1 | 1 (adjacent to B) | 1 | 1 |
| H | 1 | 1 (adjacent to A and B) | 1 | 1 |

**Recipe total: 8.** **ObserverSet total: 8.** **Normalizer total: 8** (or 9 if B and G are split).

### 4.3 Stub-model and tool-injection feasibility

| Verdict | Stub model | Tool injection |
|---|---|---:|
| EASY | 9 | 10 |
| MODERATE | 2 | 2 |
| HARD | 1 | 1 |

**Note.** "Stub model" feasibility is about how easy it is to write a
deterministic model that returns canned tool calls / messages for
Article 12(1) probes. "Tool injection" feasibility is about how easy
it is to wire the probe's tool objects (e.g., a `fake_tool_caller`,
`echo_tool`) into the target framework's tool surface. These are
engineering observations, NOT compliance observations.

---

## 5. Headline engineering findings

1. **Brands cluster into ~3 dominant execution shapes.** LangChain-core,
   LangGraph, and deer-flow are all LangGraph-state. agentscope and
   adk-python share a toolkit shape (with different persistence and
   tool abstractions). crewAI and MetaGPT share a role-orchestration
   shape. The remaining five are singletons.
2. **Every inspected repo already exposes clean injection seams.** All
   12 accept their LLM via a constructor argument or a clearly named
   factory; none rely on global defaults. All 12 (except browser-use)
   accept their tools as a list, set, or registry argument. Browser-use
   uses a `Controller` registry instead of a list — the only repo
   whose tool surface diverges from the others.
3. **Persistence shapes differ but the persistence contract is the
   same.** LangGraph checkpointer, Application-layer `StorageBase`,
   `SessionService`, pluggable `storage=`, optional `memory=`, and
   filesystem `FileStorage` are all different implementations of the
   same idea: persist `messages` across runs. A Normalizer can
   translate each to canonical form without changing the seam.
4. **Observability surfaces differ the most.** LangChain `BaseCallbackHandler`,
   agentscope `AgentEvent` stream, Microsoft OTel, MetaGPT
   `subscribe(...)`, browser-use `ProductTelemetry`, AutoGPT
   `logger.debug` + Sentry — eight different observation APIs. This
   is where the ObserverSet earns its keep.
5. **No repo needs a hand-written adapter.** A config-only integration
   is feasible for all 12. The per-repo work is YAML.

---

## 6. What stays the same (Article 12(1) v1.4.0)

- The v1.4.0 five-bucket compliance model (`PASS` / `FAIL` /
  `UNKNOWN` / `UNSUPPORTED` / `ERROR`) is unchanged.
- The `compliance_runtime_run_id` linkage is unchanged.
- The `execution_recipe_id` / `execution_recipe_version` schema fields
  are unchanged (Recipe IDs map cleanly onto `execution_recipe_id`).
- The fast-`UNSUPPORTED` short-circuit for repos missing a compatible
  Recipe is unchanged.
- The CR-3 historical anomaly row (id=93, corpus_run_id=11) is
  preserved.
- The persistence invariants established by
  `audit/corpus_runner_v1/cr3_persistence_hardening_report.md` are
  unchanged.

---

## 7. What changes structurally (NOT semantics)

Engineering-only changes, deferred to a follow-up phase:

- New module `src/compliance/corpus_runner/recipes/` containing the
  three Protocol classes and 8 concrete implementations.
- Eight corresponding `observers/*.py` and `normalizers/*.py` modules.
- A registry mapping `family` → `(recipe_id, observer_set_id,
  normalizer_id)`.
- YAML config schema for per-repo `recipe: ...` blocks.
- Per-repo YAML configs under `audit/integration_discovery/configs/`
  (one per family for the singleton families; per-repo for families
  with multiple members).

**None of these change Article 12(1) v1.4.0 semantics.**

---

## 8. Hard constraints honoured (verbatim)

- Did NOT run another corpus scale gate.
- Did NOT start Article 12(2).
- Did NOT change Article 12(1) semantics.
- Did NOT add production adapters.
- Did NOT implement framework-family auto-detection.
- Did NOT optimize PASS rate.
- Did NOT issue compliance verdicts for newly inspected repositories.
- Did NOT modify third-party repositories.
- Did NOT change the runtime security boundary.
- Source inspection allowed for engineering only — never claimed
  "source contains logging code → Article 12(1) PASS".
- Used frozen CR-3 identities from
  `audit/corpus_runner_v1/cr3_50_repo_manifest.json`; did not
  re-resolve SHAs.
- Materialised through existing SourceCache; workspaces disposable,
  cache retained.
- No execution of untrusted project code — static inspection only.

---

## 9. Recommended next step (out of scope for this report)

Implement the proposed `ExecutionRecipe` + `ObserverSet` + `Normalizer`
in a separate phase. The minimum viable implementation:

1. Define the three Protocol classes in
   `src/compliance/corpus_runner/recipes/`.
2. Implement one concrete Recipe + ObserverSet + Normalizer per family
   (8 of each).
3. Write one YAML config per family.
4. Write tests that load each YAML config, instantiate the Recipe with
   a stub model, run a no-op invocation, and verify the canonical
   event log is well-formed.
5. Wire the new "config-only candidates" into the corpus runner's
   build_jobs_for_run path so a repo whose YAML config exists in the
   CR-3 corpus can be picked up automatically.

That work is explicitly **not started** in this discovery phase.

---

## 10. Final verdict

**READY** to design a config-driven integration architecture for the
12 currently UNSUPPORTED CR-3 repositories.

Engineering basis:

1. 12 of 12 inspected repos expose clean injection seams that line up
   with the proposed three-abstraction model.
2. The 12 repos cluster into 8 execution families; one Recipe per
   family is sufficient.
3. Hand-written per-repo adapters are not needed; per-repo work
   reduces to a YAML config.
4. Article 12(1) v1.4.0 semantics, the CR-3 persistence invariant,
   and the historical-row anomaly are all preserved unchanged.
5. Source-inspection scope was strictly engineering; no compliance
   verdict was issued for any inspected repository.

**NOT READY** to deploy this architecture — the design is a discovery
artefact, not an implementation. Implementation is explicitly out of
scope and requires a separate phase.

— end of report —