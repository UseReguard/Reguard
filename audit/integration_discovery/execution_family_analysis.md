# Execution-Family Analysis

**Date:** 2026-08-29
**Input artefact:** `repository_integration_matrix.md`
**Scope:** group the 12 inspected repos by *execution family* (the shape of
how work flows through the system), not by brand.

> **Hard constraint reminder.** Family classification is engineering
> analysis. A "family" tag is NOT a compliance classification. No row in
> this file implies any Article 12(1) outcome for the underlying
> repository.

---

## 1. Why "family" not "brand"

Two repos can be branded very differently and still share an execution
shape. Two repos with the same brand can have different execution shapes
(e.g., langchain core vs langgraph — both are "langchain-ai/" but langgraph
is the canonical graph runtime and langchain core is the chain/agent
factory). Family is the right axis for designing reusable adapters:

- A single **ExecutionRecipe** can in principle cover an entire family
  if its structural seams align.
- Cross-family reuse requires either (a) a bridge family at the Recipe
  layer, or (b) separate Observers / Normalizers per family.

The eight families below are non-overlapping. Every one of the 12 inspected
repos appears in exactly one family.

---

## 2. Family taxonomy (eight families)

### Family A — LangGraph state-graph family

| Members | langchain, langgraph, deer-flow |
|---|---|
| **Execution shape** | A `CompiledStateGraph` (LangChain v1 / langgraph) with a `messages` channel + custom reduced channels. The graph is built from `StateGraph(...).compile(checkpointer=...)` or from `langchain.agents.create_agent(model=..., tools=..., state_schema=...)` (which returns a `CompiledStateGraph`). Invocation is `.invoke({"messages": [...]}, config)` or `.astream(..., stream_mode=...)`. |
| **State channel** | `AgentState` / `MessagesState` TypedDict with annotated reducers (`add_messages`, custom `merge_*`). Persisted via LangGraph checkpointer (`MemorySaver`, `SqliteSaver`, `AsyncPostgresSaver`). |
| **Model injection seam** | `BaseChatModel` (LangChain core). LangChain's `init_chat_model` resolves string → provider. deer-flow's `create_chat_model` factory adds YAML-driven class resolution. |
| **Tool injection seam** | `langchain_core.tools.BaseTool` subclass — plain list argument to `create_agent(tools=...)`. No registry between harness and framework. |
| **Observability seam** | LangChain `BaseCallbackHandler` via `RunnableConfig["callbacks"]`. Tracing attached at graph invocation root in langgraph + deer-flow (so a single LangGraph run produces one trace with all node / LLM / tool calls as child spans). `astream_events(stream_mode="events")` is the event surface. |
| **Multi-agent shape** | langgraph: `StateGraph.add_node(..., <subgraph>)` nests another compiled graph as a node. deer-flow: explicit `task_tool` → `SubagentExecutor` that builds a fresh `create_agent(...)` per delegation. langchain: not first-class. |

**Structural seams (what a reusable ExecutionRecipe must speak):**

- `model: BaseChatModel`
- `tools: list[BaseTool]`
- `state: TypedDict` with `messages` + reducers
- `config: RunnableConfig` (with `configurable.thread_id` for checkpointer)
- `checkpointer: BaseCheckpointSaver`

**Reuse opportunity:** the three members differ in (i) which channels
are on the state, (ii) which tools are wired, (iii) which middlewares wrap
the graph. They are essentially the same execution family with three
config-only variations. A **LangGraph-family Recipe** would cover all
three with config rather than code.

---

### Family B — Single-agent toolkit family

