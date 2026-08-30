# Proposed Integration Architecture

**Date:** 2026-08-29
**Inputs:** `repository_integration_matrix.md`, `execution_family_analysis.md`
**Scope:** design the **ExecutionRecipe + ObserverSet + Normalizer**
abstraction that would let Reguard integrate an arbitrary CR-3 repository
without writing a hand-coded adapter/probe for each one.

> **Hard constraint reminder.** This is engineering design only. No
> production adapter is created. No Article 12(1) semantics are changed.
> No framework-family auto-detection is implemented. No new compliance
> verdicts are issued.

---

## 1. Why three abstractions

Inspection of the 12 repos in §1 revealed that the surface area splits
into three independent concerns:

1. **How to drive the agent.** This is the *execution* shape — invoke
   one call, drive a loop, build a graph, build a pipeline. Same Recipe
   may be reused across frameworks if the execution shape is the same
   (Family A: langchain + langgraph + deer-flow).
2. **What to observe.** This is the *event surface* — LangChain
   callbacks, AgentEvent stream, Pipeline component traces, browser
   navigation events. Different frameworks expose completely different
   event APIs. Reguard needs an *Observer* per family that translates
   these into a common internal event vocabulary.
3. **How to normalise state.** This is the *Normalizer* — given the
   framework-specific state (AgentState pydantic, ThreadState TypedDict,
   Pipeline dict, ActionProposal + ActionResult, ...) produce the
   Reguard-internal canonical form (a flat event log keyed by
   `invocation_id`, with model calls / tool calls / errors / messages
   as first-class records).

Recipes are **execution policy**; ObserverSets are **observation
policy**; Normalizers are **state-shape translation**.

A **config-only candidate** is a repository whose existing
injection seams already line up with the Recipe + ObserverSet +
Normalizer seams — i.e. no code change is needed, just a YAML config
that selects the right Recipe + ObserverSet + Normalizer and supplies
the per-repo parameters.

---

## 2. Conceptual model

```
  ┌─────────────────┐
  │  Recipe config  │  family: "langgraph-state"
  │   (YAML / dict) │  recipe: "compilable_graph_v1"
  │                 │  model: stub:Article12_1StubModel
  │                 │  tools: [stub:Article12_1Tool]
  │                 │  checkpointer: in_memory
  │                 │  observer_set: "langgraph_v1"
  │                 │  normalizer: "langgraph_state_to_canonical_v1"
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ ExecutionRecipe │  base class — knows how to wire (model, tools, state)
  │  (concrete)     │  into a framework-specific graph / agent / pipeline,
  │                 │  invoke it, and return a canonical event log.
  └────────┬────────┘
           │  delegates observation to ObserverSet,
           │  delegates state-shape to Normalizer
           ▼
  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
  │   ObserverSet   │  │   Normalizer    │  │   Canonical     │
  │  (concrete)     │  │  (concrete)     │  │   Event Log     │
  │                 │  │                 │  │                 │
  │ subscribes to   │→ │ converts raw   │→ │  {ts, kind,     │
  │ framework-      │  │ framework-     │  │   payload,      │
  │ specific event  │  │ specific state │  │   invocation_id}│
  │ surface         │  │ to canonical   │  │                 │
  └─────────────────┘  └─────────────────┘  └─────────────────┘
```

The three abstractions are independently selectable. A given repo
configuration picks exactly one of each.

---

## 3. `ExecutionRecipe` contract

`ExecutionRecipe` is the *what to run* side. It is the only abstraction
that touches the target framework's *entrypoint* API. ObserverSets and
Normalizers are passive — they receive framework events / state and
translate them.

