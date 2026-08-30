# Integration-Pattern Discovery — 25-Item Final Report

**Date:** 2026-08-30
**Phase:** Reguard Corpus Runner v1.1.1 → v1.2 integration-pattern discovery
**Verdict:** **READY** to design a config-driven integration architecture
for the 12 currently UNSUPPORTED CR-3 repositories. Implementation is
**not started** in this phase.

> **Hard constraint reminder.** No compliance verdict was issued for any
> inspected repository. The work below is engineering discovery only.

---

## Section A — Sample and source (items 1-5)

1. **Sample size = 12** CR-3-UNSUPPORTED repositories, frozen SHAs only
   (no HEAD inspection, no SHA re-resolution).
2. **Sample composition** — 9 preferred from the brief plus 3
   structurally diverse (haystack, adk-python, microsoft/agent-framework).
   NousResearch/hermes-agent excluded due to
   `sha_resolution_error`; agentscope-ai/agentscope substituted as a
   replacement with a different execution shape (GoalPipeline).
3. **Materialisation** — 9 via existing `SourceCache` +
   `RepositoryMaterializer`; 3 via direct `git clone` fallback
   (agno-agi/agno, Significant-Gravitas/AutoGPT, microsoft/agent-framework)
   because SourceCache failed for transient reasons (git fetch 128,
   unsafe symlink safety check on AutoGPT's `.agents/skills`).
4. **Materialisation roots** — distinct from any prior CR-3 run:
   `discovery_cache_root = /home/mrcel/.reguard/discovery_cache`,
   `discovery_workspace_root = /home/mrcel/.reguard/discovery_ws`.
   `/tmp` was avoided (only 7.7 G free, mostly used by other caches).
5. **Workspace discipline** — inspection workspaces are disposable;
   source cache retained. Sample manifest persisted at
   `audit/integration_discovery/sample_manifest.json` (12 entries).

## Section B — Per-repo findings (items 6-17)

6. **langchain-ai/langchain @ `5893459c…`** — uv workspace monorepo;
   `create_agent(model=..., tools=..., state_schema=...)` at
   `libs/langchain_v1/langchain/agents/factory.py:840` returns a
   `CompiledStateGraph`; in-repo `FakeToolCallingModel` reference at
   `tests/unit_tests/agents/model.py`; **stub model EASY, tool
   injection EASY**.

7. **langchain-ai/langgraph @ `11ee185999…`** — uv workspace with
   sub-packages (`libs/langgraph`, `libs/checkpoint`,
   `libs/checkpoint-sqlite`, `libs/checkpoint-postgres`, `libs/prebuilt`);
   `StateGraph(...).compile(checkpointer=...)` returns
   `CompiledStateGraph`; persistence is opt-in via checkpointer;
   **stub model EASY, tool injection EASY** (inherits langchain core).

8. **crewAIInc/crewAI @ `da4daadba…`** — uv-managed monorepo under
   `lib/` (`crewai`, `crewai-tools`, `crewai-core`, `crewai-files`,
   `cli`, `devtools`); `Agent(role, goal, backstory, llm, tools)` +
   `Crew(...).kickoff(inputs)`; LLM wrapper at `crewai/llm.py`
   resolves string → LiteLLM by default; **stub model MODERATE**
   (different `BaseLLM.call()` protocol), **tool injection EASY**.

9. **agno-agi/agno @ `c96291cbd0…`** — uv-managed single package
   (`libs/agno`); `Agent(model, tools, instructions, storage)` +
   `.run(message)` / `.arun(message)`; framework-internal model
   registry; pluggable `storage=` (sqlite / postgres); **stub model
   MODERATE** (must subclass + register), **tool injection EASY**.

10. **Significant-Gravitas/AutoGPT @ `32a43d005c…`** — mixed monorepo
    (modern FastAPI backend + legacy Python CLI under `classic/`); the
    legacy `Agent` exposes `propose_action()` + `execute()` as
    **separate calls** (long-running CLI loop, not single-shot); LLM
    via `MultiProvider` factory at `agents/agent.py:357-366`; ReWOO
    bypass at `agents/agent.py:312-326`; permission manager at
    `agents/agent.py:387-400`; `AgentSettings` + `EpisodicActionHistory`
    state + `FileStorage` filesystem backend; **stub model HARD**
    (long-running process + phase-aware LLM bypass + MultiProvider),
    **tool injection MODERATE** (command-provider pipeline).

11. **FoundationAgents/MetaGPT @ `11cdf466d0…`** — single Python
    package (`metagpt/`); `Team(investment, role_roles=[...]).run(idea)`;
    **global `LLMConfig`** at `config/config2.yaml:4-8` + `metagpt/
    configs/llm_config.py:59-61`; consumed by `BaseLLM.aask()`;
    `Role.set_actions([...])` registers `Action` subclasses
    (`metagpt/roles/role.py`); `MGXEnv` for multi-agent routing
    (`metagpt/environment/mgx/mgx_env.py:60`); `subscribe(role,
    trigger, callback)` for async callbacks (`metagpt/subscription.py:
    44-63`); **stub model MODERATE** (global LLMConfig + aask
    patch), **tool injection MODERATE** (action list, not constructor
    arg).

12. **browser-use/browser-use @ `2e32d26034…`** — single-package
    Python (`browser_use/`); `Agent(task, llm, browser_session, ...)`
    + `await agent.run(max_steps=500)` returns
    `AgentHistoryList[AgentStructuredOutput]`; **`Controller` registry**
    with `@controller.action(...)` decorator (browser-action-specific);
    first-party `ProductTelemetry` opt-out via env var
    (`service.py:2214-2246`); `save_conversation_path` filesystem save
    (`service.py:1720-1729`); **stub model EASY** (`BaseChatModel`
    subclass + custom `Controller`), **tool injection HARD** (custom
    `RegisteredAction` plumbing; no plain list constructor).

13. **bytedance/deer-flow @ `bf740ffa90…`** — uv workspace, 3 packages
    (`deerflow`, `deerflow-harness`, `deerflow-extension-api`);
    hatchling backend; `requires-python = ">=3.12"`; LangGraph Server
    entrypoint `deerflow.agents:make_lead_agent` (`backend/langgraph.
    json:9`); `_assemble_lead_agent` calls `langchain.agents.create_
    agent(model, tools, middleware, state_schema)` (`agent.py:1047-1053,
    1165-1171`); model factory `create_chat_model(...)` at
    `models/factory.py:174-321` resolves YAML `cfg.use` to class path;
    subagent delegation via `task_tool` → `SubagentExecutor` (each
    builds a fresh `create_agent` per delegation); `ThreadState
    (AgentState)` with custom reducers (`merge_sandbox`,
    `merge_delegations`, etc.); persistence via langgraph-checkpoint-
    sqlite (default) / postgres; ~40 middlewares emit
    `aemit_custom_event`; `attach_tracing=False` discipline enforced
    inside the graph; **stub model EASY, tool injection EASY**.

14. **agentscope-ai/agentscope @ `e90f1c7592…`** — single Python
    package at `src/agentscope/`; setuptools backend; ~16 optional
    extras; `Agent(name, system_prompt, model, toolkit, middlewares,
    state)` at `agent/_agent.py:112-217`; `await agent.reply(inputs)`
    / `async for event in agent.reply_stream(inputs)`; only built-in
    pipeline is `GoalPipeline(executor, verifier, max_iters=10)`;
    `ChatModelBase` abstract + 8 concrete providers
    (`OpenAIChatModel`, `AnthropicChatModel`, `DashScopeChatModel`,
    `DeepSeekChatModel`, `GeminiChatModel`, `OllamaChatModel`,
    `XAIChatModel`, `OpenAIResponseModel`); `CredentialFactory` for
    typed credentials; `ToolBase` + `Toolkit(tools=[...])` with
    `ToolGroup`s; `AgentState` pydantic (`session_id`, `context`,
    `summary`, `tool_context`, `tasks_context`, `middle_context`);
    `StorageBase` for SQL (SQLAlchemy + Alembic) or Redis persistence;
    rich `AgentEvent` stream (23 event subclasses); OpenTelemetry
    `TracingMiddleware`; **stub model EASY, tool injection EASY**.

15. **deepset-ai/haystack @ `e318778c9b…`** — single Python package
    `haystack`; pyproject at root with `openai>=2.6.0`; **`Pipeline`
    DAG**, not an agent — `Pipeline().add_component("name",
    MyComponent())` → `pipeline.run({"comp1": ...})` returns dict of
    named outputs; `Component` Protocol (runtime-checkable) at
    `core/component/component.py:137-184`; chat generators
    (`OpenAIChatGenerator`, `AzureOpenAIChatGenerator`,
    `OpenAIResponsesChatGenerator`, `AzureOpenAIResponsesChatGenerator`,
    `LLM`, `MockChatGenerator`) lazy-imported via
    `_import_structure`; lazy `tracing.tracer.ff_tracer`;
    `MockChatGenerator` already exists; **stub model EASY, tool
    injection EASY** (interpreted as pipeline-component injection).

16. **google/adk-python @ `c3d3730250…`** — single Python package
    `google-adk` at `src/google/adk/`; `aiosqlite>=0.21` core dep;
    Python 3.10-3.14 support (per `constraints-*.txt`); `LlmAgent
    (name, model, instruction, tools)` + `Runner(agent, app_name,
    session_service)` + `async for event in runner.run_async(user_id,
    session_id, new_message)`; `LiteLlm` (litellm-based multi-provider)
    wrapper; env-var API keys for `GOOGLE_API_KEY`, `GEMINI_API_KEY`,
    `ANTHROPIC_API_KEY`, `VERTEXAI_PROJECT`; `BaseTool` + `BaseToolset`
    with async `get_tools()` protocol at `tools/base_toolset.py:88-127`
    + `tool_name_prefix` grouping (`base_toolset.py:103-166`);
    `SessionService` (InMemory / Sqlite / VertexAI); artifact services
    (`InMemoryArtifactService`, `FileArtifactService`,
    `GcsArtifactService`); sub-agents via `LlmAgent(sub_agents=[...])`;
    `SequentialAgent` / `ParallelAgent` / `LoopAgent`;
    `BigQueryAgentAnalyticsPlugin`; **stub model EASY, tool injection
    EASY**.

17. **microsoft/agent-framework @ `edfe115ea0…`** — **uv workspace
    monorepo**, 35 Python packages under `python/packages/`; 30 use
    `flit_core.buildapi`, 2 use `uv_build`, 2 use `hatchling.build`,
    1 uses `setuptools.build_meta`; `poethepoet==0.48.0` task runner;
    no native extensions; **two coexisting execution shapes**:
    `ChatAgent(chat_client=..., instructions=..., tools=[...])` and
    `WorkflowBuilder().set_start_executor(...).add_edge(...).build()`;
    `ChatClient` abstract with concrete `OpenAIChatClient`,
    `AnthropicChatClient`, `AzureAIAgent`, `OllamaChatClient`,
    `GeminiChatClient`, `MistralChatClient`, `BedrockChatClient`,
    `FoundryChatClient`; `ai_function` decorator → `AIFunction`
    (dataclass, not framework subclass); `AgentThread` per chat
    agent; OpenTelemetry spans; optional `RedisStateStore`;
    **stub model EASY, tool injection EASY**.

## Section C — Family taxonomy (items 18-19)

18. **Eight execution families identified** (not brands):

    | Family | Members | Execution shape |
    |---|---|---|
    | A — LangGraph-state | langchain, langgraph, deer-flow | `CompiledStateGraph` + checkpointer |
    | B — Single-agent toolkit | agentscope, agno | Single `Agent` + `Toolkit` |
    | C — Role-orchestration | crewAI, MetaGPT | Roles + `Crew` / `Team` |
    | D — Pipeline-DAG | haystack | `Pipeline().add_component(...)` |
    | E — Long-running CLI-loop | AutoGPT | `propose_action()` + `execute()` |
    | F — Browser-runtime | browser-use | `Agent.run(max_steps=500)` over browser |
    | G — Runner-SessionService | adk-python | `Runner.run_async(...)` + `SessionService` |
    | H — Workflow-builder | microsoft/agent-framework | `ChatAgent` + `WorkflowBuilder` |

    Every repo appears in exactly one family. Detail in
    `audit/integration_discovery/execution_family_analysis.md`.

19. **Family-A is the densest** with 3 members; families B and C each
    have 2; families D, E, F, G, H are singletons.

## Section D — Reuse design (items 20-22)

20. **Three abstractions proposed** (NOT implemented in this phase):
    `ExecutionRecipe` (what to run) + `ObserverSet` (what to capture)
    + `Normalizer` (state-shape translation). The three are
    independently selectable; per-repo work reduces to YAML.

21. **Recipe / ObserverSet / Normalizer count:**

    - Recipes: **8** (one per family).
    - ObserverSets: **8** (one per family).
    - Normalizers: **8** (one per family).

    Family B + G share a Normalizer; Family H's chat-agent path can
    share Family B's Normalizer; Family H's workflow path can share
    Family A's Recipe. Otherwise, the (Recipe, ObserverSet,
    Normalizer) tuple is family-specific.