| Members | agentscope, agno |
|---|---|
| **Execution shape** | One `Agent` object owns its `model`, `toolkit`/`tools`, and `state`. `await agent.reply(message)` / `async for event in agent.reply_stream(message)` (agentscope) or `agent.run(message)` / `await agent.arun(message)` (agno). Optional multi-agent via `GoalPipeline(executor, verifier)` in agentscope (verifier-loop pattern). |
| **State channel** | agentscope: `AgentState` pydantic with `context: list[Msg]`, `summary`, `permission_context`, `tool_context` (`activated_groups`), `tasks_context`. Persistence via `StorageBase` — `AsyncSQLAlchemyStorage` (SQLite / aiosqlite / asyncpg / aiomysql with Alembic) or `RedisStorage`. agno: pluggable `storage=` (in-memory / sqlite / postgres). |
| **Model injection seam** | agentscope: `ChatModelBase` abstract + 8 concrete providers (`OpenAIChatModel`, `AnthropicChatModel`, `DashScopeChatModel`, ...). agno: framework-internal model registry (string → provider). |
| **Tool injection seam** | agentscope: `ToolBase` + `Toolkit(tools=[...])`. agno: plain python functions with `@tool` decorator, passed as list to `Agent(tools=[...])`. |
| **Observability seam** | agentscope: rich `AgentEvent` async stream (`ReplyStartEvent`, `ModelCallStartEvent`, `TextBlockDeltaEvent`, `ToolCallDeltaEvent`, `ToolResultStartEvent`, `ThinkingBlock*`, `RequireUserConfirmEvent`, ...) + 7 middleware hooks (`on_reply`, `on_reasoning`, `on_check_permission`, `on_acting`, `on_model_call`, `on_compress_context`, `on_system_prompt`) + OpenTelemetry `TracingMiddleware`. agno: no first-party; relies on provider OTel. |
| **Multi-agent shape** | agentscope: `GoalPipeline(executor, verifier, max_iters=10)`. agno: per-agent `team=` group but no built-in pipeline. |

**Structural seams:**

- `model: ChatModelBase` (agentscope) or framework-internal model id (agno)
- `toolkit: Toolkit` (agentscope) or `tools: list[callable]` (agno)
- `state: AgentState` (pydantic, JSON-serialisable)
- `storage: StorageBase | None`
- `event_stream: AsyncGenerator[AgentEvent]`

**Reuse opportunity:** agentscope's `Toolkit.call_tool(...)` is a single
dispatch point; agno's per-tool decorator is a flat list. The state
shapes are similar enough (pydantic with serialisable fields) that a
**Single-Agent-Toolkit Recipe** could capture both — but only after a
small bridge (the framework-specific chat-model class).

---

### Family C — Role-orchestration family