```python
# Proposed shape — NOT IMPLEMENTED in this discovery phase.

@dataclass(frozen=True)
class RecipeConfig:
    family: str              # e.g. "langgraph-state"
    recipe_id: str           # e.g. "compilable_graph_v1"
    model: Any               # framework-specific chat model instance
    tools: list[Any]         # framework-specific tool instances
    state: dict              # initial state (framework-specific)
    checkpointer: Any | None # persistence handle (framework-specific)
    observer_set_id: str     # which ObserverSet to register
    normalizer_id: str       # which Normalizer to apply
    extra: dict              # framework-specific knobs


class ExecutionRecipe(Protocol):
    """An execution recipe knows how to invoke a target framework's
    agent, graph, or pipeline and return a canonical event log.

    It does NOT decide what to observe (ObserverSet) nor how to
    normalise state (Normalizer). It only:
      1. wire (model, tools, state) into the target framework's
         construction API;
      2. attach the chosen ObserverSet to the framework's event
         surface (e.g. RunnableConfig["callbacks"], AgentEvent stream,
         pipeline tracer);
      3. invoke the framework's run / invoke / astream method;
      4. hand the raw observed events to the Normalizer for canonical
         form;
      5. return the canonical event log + final state.
    """

    family: str
    recipe_id: str

    def build(self, cfg: RecipeConfig) -> BuiltRecipe: ...

    async def run(
        self,
        built: BuiltRecipe,
        inputs: Any,
        *,
        invocation_id: str,
    ) -> tuple[CanonicalEventLog, FinalState]: ...


@dataclass
class BuiltRecipe:
    """The runtime artifact a Recipe builds — a compiled graph, an
    Agent instance, a Pipeline, a Workflow, etc. plus the registered
    ObserverSet and Normalizer."""

    target: Any                  # the framework-native object
    observer_set: ObserverSet
    normalizer: Normalizer
    framework_name: str          # e.g. "langchain", "crewai"
    framework_version: str | None
```

**Key property:** Recipes are stateless (no global config, no env-var
consultation, no model-default registry). The Recipe takes everything
via `RecipeConfig`. This is what enables config-only integration.

---

## 4. `ObserverSet` contract

`ObserverSet` is the *what to capture* side. It maps a
framework-specific event surface onto the canonical event vocabulary.

```python
@dataclass(frozen=True)
class CanonicalEvent:
    invocation_id: str
    ts: str                      # ISO-8601 UTC with 'Z'
    kind: str                    # one of the canonical kinds (see §6)
    payload: dict                # kind-specific structured payload
    provenance: Provenance       # SYSTEM_NATIVE / SYSTEM_STATE_EXPORTED_BY_HARNESS / HARNESS_GENERATED
    source_file: str | None      # which file emitted the event (for harness-generated)
    source_line: int | None


class ObserverSet(Protocol):
    """An ObserverSet knows how to subscribe to a framework-specific
    event surface and emit CanonicalEvents.

    The Recipe calls attach(target, observer_set) at build time; the
    framework then calls back to the observer_set as the agent /
    pipeline / workflow runs."""

    family: str
    observer_set_id: str

    def attach(self, target: Any, invocation_id: str) -> None: ...
    def detach(self, target: Any) -> None: ...
    def events(self) -> list[CanonicalEvent]: ...
```

**Why per-family ObserverSets:** each framework exposes a different
event API:

| Family | Event API | ObserverSet maps |
|---|---|---|
| LangGraph-state | `BaseCallbackHandler` + `astream_events` | `on_llm_start`, `on_llm_end`, `on_tool_start`, `on_tool_end`, `on_chain_start`, `on_chain_end` |
| Single-agent toolkit (agentscope) | `AgentEvent` stream | `ModelCallStartEvent`, `ToolCallStartEvent`, `TextBlock*`, `ThinkingBlock*` |
| Role-orchestration (MetaGPT) | `subscription.subscribe(...)` callbacks | `Role.role_run_start`, `Role.role_run_end` + per-role LLM events |
| Pipeline-DAG (haystack) | `tracing.tracer.ff_tracer` | per-component `run()` start/end |
| CLI-loop (AutoGPT) | `logger.debug` + `dump_prompt` + Sentry | parsed log lines + manual probes |
| Browser-runtime (browser-use) | `ProductTelemetry` + `BrowserSession` events | `agent_step_start`, `agent_step_end`, `browser_navigate`, `browser_click`, ... |
| Runner-SessionService (adk-python) | `runner.run_async` `Event` stream | `Event` → canonical |
| Workflow-builder (microsoft) | OpenTelemetry spans + `ExecutorEvent` | span `start`/`end` |