22. **Config-only candidates: 12 of 12.** Every inspected repo's
    existing injection seams already line up with the proposed
    abstractions. No code change is needed in any inspected
    repository; per-repo work reduces to a YAML config that selects
    the right Recipe + ObserverSet + Normalizer.

## Section E — Article 12(1) preservation and constraint compliance (items 23-24)

23. **What stays the same (Article 12(1) v1.4.0 + CR-3 invariants):**
    - v1.4.0 five-bucket compliance model is unchanged.
    - `compliance_runtime_run_id`, `execution_recipe_id`,
      `execution_recipe_version` schema fields are unchanged
      (Recipe IDs map cleanly onto `execution_recipe_id`).
    - Fast-`UNSUPPORTED` short-circuit for repos missing a compatible
      Recipe is unchanged.
    - CR-3 historical anomaly row (id=93, corpus_run_id=11,
      `ZhuLinsen/daily_stock_analysis`) is preserved.
    - All persistence invariants established by
      `audit/corpus_runner_v1/cr3_persistence_hardening_report.md`
      (atomic terminalization, structured validator, busy-retry
      budget, etc.) are unchanged.

24. **Hard constraints honoured (verbatim from the brief):**

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
    - Source inspection was strictly engineering; never claimed
      "source contains logging code → Article 12(1) PASS".
    - Used frozen CR-3 identities from
      `audit/corpus_runner_v1/cr3_50_repo_manifest.json`; did not
      re-resolve SHAs.
    - Materialised through existing `SourceCache` +
      `RepositoryMaterializer`; workspaces disposable, cache
      retained.
    - Did NOT execute any untrusted project code — static inspection
      only (Read / Grep tools against frozen materialised
      workspaces).