| Members | crewAI, MetaGPT |
|---|---|
| **Execution shape** | Roles are first-class agents with `goal`, `backstory`, `tools=[...]`. A `Crew` (crewAI) or `Team` (MetaGPT) orchestrates multiple roles through `kickoff(inputs)` or `team.run(idea)`. Process is sequential / hierarchical (crewAI) or managed by a `TeamLeader` "Mike" (MetaGPT's MGXEnv). |
| **State channel** | crewAI: in-process per `kickoff()` call; optional `memory=` (short / long / entity / external). MetaGPT: `MGXEnv.history` records published messages; per-role `Role.rc.memory` keeps context; routing via `MESSAGE_ROUTE_TO_ALL` (`"all"`) or `set(direct_chat_roles)`. |
| **Model injection seam** | crewAI: `llm=` (string or `BaseLLM`); wrapper at `crewai/llm.py` resolves string → LiteLLM by default. MetaGPT: **global config-based** — `config/config2.yaml` defines `llm.api_type / model / base_url / api_key`; loaded into `LLMConfig` (`metagpt/configs/llm_config.py:59-61`); consumed by `BaseLLM.aask()`; tests `mocker.patch("metagpt.provider.base_llm.BaseLLM.aask", llm.aask)` (`conftest.py:65-67`). |
| **Tool injection seam** | crewAI: `crewai.tools.BaseTool` plain list on `Agent(tools=[...])`. MetaGPT: `Action` subclasses registered via `role.set_actions([...])` (`metagpt/roles/role.py`). |
| **Observability seam** | crewAI: `token_usage_callback` + optional `Opik` / `Langfuse` / `MLflow` / `AgentOps` trackers. MetaGPT: rich console via `metagpt/logs.py` + `subscription.subscribe(role, trigger, callback)` for async callbacks on role responses (`metagpt/subscription.py:25-30, 44-63`). |
| **Multi-agent shape** | Crew + process; Team + Leader. |

**Structural seams:**

- `roles: list[Agent]` with `(role, goal, backstory, llm, tools)`
- `process: "sequential" | "hierarchical"` (crewAI) or `Leader`-based (MetaGPT)
- `tasks: list[Task]` with assigned `agent`
- per-role memory; per-crew / per-team message history

**Reuse opportunity:** the two members look superficially similar but
have divergent model-injection seams (string → LiteLLM vs YAML-driven
BaseLLM) and divergent action-vs-tool semantics. A **Role-Orchestration
Recipe** is feasible for the workflow shell (Crew / Team → kickoff /
run → result) but the inner model and tool wiring must be family-specific
adapters. This is one Recipe with two **Normalizers**.

---

### Family D — Pipeline-DAG family

| Members | haystack |
|---|---|
| **Execution shape** | `Pipeline().add_component("name", MyComponent())` builds a DAG of `@component`-decorated classes. `pipeline.run({"comp1": {"input": ...}})` returns a dict of named outputs. There is no "agent" concept — only components that consume input sockets and produce output sockets. |
| **State channel** | Pipeline state is the per-run dict flowing between components. No built-in cross-run persistence in core. |
| **Model injection seam** | `ChatGenerator` subclasses (`OpenAIChatGenerator`, `AzureOpenAIChatGenerator`, `OpenAIResponsesChatGenerator`, `AzureOpenAIResponsesChatGenerator`, `LLM`, `MockChatGenerator`) — lazy-imported via `_import_structure` in `__init__.py`. |
| **Tool injection seam** | `Component` Protocol — any class with `run(*args, **kwargs) -> Mapping[str, Any]`. The pipeline wires components by name + socket compatibility. |
| **Observability seam** | Lazy-imported `tracing.tracer.ff_tracer` / `content_tracer`; standard `logger`. |
| **Multi-agent shape** | None — DAG. |

**Structural seams:**

- `components: dict[str, Component]` (name → instance)
- `connections: list[(src, src_socket, dst, dst_socket)]`
- `run_inputs: dict[str, dict]`

**Reuse opportunity:** Haystack is structurally different from every
other family. It has no agent loop, no tool-call loop, no state channel.
A reusable Recipe would need to map *Article 12(1) "automatic event
logging"* onto pipeline-component execution traces. The seams (component
name, socket names, run input/output dicts) are clean. This is a
**Pipeline Recipe** that produces structured events from per-component
`run()` invocations.

---

### Family E — Long-running CLI-loop family

| Members | AutoGPT |
|---|---|
| **Execution shape** | `await agent.propose_action()` / `await agent.execute(proposal)` are exposed as **two separate calls** rather than one `run()`. The process is meant to run indefinitely in a CLI loop driven by command queues — not single-shot. `Agent(propose_action → execute → propose → execute → ...)` repeats until termination. |
| **State channel** | `AgentSettings` (pydantic) + `EpisodicActionHistory[AnyActionProposal]`; filesystem-backed via `FileStorage` (`autogpt/file_storage/`). |
| **Model injection seam** | `MultiProvider` factory (`autogpt/llm/providers/multi.py`); LLM resolved per call by `MultiProvider.create_chat_completion(...)` (`agent.py:357-366`). **ReWOO bypass** (`agent.py:312-326`) means LLM calls can be skipped if ReWOO has cached an action — adds a phase-aware skip path. |
| **Tool injection seam** | `Command` subclasses registered through `CommandProvider.get_commands`; permission manager (`CommandPermissionManager.check_command`) gates execution (`agent.py:387-400`). |
| **Observability seam** | `logger = logging.getLogger(__name__)`; Sentry SDK via `sentry_sdk.capture_exception` (`agent.py:417`); component-level trace dumps (`logger.debug(f"Executing prompt:\n{dump_prompt(prompt)}")` line 335). |
| **Multi-agent shape** | `DefaultAgentFactory` creates sub-agents (`agent_factory/default_factory.py`); recursion depth tracked via `ExecutionContext.depth`. |