**Key property:** ObserverSets are *additive* — they never suppress
framework-native events. The framework's own event surface continues
to function; the ObserverSet merely translates events into the
canonical vocabulary.

---

## 5. `Normalizer` contract

`Normalizer` is the *shape translation* side. It takes the
framework-specific final state plus the canonical events produced by
the ObserverSet, and produces a single canonical record for
Reguard-internal consumption.

```python
@dataclass(frozen=True)
class CanonicalRunResult:
    invocation_id: str
    framework: str
    framework_version: str | None
    events: list[CanonicalEvent]              # already canonical
    final_state: dict                        # framework-agnostic
    token_usage: TokenUsage | None           # input/output/cache
    duration_s: float
    error: NormalizedError | None


class Normalizer(Protocol):
    """A Normalizer knows the framework-specific state shape (AgentState
    pydantic, ThreadState TypedDict, Pipeline dict, ActionProposal
    objects, ...) and translates it to the canonical form.

    Crucially, the Normalizer does NOT derive compliance verdicts. It
    only translates structure. Compliance is a separate concern."""

    family: str
    normalizer_id: str

    def normalize_final_state(self, raw_state: Any) -> dict: ...
    def normalize_token_usage(self, raw_usage: Any) -> TokenUsage | None: ...
    def normalize_error(self, raw_exc: BaseException | None) -> NormalizedError | None: ...
    def merge(self, events: list[CanonicalEvent], raw_state: Any,
              raw_usage: Any, duration_s: float,
              error: BaseException | None) -> CanonicalRunResult: ...
```

**Why per-family Normalizers:** even when two families share the same
shape (e.g. Family A and Family G both produce dict-like states with a
`messages` channel), the *normalised* form for downstream Reguard code
must match what other Families produce. Family-specific Normalizers
make this explicit and tested.

---

## 6. Canonical event vocabulary (proposed)

This is the single vocabulary every ObserverSet emits into. Defined
once; tested once; reused everywhere.

```python
class EventKind(str, Enum):
    # Lifecycle
    INVOCATION_START        = "invocation_start"
    INVOCATION_END          = "invocation_end"
    INVOCATION_ERROR        = "invocation_error"

    # Model (LLM) calls
    MODEL_REQUEST           = "model_request"     # full request payload
    MODEL_RESPONSE          = "model_response"    # full response payload
    MODEL_STREAM_CHUNK      = "model_stream_chunk"

    # Tool calls
    TOOL_INVOCATION         = "tool_invocation"   # tool name + args
    TOOL_RESULT             = "tool_result"       # tool output
    TOOL_ERROR              = "tool_error"        # exception

    # Messages (assistant / user / system / tool message log)
    MESSAGE_EMITTED         = "message_emitted"

    # State transitions
    STATE_CHECKPOINT        = "state_checkpoint"  # new checkpoint written
    STATE_SNAPSHOT          = "state_snapshot"    # full state capture

    # Permission / authorisation
    PERMISSION_REQUEST      = "permission_request"
    PERMISSION_GRANT        = "permission_grant"
    PERMISSION_DENIAL       = "permission_denial"

    # Family-specific extras (with sub-kind)
    BROWSER_NAVIGATE        = "browser_navigate"  # F only
    BROWSER_CLICK           = "browser_click"
    PIPELINE_COMPONENT_RUN  = "pipeline_component_run"  # D only
    ROLE_MESSAGE_PUBLISH    = "role_message_publish"    # C only
```

The **canonical event vocabulary is part of the frozen contract.** New
kinds are added by extending the enum and bumping the contract
version; existing kinds never change shape (only payload fields may be
added).

---

## 7. Recipe ↔ ObserverSet ↔ Normalizer matrix

For each of the eight execution families identified in
`execution_family_analysis.md`, here is the *minimal* Recipe +
ObserverSet + Normalizer needed:

| Family | Recipe | ObserverSet | Normalizer |
|---|---|---|---|
| A — LangGraph-state | `CompilableGraphRecipe` (one recipe; picks `create_agent` vs `StateGraph` via config) | `LangGraphCallbackObserverSet` (uses `BaseCallbackHandler` + `astream_events`) | `LangGraphStateNormalizer` (handles `AgentState` / `MessagesState` / `ThreadState`) |
| B — Single-agent toolkit | `SingleAgentReplyRecipe` (covers agentscope `reply` + agno `run`/`arun` via Normalizer) | `AgentEventStreamObserverSet` | `AgentStateNormalizer` (covers pydantic `AgentState` + agno `storage=`) |
| C — Role-orchestration | `RoleOrchestrationRecipe` (crewAI `kickoff` + MetaGPT `team.run` via Normalizer) | `RoleCallbackObserverSet` (covers `subscribe(...)` + `token_usage_callback`) | `RoleMemoryNormalizer` (covers crewAI memory + MGXEnv history) |
| D — Pipeline-DAG | `PipelineRunRecipe` (haystack `pipeline.run`) | `PipelineComponentObserverSet` (tracer + per-component hooks) | `PipelineStateNormalizer` (per-run input/output dicts) |
| E — CLI-loop | `LongRunningLoopRecipe` (drives propose → execute → propose) | `LoggerParseObserverSet` (parses `logger.debug` lines + Sentry spans) | `EpisodicHistoryNormalizer` (covers `EpisodicActionHistory`) |
| F — Browser-runtime | `BrowserRunRecipe` (browser-use `agent.run`) | `BrowserTelemetryObserverSet` (covers `ProductTelemetry` + `BrowserSession`) | `BrowserHistoryNormalizer` (covers `AgentHistoryList` + `ActionResult`) |
| G — Runner-SessionService | `RunnerSessionServiceRecipe` (adk-python `Runner.run_async`) | `RunnerEventObserverSet` (covers `SessionService` `Event` stream) | `SessionServiceNormalizer` (covers `Session.events` + `state` dict) |
| H — Workflow-builder | `WorkflowBuilderRecipe` (microsoft chat-agent + workflow) | `OTelSpanObserverSet` (covers `opentelemetry` spans + workflow `ExecutorEvent`) | `AgentThreadNormalizer` (covers `AgentThread` + workflow state) |

**Recipe count:** 8 (one per family). **ObserverSet count:** 8.
**Normalizer count:** 8.

These are the *minimal* reusable units. A future Recipe may combine
two families (e.g. H's chat-agent path could share Family B's
ObserverSet + Normalizer; H's workflow path could share Family A's
Recipe + ObserverSet + Normalizer).

---

## 8. Config-only candidate count

A repository is a **config-only candidate** if its existing seams
align with the proposed Recipe + ObserverSet + Normalizer abstractions
without any code change in the repository. From §4 of
`execution_family_analysis.md`:

| Family | Members | Config-only? | Why |
|---|---|---|---|
| A | langchain, langgraph, deer-flow | **YES** (3) | All three expose `BaseChatModel` + `BaseTool` + LangGraph state |
| B | agentscope, agno | **YES** (2) | Both expose a single-agent-with-tools seam |
| C | crewAI, MetaGPT | **YES** (2) | Both expose `Crew` / `Team` with role-based agents |
| D | haystack | **YES** (1) | Pipeline + Component protocol |
| E | AutoGPT | **YES** (1) — Recipe shape differs but seams line up | propose_action + execute + history |
| F | browser-use | **YES** (1) — tool model differs but seam lines up | Controller + run + telemetry |
| G | adk-python | **YES** (1) | Runner + SessionService + Event |
| H | microsoft/agent-framework | **YES** (1) — chat-agent + workflow | ChatClient + tools + WorkflowBuilder |

**Tally:** all 12 of the 12 inspected repos are **config-only
candidates** for their family's Recipe + ObserverSet + Normalizer.

That is the headline engineering result of this discovery: **the
existing injection seams in every inspected repo already line up with
the proposed three-abstraction model.** No hand-written adapter per
repository is required; the per-repo work reduces to writing a YAML
config that selects the right Recipe + ObserverSet + Normalizer and
supplies the per-repo parameters.

---

## 9. What the config looks like (illustrative)

A single example config for a hypothetical langchain agent. **This is
not implemented — only illustrative.**