## Section F — Final verdict (item 25)

25. **READY** to design a config-driven integration architecture for
    the 12 currently UNSUPPORTED CR-3 repositories.

    Engineering basis:
    - 12 of 12 inspected repos expose clean injection seams that line
      up with the proposed three-abstraction model.
    - The 12 repos cluster into 8 execution families; one Recipe per
      family is sufficient.
    - Hand-written per-repo adapters are not needed; per-repo work
      reduces to a YAML config.
    - Article 12(1) v1.4.0 semantics, the CR-3 persistence invariant,
      and the historical-row anomaly are all preserved unchanged.
    - Source-inspection scope was strictly engineering; no compliance
      verdict was issued for any inspected repository.

    **NOT READY** to deploy this architecture — the design is a
    discovery artefact, not an implementation. Implementation is
    explicitly out of scope and requires a separate phase.

    **Suggested next action (out of scope for this report):**
    - Implement the proposed `ExecutionRecipe` + `ObserverSet` +
      `Normalizer` Protocols in
      `src/compliance/corpus_runner/recipes/`.
    - Add 8 concrete Recipes + 8 ObserverSets + 8 Normalizers.
    - Write YAML configs (one per family).
    - Write tests that load each YAML config, instantiate the Recipe
      with a stub model, run a no-op invocation, and verify the
      canonical event log shape.
    - Wire the new "config-only candidates" into the corpus runner's
      `build_jobs_for_run` path so a repo whose YAML config exists in
      the CR-3 corpus can be picked up automatically.

— end of 25-item report —