**Structural seams:**

- `propose_action() -> AnyActionProposal`
- `execute(proposal, user_feedback="") -> ActionResult`
- `AgentSettings.history: EpisodicActionHistory`
- `permission_manager: CommandPermissionManager | None`

**Reuse opportunity:** the loop is structurally different from the
"single-shot invoke + return" shape assumed by most other families. A
**Long-Running-Loop Recipe** must drive the loop externally — propose,
record, execute, record, observe — and only the inner propose / execute
calls are reusable across runs. This is one of the few repos where the
Recipe shape itself diverges.

---

### Family F — Browser-runtime family

| Members | browser-use |
|---|---|
| **Execution shape** | `Agent(task, llm, browser_session=...)` then `await agent.run(max_steps=500)` returns `AgentHistoryList[AgentStructuredOutput]`. Loop is bounded by `max_steps` and ends when `history.is_done()`. **Browser is mandatory** — agent's state is the live browser handle. |
| **State channel** | `Agent.state` (BrowserState / state.n_steps / consecutive_failures / last_result); `BrowserSession` keeps live browser handle (CDP / Playwright); optional `save_conversation_path` filesystem save (`service.py:1720-1729`). |
| **Model injection seam** | `BaseChatModel` subclass via constructor arg `llm=`. Same as LangChain family at the model layer. |
| **Tool injection seam** | **`Controller` registry with `@controller.action(...)` decorator** — each browser action is a method on `Controller` (`controller/service.py`). Tools are *not* plain instances — they are registered through a class that wraps parameter models. |
| **Observability seam** | First-party `ProductTelemetry` (`AgentTelemetryEvent` with task, model, steps, urls_visited, success, judge_verdict) — opt-out via env var (`service.py:2214-2246`). |
| **Multi-agent shape** | None — single agent. |

**Structural seams:**

- `controller: Controller` (custom registry, not a list)
- `task: str`
- `browser_session: BrowserSession`
- `max_steps: int`
- `agent.run(max_steps=...) -> AgentHistoryList`

**Reuse opportunity:** the LLM surface is shared with Family A
(LangChain-family chat models). The tool surface is wholly divergent
(`Controller` registry instead of `BaseTool` list). A **Browser-Runtime
Recipe** is the most divergent of the eight families; it needs its own
Observer (for browser navigations / actions / screenshots) and its own
Normalizer (for the `ActionResult` / `ActionErrorResult` flow).

---

### Family G — Runner + SessionService family