```yaml
# audit/integration_discovery/configs/langchain-ai_langgraph_compilable_v1.yaml
recipe:
  family: langgraph-state
  recipe_id: compilable_graph_v1
  framework:
    package: langgraph
    entrypoint: langgraph.graph.state.StateGraph
  model:
    implementation: "audit.integrations.stub:Article12_1StubModel"
    spec_kwargs:
      default_response: "no-tool-call"
  tools:
    - implementation: "audit.integrations.stub:Article12_1EchoTool"
  state_schema:
    implementation: "langchain.agents.factory:AgentState"
  checkpointer:
    implementation: "langgraph.checkpoint.memory:MemorySaver"

observer_set:
  observer_set_id: langgraph_callback_v1
  attach_via:
    target: "config['configurable']['callbacks']"

normalizer:
  normalizer_id: langgraph_state_v1
  state_to_canonical:
    messages_path: "state['messages']"
    token_usage_path: "state['messages'][-1].usage_metadata"
  error_path: "state['error']"

runtime:
  invocation_timeout_s: 60
  step_timeout_s: 30
```

The Recipe loads the framework package, instantiates the model stub,
instantiates the tool stub, builds the graph with the state schema and
checkpointer, attaches the ObserverSet to the callback config, invokes
the graph, hands the raw state and observer events to the Normalizer,
and returns the canonical run result.

---

## 10. What stays the same (Article 12(1) v1.4.0)

- The v1.4.0 five-bucket compliance model (`PASS` / `FAIL` /
  `UNKNOWN` / `UNSUPPORTED` / `ERROR`) is **unchanged**.
- The `compliance_runtime_run_id` linkage is **unchanged**.
- The `execution_recipe_id` / `execution_recipe_version` schema fields
  are **unchanged** (Recipe IDs map cleanly onto `execution_recipe_id`).
- The fast-`UNSUPPORTED` short-circuit for repos missing a compatible
  Recipe is **unchanged**.
- The CR-3 historical anomaly row (id=93, corpus_run_id=11) is
  **preserved**.
- All source-control invariants established by
  `audit/corpus_runner_v1/cr3_persistence_hardening_report.md` are
  **unchanged**.

The new abstraction is purely an internal restructuring of how
"compatible execution recipe" is selected and applied. It does not
change any contract the corpus runner exposes.

---

## 11. What changes structurally (NOT semantics)

These are **engineering** changes — they do not alter the
Article 12(1) v1.4.0 semantics:

- A new module `src/compliance/corpus_runner/recipes/` containing:
  - `recipe.py` — `ExecutionRecipe` Protocol
  - `observer.py` — `ObserverSet` Protocol + `CanonicalEvent` / `EventKind`
  - `normalizer.py` — `Normalizer` Protocol + `CanonicalRunResult`
  - `recipes/langgraph_state.py` — concrete `CompilableGraphRecipe`
  - `recipes/agent_toolkit.py` — concrete `SingleAgentReplyRecipe`
  - `recipes/role_orchestration.py` — concrete `RoleOrchestrationRecipe`
  - `recipes/pipeline_dag.py` — concrete `PipelineRunRecipe`
  - `recipes/cli_loop.py` — concrete `LongRunningLoopRecipe`
  - `recipes/browser_runtime.py` — concrete `BrowserRunRecipe`
  - `recipes/runner_session.py` — concrete `RunnerSessionServiceRecipe`
  - `recipes/workflow_builder.py` — concrete `WorkflowBuilderRecipe`
- Eight corresponding `observers/*.py` and `normalizers/*.py` modules.
- A registry mapping `family` → (recipe_id, observer_set_id,
  normalizer_id).
- YAML config schema for per-repo `recipe: ...` blocks.

---

## 12. Hard constraints honoured

- Did NOT implement any of §11. This file is the design document.
- Did NOT add production adapters.
- Did NOT implement framework-family auto-detection (the family is
  *selected by the config*, not inferred from the repo).
- Did NOT change Article 12(1) v1.4.0 semantics.
- Did NOT modify any third-party repository.
- Did NOT change the runtime security boundary.
- Did NOT issue any compliance verdicts for newly inspected repositories.

— end of architecture proposal —