| Members | adk-python |
|---|---|
| **Execution shape** | `LlmAgent(name, model, instruction, tools=[...])` → `Runner(agent, app_name, session_service=...)` → `async for event in runner.run_async(user_id, session_id, new_message)`. The `Runner` decouples agent invocation from session persistence. |
| **State channel** | `SessionService` (`BaseSessionService` + `InMemorySessionService`, `SqliteSessionService` (aiosqlite), `VertexAI SessionService`); `Session` with `events: list[Event]`; `state: dict` per session. |
| **Model injection seam** | `model: Union[str, BaseLlm]`; str resolved via `LiteLlm` (litellm wrapper) — multi-provider; Google-specific `google_llm.Gemini`; `AnthropicLlm` via env (`models/anthropic_llm.py`); env-var API keys for `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `VERTEXAI_PROJECT` etc. |
| **Tool injection seam** | `BaseTool` + `BaseToolset` (async `get_tools()` protocol at `tools/base_toolset.py:88-127`); `FunctionTool` for python functions; `McpToolset`; `tool_name_prefix` for grouping (`base_toolset.py:103-166`). |
| **Observability seam** | `BigQueryAgentAnalyticsPlugin` (`plugins/bigquery_agent_analytics_plugin.py:46`); standard `logger`; `ADK_MAX_LLM_CALLS` env-var knob. |
| **Multi-agent shape** | Sub-agents: `LlmAgent(sub_agents=[...])`; `SequentialAgent`, `ParallelAgent`, `LoopAgent` for orchestration. |

**Structural seams:**

- `agent: BaseAgent` (LlmAgent / SequentialAgent / ParallelAgent / LoopAgent)
- `runner: Runner(agent, session_service)`
- `session_service: BaseSessionService`
- `tools: list[BaseTool | BaseToolset]`
- `session_id, user_id, app_name, new_message`
- `run_async(...) -> AsyncGenerator[Event]`

**Reuse opportunity:** adk-python's `Runner` / `SessionService` / `Event`
trio is the cleanest persistence + event surface in the entire sample
(except agentscope, which it closely resembles). It is functionally
adjacent to Family B but with a separate tool abstraction. A
**Runner-SessionService Recipe** could cover both B and G with a
Normalizer that bridges `Toolkit.call_tool(...)` to `BaseToolset.get_tools()`.

---

### Family H — Workflow-builder family

| Members | microsoft/agent-framework |
|---|---|
| **Execution shape** | **Two execution shapes coexist.** `ChatAgent(chat_client=..., instructions=..., tools=[...])` for chat-agent; `WorkflowBuilder().set_start_executor(...).add_edge(...).build()` for graph workflows. `await agent.run(message, thread=...)` for chat agents; workflow executors handle events. |
| **State channel** | `AgentThread` for chat agents; per-workflow state machine for workflows; optional persistence via `RedisStateStore` (`packages/redis/`). |
| **Model injection seam** | `ChatClient` abstract base class; concrete clients `OpenAIChatClient`, `AnthropicChatClient`, `AzureAIAgent`, `OllamaChatClient`, `GeminiChatClient`, `MistralChatClient`, `BedrockChatClient`, `FoundryChatClient`, etc. |
| **Tool injection seam** | `ai_function` decorator → `AIFunction`; passed as list to `ChatAgent(tools=[...])`. Tools are first-class schemas + invocation handlers, not framework subclasses. |
| **Observability seam** | OpenTelemetry spans per agent invocation; standard `logger`; some packages include `tracing/` modules. |
| **Multi-agent shape** | Workflow builder (`WorkflowBuilder`); sub-graphs via `add_edge`/`set_start_executor`/`set_next_executor`. |

**Structural seams:**

- `chat_client: ChatClient` (for chat agents)
- `tools: list[AIFunction]` (for chat agents)
- `executor: Executor` (for workflows)
- `WorkflowBuilder` + `add_edge` / `set_start_executor` / `build()`
- `AgentThread` (per-conversation)

**Reuse opportunity:** microsoft/agent-framework is structurally similar
to Family A (graph workflows are graph-shaped) and Family B (chat
agents are toolkit-shaped). The tool abstraction (`AIFunction`) is
reminiscent of `BaseTool` but is a dataclass, not a framework subclass.
A **Workflow-Builder Recipe** could share the Family A skeleton (graph)
and the Family B skeleton (chat-agent) with different seams.

---

## 3. Cross-family structural map

| Concern | A (LG-state) | B (toolkit) | C (role) | D (DAG) | E (CLI-loop) | F (browser) | G (runner) | H (workflow) |
|---|---|---|---|---|---|---|---|---|
| One-shot `run(...) -> result`? | ✓ | ✓ | ✓ | ✓ | ✗ (loop) | ✓ | ✓ (async gen) | ✓ (chat) / ✗ (workflow stream) |
| Tool list argument | ✓ | ✓ | ✓ | n/a (component) | ✓ (`Command`) | ✗ (`Controller`) | ✓ | ✓ |
| Pluggable persistence | ✓ (checkpointer) | ✓ (`Storage`) | partial (`memory=`) | ✗ | ✓ (`FileStorage`) | optional (`save_conversation_path`) | ✓ (`SessionService`) | ✓ (`AgentThread`) |
| Async event stream | ✓ (`astream_events`) | ✓ (`AgentEvent`) | partial (`subscribe`) | ✗ | partial (`trace dump`) | partial (telemetry) | ✓ (`Event`) | ✓ (`ExecutorEvent`) |
| Multi-agent primitive | subgraph | `GoalPipeline` | `Crew` / `Team` | n/a | `AgentFactory` | n/a | `Sequential/Parallel/LoopAgent` | `WorkflowBuilder` |
| LLM protocol | `BaseChatModel` | `ChatModelBase` (or framework-internal) | `BaseLLM` (LiteLLM-wrapped) or `LLMConfig` global | `ChatGenerator` | `MultiProvider` | `BaseChatModel` | `BaseLlm` | `ChatClient` |

---

## 4. Reuse potential (per family)

| Family | Reuse Recipe? | Estimated config-only candidates (out of 12) | Comment |
|---|---|---|---|
| A — LangGraph-state | **YES** — single Recipe | 3 (langchain, langgraph, deer-flow) | Differences are channels, tools, middlewares — config-shaped |
| B — Single-agent toolkit | **YES** — single Recipe with chat-model Normalizer | 2 (agentscope, agno) | Toolkit/agent shape differs (Toolkit vs flat list); Normalizer needed |
| C — Role-orchestration | **YES** — single Recipe with two Normalizers | 2 (crewAI, MetaGPT) | Inner model + action/tool semantics diverge |
| D — Pipeline-DAG | **YES** — single Recipe, divergent event model | 1 (haystack) | No tool loop; traces are per-component |
| E — CLI-loop | **YES, divergent shape** — Recipe drives loop | 1 (AutoGPT) | Loop shape differs from single-shot |
| F — Browser-runtime | **YES, divergent tool model** | 1 (browser-use) | `Controller` registry instead of tool list |
| G — Runner-SessionService | **YES** — adjacent to Family B | 1 (adk-python) | Almost identical to B but separate BaseTool / SessionService seam |
| H — Workflow-builder | **YES** — adjacent to A and B | 1 (microsoft/agent-framework) | Coexists; covers both chat-agent and workflow-shape |

**Tally — config-only candidates:**

- A single Recipe covers ~3 repos.
- B + G together cover ~3 repos with one Normalizer bridge.
- C covers ~2 repos with two Normalizers.
- D, E, F, H each cover 1 repo (Recipe + family-specific Observer / Normalizer).

Roughly **7 of 12** inspected repos fit into one of three Recipes with
Normalizers; the remaining 5 need family-specific Recipes.

---

## 5. What "family" deliberately ignores

- **Stars and downloads** — engineering shape, not popularity.
- **Brand history** — langchain and langgraph share a brand but are in
  the same family; crewAI and MetaGPT are different brands but the same
  family. Brand is irrelevant.
- **License** — out of scope for this engineering analysis (but Apache /
  MIT-dominant across the sample).
- **Python version** — `requires-python` ranges span 3.10-3.14 across
  the sample, but this is a deployment concern (handled by the
  runtime's interpreter selection, not the Recipe shape).

---

## 6. Constraint compliance

- Did NOT issue compliance verdicts for any inspected repository.
- Did NOT modify any third-party repository.
- Source inspection only — no execution.
- Family classification is engineering analysis, not compliance
  classification.

— end of family analysis —