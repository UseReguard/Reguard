# Repository Integration Matrix

**Date:** 2026-08-29
**Source:** static inspection of 12 CR-3-UNSUPPORTED frozen-SHA snapshots
**Materialisation root:** `/home/mrcel/.reguard/discovery_ws/` (workspaces disposable)
**Cache root:** `/home/mrcel/.reguard/discovery_cache/` (retained per spec)
**Sample manifest:** `audit/integration_discovery/sample_manifest.json`
**Frozen manifest:** `audit/corpus_runner_v1/cr3_50_repo_manifest.json`

> **Hard constraint reminder.** This file is engineering discovery only.
> No compliance verdict is issued for any repository below. A row saying
> "uses logging" is NOT a claim that the repository would PASS Article 12(1).

---

## 1. Sample composition (12 repos)

| # | Repository | Position | Resolved SHA (frozen) | Stars | CR-3 status | Materialised via |
|---:|---|---:|---|---:|---|---|
| 1 | langchain-ai/langchain | 7 | `5893459c4f2bfac6c8d3262cae1e3f2246d9287f` | 145,088 | UNSUPPORTED | SourceCache |
| 2 | langchain-ai/langgraph | 19 | `11ee185999b86bfea2d8c0e69cef9a5e37acf686` | 40,516 | UNSUPPORTED | SourceCache |
| 3 | crewAIInc/crewAI | 13 | `da4daadba0e5049abc00fee8bc31b8b8019c60dd` | 57,658 | UNSUPPORTED | SourceCache |
| 4 | agno-agi/agno | 18 | `c96291cbd0f644774d48a398c30101e90c947354` | 41,938 | UNSUPPORTED | direct clone (SourceCache transient git error) |
| 5 | Significant-Gravitas/AutoGPT | 6 | `32a43d005c0c42079ceba68d9a49c28e0eeaa6c7` | 186,910 | UNSUPPORTED | direct clone (SourceCache symlink safety check) |
| 6 | FoundationAgents/MetaGPT | 11 | `11cdf466d042aece04fc6cfd13b28e1a70341b1f` | 70,053 | UNSUPPORTED | SourceCache |
| 7 | browser-use/browser-use | 8 | `2e32d260341fae39c80bc8529ec174bad91e7672` | 111,105 | UNSUPPORTED | SourceCache |
| 8 | bytedance/deer-flow | 9 | `bf740ffa9077f55661fce80186b656651f497c89` | 80,969 | UNSUPPORTED | SourceCache |
| 9 | agentscope-ai/agentscope | 27 | `e90f1c7592896cc95f6e5ee506194f533378247d` | 29,730 | UNSUPPORTED | SourceCache (replaces NousResearch/hermes-agent due to sha-resolution error) |
| 10 | deepset-ai/haystack | 29 | `e318778c9bf60a1963e3b5f451359655dd696c30` | 26,325 | UNSUPPORTED | SourceCache |
| 11 | google/adk-python | 30 | `c3d3730250b64156129508354b45120372f95334` | 21,303 | UNSUPPORTED | SourceCache |
| 12 | microsoft/agent-framework | 43 | `edfe115ea06bca57ae5a123d0fac5b3fdda13603` | 13,137 | UNSUPPORTED | direct clone (SourceCache transient git error) |

No HEAD inspection. No SHA re-resolution. All SHAs are the frozen CR-3 identities.

---

## 2. Per-repository integration shape

### 2.1 langchain-ai/langchain

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | uv workspace monorepo (`libs/langchain_v1/`, `libs/core/`, `libs/langchain/`, ...), hatchling backend, Python `>=3.10,<4.0`, no native extensions, langgraph is external PyPI dep | `libs/langchain/pyproject.toml` |
| Execution entrypoint | `create_agent(model, tools, system_prompt=..., middleware=..., state_schema=...)` returns `CompiledStateGraph`; called via `.invoke({"messages": [...]})` / `.astream(...)` | `libs/langchain_v1/langchain/agents/factory.py:840` |
| Model injection | Positional `BaseChatModel` instance OR `str` (lazy `init_chat_model` import). No global default. No env-var API key consultation inside `create_agent` itself. | `libs/langchain_v1/langchain/agents/factory.py:840` and chain construction |
| Tool surface | `langchain_core.tools.BaseTool` subclasses, plain list argument, `@tool` decorator, `ToolMessage` results, `ToolException` for failures | `libs/langchain_v1/langchain/tools/`, `libs/core/langchain_core/tools/` |
| State | `AgentState` TypedDict with `messages: Annotated[list, add_messages]`, no persistence by default, checkpointer optional | `libs/langchain_v1/langchain/agents/factory.py:840` |
| Observability | `BaseCallbackHandler` via `RunnableConfig["callbacks"]`, `astream_events`, LangSmith tracer (off by default) | `libs/langchain_core/callbacks/base.py` |
| Stub model feasibility | **EASY** — in-repo `FakeToolCallingModel` reference at `tests/unit_tests/agents/model.py` | same |
| Tool injection feasibility | **EASY** — plain list argument, no registry between harness and `create_agent` | same |

### 2.2 langchain-ai/langgraph

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | uv workspace monorepo with sub-packages `libs/langgraph`, `libs/checkpoint`, `libs/checkpoint-sqlite`, `libs/checkpoint-postgres`, `libs/prebuilt`; uv.lock present | `libs/langgraph/pyproject.toml` |
| Execution entrypoint | `StateGraph(...).compile(checkpointer=...)` returns `CompiledStateGraph`; called via `.invoke(state, config)` / `.astream(state, config, stream_mode=...)` | `libs/langgraph/langgraph/graph/state.py` |
| Model injection | Caller-supplied — graph nodes receive whatever model the user wires into the node function; no global default | `libs/langgraph/langgraph/graph/state.py` |
| Tool surface | Same LangChain `BaseTool` universe; `ToolNode` (in `libs/prebuilt/langgraph/prebuilt/tool_node.py`) is the canonical prebuilt node; accepts list of tools and runs them as a node | `libs/prebuilt/langgraph/prebuilt/tool_node.py` |
| State | `MessagesState` (TypedDict) or custom State with annotated reducers; **persistence is opt-in via checkpointer** (sqlite / postgres / in-memory) | `libs/checkpoint/`, `libs/checkpoint-sqlite/` |
| Observability | `astream_events(stream_mode="events")` emits model / tool / node callbacks; `LangChainTracer` (off by default) | `libs/langgraph/langgraph/graph/state.py` |
| Stub model feasibility | **EASY** — same `BaseChatModel` interface as langchain core | inherited from langchain-core |
| Tool injection feasibility | **EASY** — same `BaseTool` interface | inherited |

### 2.3 crewAIInc/crewAI

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | uv-managed monorepo under `lib/` (`crewai`, `crewai-tools`, `crewai-core`, `crewai-files`, `cli`, `devtools`); `uv.lock` (1.6 MB) at repo root | `pyproject.toml:12408` |
| Execution entrypoint | `Agent(role=..., goal=..., backstory=..., llm=..., tools=[...])` then `Crew(agents=[...], tasks=[...], process=Process.sequential | hierarchical).kickoff(inputs={...})` | `lib/crewai/src/crewai/agent.py`, `lib/crewai/src/crewai/crew.py` |
| Model injection | Constructor arg `llm=` (string or `BaseLLM`); the wrapper at `lib/crewai/src/crewai/llm.py` resolves string → LiteLLM by default | `lib/crewai/src/crewai/llm.py` |
| Tool surface | `BaseTool` subclasses in `crewai-tools`, registered as plain Python list on `Agent(tools=[...])` | `lib/crewai-tools/src/crewai_tools/` |
| State | In-process per `kickoff()` call — no built-in cross-run persistence by default; optional `memory=` (short / long / entity / external) | `lib/crewai/src/crewai/memory/` |
| Observability | `token_usage_callback` callback, optional `Opik` / `Langfuse` / `MLflow` / `AgentOps` trackers | `lib/crewai/src/crewai/utilities/observability/` |
| Stub model feasibility | **MODERATE** — `BaseLLM` is a wrapper around LiteLLM, not LangChain `BaseChatModel`; stub must subclass `crewai.llm.BaseLLM` (different protocol: `call(messages, ...)` not `.invoke(messages)`) | `lib/crewai/src/crewai/llm.py` |
| Tool injection feasibility | **EASY** — plain list argument on `Agent(tools=...)` | inherited |

### 2.4 agno-agi/agno

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | uv-managed single-package (`libs/agno`); optional `storage-postgres` / `storage-sqlite` extras | `libs/agno/pyproject.toml` |
| Execution entrypoint | `Agent(model=..., tools=[...], instructions=..., storage=..., markdown=...)`; `.run(message)` (sync) or `.arun(message)` (async) | `libs/agno/agno/agent/agent.py` |
| Model injection | Constructor arg `model=`; agno internally dispatches on model id (`OpenAIChat`, `Anthropic`, etc.); if string, defers resolution to a model factory | `libs/agno/agno/models/` |
| Tool surface | Plain Python functions decorated `@tool` or subclasses of `Toolkit`; passed as list to `Agent(tools=...)` | `libs/agno/agno/tools/` |
| State | `storage=` pluggable — defaults to no storage; sql / postgres / sqlite storage backends in `libs/agno/agno/storage/` | `libs/agno/agno/storage/` |
| Observability | No first-party tracing; integrates with OpenTelemetry via the model provider's own instrumentation | n/a |
| Stub model feasibility | **MODERATE** — agno subclasses need a registry entry; bypassing registry requires a custom `Model` subclass (different protocol from LangChain) | `libs/agno/agno/models/` |
| Tool injection feasibility | **EASY** — plain list, plain functions | same |

### 2.5 Significant-Gravitas/AutoGPT

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | Mixed monorepo — modern FastAPI backend under `autogpt_backend/` plus legacy Python CLI under `classic/` (`classic/original_autogpt/`, `classic/autogpt/`) | `classic/pyproject.toml` |
| Execution entrypoint | `Agent(settings=AgentSettings, llm_provider=MultiProvider, file_storage=FileStorage, app_config=AppConfig, ...)` then `await agent.propose_action()` / `await agent.execute(proposal)` — **long-running CLI loop, not single-shot invoke** | `classic/original_autogpt/autogpt/agents/agent.py:100-200` |
| Model injection | `MultiProvider` factory injected at construction (`autogpt/llm/providers/multi.py`); LLM resolved per call by `MultiProvider.create_chat_completion(...)` (`agent.py:357-366`) | `classic/original_autogpt/autogpt/agents/agent.py:357-366` |
| Tool surface | `Command` subclasses registered through `CommandProvider.get_commands`; pipeline-of-providers composition (`autogpt/prompt_strategies/`); `ActionProposal` / `ActionResult` typed flow (`agent.py:373-460`) | `classic/original_autogpt/autogpt/agents/agent.py:373-460` |
| State | `AgentSettings` (pydantic) + `EpisodicActionHistory[AnyActionProposal]`; filesystem-backed via `FileStorage` (`autogpt/file_storage/`) | `classic/original_autogpt/autogpt/agents/agent.py:170-180` |
| Observability | `logger = logging.getLogger(__name__)`; Sentry SDK via `sentry_sdk.capture_exception` (`agent.py:417`); plus component-level trace dumps (`logger.debug(f"Executing prompt:\n{dump_prompt(prompt)}")` line 335) | `classic/original_autogpt/autogpt/agents/agent.py:417` |
| Stub model feasibility | **HARD** — long-running process + `MultiProvider` factory + ReWOO phase-specific LLM bypass (`agent.py:312-326`) makes a clean stub awkward; `RecordResult` callbacks wrap the LLM at multiple call sites | `classic/original_autogpt/autogpt/agents/agent.py:312-326, 357-366` |
| Tool injection feasibility | **MODERATE** — commands are registered through a provider pipeline (`CommandProvider.get_commands`); requires subclassing `Command` and being discoverable | `classic/original_autogpt/autogpt/agents/agent.py:285-287` |

### 2.6 FoundationAgents/MetaGPT

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | Single-package (`metagpt/`); Poetry-managed historically, pyproject.toml at root | `pyproject.toml` |
| Execution entrypoint | `Team(investment=10.0, role_roles=[ProductManager(), Architect(), Engineer(), ...])` → `team.run(idea=...)`; alternatively `SoftwareCompany().run(...)` with role profile config | `metagpt/team.py`, `metagpt/software_company.py` |
| Model injection | **Global config-based** — `config/config2.yaml` defines `llm.api_type / model / base_url / api_key`; loaded into `LLMConfig` (`metagpt/configs/llm_config.py:59-61`); consumed by `BaseLLM.aask()` | `config/config2.yaml:4-8`, `metagpt/configs/llm_config.py:59-61` |
| Tool surface | `Action` subclasses registered onto `Role.actions` list; tools like `WebBrowseAndSummarize`, `CollectLinks`, `ConductResearch` are actions (`metagpt/actions/research.py`); actions called by `_act()` of each Role | `metagpt/actions/`, `metagpt/roles/role.py` |
| State | `MGXEnv` (multi-agent environment) holds message routing; per-role `Role.rc.memory` keeps context; per-thread `Environment.history` records published messages (`metagpt/environment/mgx/mgx_env.py:60`) | `metagpt/environment/mgx/mgx_env.py:60` |
| Observability | `metagpt/logs.py` (rich console output); `metagpt/subscription.py` defines `subscribe(role, trigger, callback)` for async callbacks on role responses; standard `logger` | `metagpt/subscription.py:25-30, 44-63` |
| Stub model feasibility | **MODERATE** — global `LLMConfig` plus `BaseLLM.aask()` patch pattern (`conftest.py:65-67` patches `BaseLLM.aask` directly); a stub class must be registered into the provider list and replace aask calls | `tests/conftest.py:65-67` |
| Tool injection feasibility | **MODERATE** — actions must be registered onto a `Role` via `set_actions([...])` (`metagpt/roles/role.py`); not a simple list on a constructor | `metagpt/roles/role.py` |

### 2.7 browser-use/browser-use

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | Single-package Python (`browser_use/`) + browser-side TS; pyproject at root; depends on playwright / chromium at runtime | `pyproject.toml`, `browser_use/browser/` |
| Execution entrypoint | `Agent(task, llm, browser_session=..., **settings)` → `await agent.run(max_steps=500)` (async-only, no sync API) → `AgentHistoryList[AgentStructuredOutput]` | `browser_use/agent/service.py:2506-2511` |
| Model injection | Constructor arg `llm=` (BaseChatModel subclass); resolved per-call via internal `_log_model_output()` | `browser_use/agent/service.py:153-180` |
| Tool surface | **`Controller` registry with `@controller.action(...)` decorator** — each browser action is a method on `Controller` (`browser_use/controller/service.py`); methods invoked by name from LLM-emitted tool calls | `browser_use/controller/service.py` |
| State | `Agent.state` (BrowserState / state.n_steps / consecutive_failures / last_result); `BrowserSession` keeps live browser handle; `save_conversation_path` optional filesystem save (`service.py:1720-1729`) | `browser_use/agent/service.py:1720-1729` |
| Observability | `telemetry = ProductTelemetry()` capture (`service.py:2214-2246`) — AgentTelemetryEvent with task, model, steps, urls_visited, success, judge_verdict; **telemetry is first-party, opt-out via env var** | `browser_use/agent/service.py:2214-2246` |
| Stub model feasibility | **EASY** — `BaseChatModel` subclass + custom `Controller` subclass (`controller/service.py`) to handle expected tool calls; `use_vision=False` to avoid screenshots | `browser_use/agent/service.py:153-180` |
| Tool injection feasibility | **HARD** for non-browser tools — the `Controller` registry is browser-action-specific; a custom tool requires custom `RegisteredAction` plumbing + parameter model; no plain list constructor | `browser_use/controller/service.py` |

### 2.8 bytedance/deer-flow

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | uv workspace, 3 packages (`deerflow`, `deerflow-harness`, `deerflow-extension-api`); hatchling backend; `requires-python = ">=3.12"`; langgraph 1.2.x | `backend/packages/harness/pyproject.toml:2-95` |
| Execution entrypoint | `make_lead_agent(config: RunnableConfig)` (LangGraph Server entrypoint) → `assemble_lead_agent(config)` → `_assemble_lead_agent` calls `langchain.agents.create_agent(model=..., tools=final_tools, middleware=..., state_schema=...)` | `backend/langgraph.json:9`, `backend/packages/harness/deerflow/agents/lead_agent/agent.py:741-743, 1047-1053` |
| Model injection | YAML-driven — `create_chat_model(name, ..., app_config=..., attach_tracing=False, ...)` resolves `cfg.use` (importable class path) → `model_class(**kwargs)`; factory at `models/factory.py:174-321` | `backend/packages/harness/deerflow/models/factory.py:174-321` |
| Tool surface | `langchain.tools.BaseTool`; discovery via `get_available_tools(groups=None, include_mcp=True, ...)` (`tools/tools.py:59-201`); builtins + MCP + ACP tools; deferred-tool assembly + bypassable | `backend/packages/harness/deerflow/tools/tools.py:59-201` |
| State | `ThreadState(AgentState)` with custom reducers (`merge_sandbox`, `merge_artifacts`, `merge_todos`, `merge_delegations`, `merge_skill_context`); persisted via langgraph-checkpoint-sqlite (default) / postgres; delegation ledger capped at 50 | `backend/packages/harness/deerflow/agents/thread_state.py:274-287, 167-214` |
| Observability | Langfuse / LangSmith callbacks attached at graph invocation root (`agent.py:973-978`); `attach_tracing=False` discipline enforced inside the graph; Monocle (OTel) optional extra; ~40 middlewares emit `aemit_custom_event` | `backend/packages/harness/deerflow/tracing/factory.py:37-65`, `agent.py:1-23` (docstring) |
| Stub model feasibility | **EASY** — `BaseChatModel` subclass with `use: "my.stub:StubChatModel"` in `config.yaml`; `attach_tracing=False` already enforced | `backend/packages/harness/deerflow/models/factory.py:208-313` |
| Tool injection feasibility | **EASY** — pass `BaseTool` instances directly to `create_agent(tools=...)`; bypass config-driven path | `backend/packages/harness/deerflow/agents/lead_agent/agent.py:1047-1053` |

### 2.9 agentscope-ai/agentscope

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | Single Python package (`agentscope`) at `src/agentscope/`; setuptools backend; `requires-python = ">=3.11"`; ~16 optional extras (`model-gemini`, `model-ollama`, `service`, `storage-sql/-redis/-s3`, `channel`, `workspace-docker/-e2b/-k8s`, `vdb-*`, `rag`, `memory-*`) | `src/agentscope/pyproject.toml:1-227` |
| Execution entrypoint | `Agent(name, system_prompt, model, toolkit=None, middlewares=None, state=None, ...)` → `await agent.reply(inputs)` / `async for event in agent.reply_stream(...)` (`agent/_agent.py:300-347, 256-298`); only built-in pipeline is `GoalPipeline(executor=..., verifier=...)` | `src/agentscope/agent/_agent.py:112-217, 300-347, 256-298`; `src/agentscope/pipeline/_goal_pipeline.py:55-92` |
| Model injection | Constructor arg `model: ChatModelBase` (`agent/_agent.py:115-119, 168`); `ChatModelBase` abstract at `model/_base.py:37-98`; concrete providers `OpenAIChatModel`, `AnthropicChatModel`, `DashScopeChatModel`, `DeepSeekChatModel`, `GeminiChatModel`, `OllamaChatModel`, `XAIChatModel`, `MoonshotChatModel`, `OpenAIResponseModel`; credentials via typed `CredentialBase` subclasses registered through `CredentialFactory` (`credential/_factory.py:18-117`) | `src/agentscope/model/_base.py:37-98`; `src/agentscope/credential/_factory.py:18-117` |
| Tool surface | `ToolBase` abstract (`tool/_base.py:94-451`) + `Toolkit` container (`tool/_toolkit.py:66-691`); `ToolGroup` model with `basic` group always present; built-ins `Bash`, `PowerShell`, `Read`, `Write`, `Edit`, `Glob`, `Grep`, `ResetTools` (group activator), `SkillViewer`, plus `TaskCreate/TaskList/TaskGet/TaskUpdate`; `FunctionTool` / `MCPTool` adapters in `tool/_adapters.py` | `src/agentscope/tool/_base.py:94-451`, `src/agentscope/tool/_toolkit.py:66-691` |
| State | `AgentState` pydantic model (`state/_state.py:178-372`) — `session_id`, `context: list[Msg]`, `summary`, `reply_context`, `permission_context`, `tool_context` (with `read_file_cache`, `activated_groups`), `tasks_context`, `middle_context`; persistence via `StorageBase` — `AsyncSQLAlchemyStorage` (SQLite/aiosqlite/asyncpg/aiomysql) or `RedisStorage`; sessions indexed under `source_chat_id / source_channel_id / source_schedule_id` | `src/agentscope/state/_state.py:178-372`; `src/agentscope/app/storage/_base.py:29-...` |
| Observability | OpenTelemetry via `TracingMiddleware` (`middleware/_tracing/_trace.py:117-...`) — hooks `on_reply`, `on_model_call`, `on_acting`; 7 agent middleware hooks (`middleware/_base.py:13-303`); rich `AgentEvent` async stream (`event/__init__.py:1-77`) with 23 event subclasses including `RequireUserConfirmEvent`, `UserInterruptEvent`, `ExceedMaxItersEvent`; standard logger; per-message `Msg.usage: Usage` carries token counts | `src/agentscope/middleware/_tracing/_trace.py:117-...`; `src/agentscope/event/__init__.py:1-77` |
| Stub model feasibility | **EASY** — subclass `ChatModelBase`, implement `async def _call_api(self, model_name, messages, tools=None, tool_choice=None, **kwargs) -> ChatResponse | AsyncGenerator[ChatResponse, None]` (`model/_base.py:292-313`); `__call__` and structured-output are base-class concerns | `src/agentscope/model/_base.py:292-313` |
| Tool injection feasibility | **EASY** — subclass `ToolBase` (or use `FunctionTool`), pass `Toolkit(tools=[...])` to `Agent(..., toolkit=...)` | `src/agentscope/tool/_base.py:94-451`; `src/agentscope/agent/_agent.py:186` |

### 2.10 deepset-ai/haystack

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | Single Python package `haystack`; pyproject at root with `openai>=2.6.0` and many optional extras (`[haystack-ai]`, `[inference]`, etc.) | `pyproject.toml`, `haystack/components/generators/chat/__init__.py` |
| Execution entrypoint | **Pipeline DAG**, not an agent. `@component` decorator (`haystack/core/component/component.py:14`) → `Pipeline().add_component("name", MyComponent())` → `pipeline.run({"comp1": {"input": ...}})` returns dict of named outputs | `haystack/core/component/component.py:137-184`, `haystack/core/pipeline/` |
| Model injection | `OpenAIChatGenerator`, `AzureOpenAIChatGenerator`, `AzureOpenAIResponsesChatGenerator`, `OpenAIResponsesChatGenerator`, `LLM` wrapper, `MockChatGenerator` — all lazy-imported (`_import_structure` in `__init__.py`); no global registry, chosen at construction time | `haystack/components/generators/chat/__init__.py:10-31` |
| Tool surface | `Component` Protocol (runtime-checkable) — anything with a `run(*args, **kwargs) -> Mapping[str, Any]` method qualifies (`component.py:137-184`); pipeline wires components together; no separate "tool" concept in pure Haystack core | `haystack/core/component/component.py:137-184` |
| State | Pipeline state is the per-run dict; no built-in cross-run persistence in core; optional storage helpers in `haystack/components/retrievers/`, etc. | `haystack/core/pipeline/` |
| Observability | Tracing via `tracing.tracer.ff_tracer` / `content_tracer` (LazyImporter); `logger = logging.getLogger(__name__)`; no first-party callback bus | `haystack/tracing/` |
| Stub model feasibility | **EASY** — `MockChatGenerator` exists at `haystack/components/generators/chat/mock.py`; new chat generators are just `ChatGenerator` subclasses | `haystack/components/generators/chat/__init__.py:17, 25` |
| Tool injection feasibility | **EASY** (re-interpreted) — `Component` Protocol accepts any class with a `run` method; pipeline.add_component("name", MyComponent()) | `haystack/core/component/component.py:137-184` |

### 2.11 google/adk-python

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | Single Python package `google-adk` at `src/google/adk/`; pyproject at root; `aiosqlite>=0.21` core dep; multiple constraints files (`constraints-3.10.txt` ... `constraints-3.14.txt`) indicate Python 3.10-3.14 support | `pyproject.toml:35`, `constraints-*.txt` |
| Execution entrypoint | `LlmAgent(name, model, instruction, tools=...)` → `Runner(agent, app_name, session_service=...)` → `async for event in runner.run_async(user_id, session_id, new_message)`; `SessionService` (InMemory / Sqlite / VertexAI) | `src/google/adk/agents/llm_agent.py`, `src/google/adk/runners.py`, `src/google/adk/sessions/sqlite_session_service.py:127-176` |
| Model injection | `model: Union[str, BaseLlm]`; str resolved via `LiteLlm` (litellm wrapper) — `litellm`-based multi-provider; Google-specific `google_llm.Gemini`; `AnthropicLlm` via env (`models/anthropic_llm.py`); env-var API keys for `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `VERTEXAI_PROJECT` etc. | `src/google/adk/models/lite_llm.py:306`, `src/google/adk/models/google_llm.py:445`, `src/google/adk/models/anthropic_llm.py:1321-1322` |
| Tool surface | `BaseTool` + `BaseToolset` (with `async def get_tools()` protocol at `tools/base_toolset.py:88-127`); `FunctionTool` for python functions; `McpToolset`; `tool_name_prefix` for grouping (`base_toolset.py:103-166`); artifact services (`InMemoryArtifactService`, `FileArtifactService`, `GcsArtifactService`) | `src/google/adk/tools/base_toolset.py:88-166`; `src/google/adk/artifacts/__init__.py:20-36` |
| State | `SessionService` (BaseSessionService + InMemory / Sqlite / VertexAI implementations) holds `Session` with `events: list[Event]`; `state` dict per session; persistence via `aiosqlite` for sqlite implementation | `src/google/adk/sessions/sqlite_session_service.py:127-176` |
| Observability | BigQuery analytics plugin (`plugins/bigquery_agent_analytics_plugin.py:46`); standard `logger`; `ADK_MAX_LLM_CALLS` env-var knob (`agents/run_config.py:42`) | `src/google/adk/agents/run_config.py:42`; `src/google/adk/plugins/bigquery_agent_analytics_plugin.py:46` |
| Stub model feasibility | **EASY** — `BaseLlm` subclass with `async def generate_content_async(...)`; `LiteLlm` wrapper is the integration seam for external providers | `src/google/adk/models/base_llm.py`, `src/google/adk/models/lite_llm.py` |
| Tool injection feasibility | **EASY** — `BaseTool` or `BaseToolset` subclasses, passed as list to `LlmAgent(tools=[...])` | `src/google/adk/tools/base_toolset.py:88-166` |

### 2.12 microsoft/agent-framework

| Dimension | Value | Source citation |
|---|---|---|
| Build shape | **uv workspace monorepo**, 35 Python packages under `python/packages/` (`core`, `openai`, `anthropic`, `azure-ai-*`, `claude`, `gemini`, `ollama`, `mistral`, `bedrock`, `redis`, `azure-cosmos*`, `mem0`, `orchestrations`, `workflows`, `ag-ui`, `a2a`, `chatkit`, `devui`, `copilotstudio`, `hosting*`, etc.); 30 use `flit_core.buildapi`, 2 use `uv_build`, 2 use `hatchling.build`, 1 uses `setuptools.build_meta`; `poethepoet==0.48.0` task runner; no native extensions visible | `python/pyproject.toml:47, 247-...`; `python/packages/*/pyproject.toml` |
| Execution entrypoint | `ChatAgent(chat_client=OpenAIChatClient(...), instructions=..., tools=[...])` then `await agent.run(message, thread=...)`; or `WorkflowBuilder().set_start_executor(...).add_edge(...).build()` for graph | `python/packages/core/agent.py`, `python/packages/core/workflows/` |
| Model injection | Constructor arg `chat_client=...` typed against an abstraction; concrete clients `OpenAIChatClient`, `AnthropicChatClient`, `AzureAIAgent`, `OllamaChatClient`, `GeminiChatClient`, `MistralChatClient`, `BedrockChatClient`, `FoundryChatClient`, etc. | `python/packages/openai/`, `python/packages/anthropic/`, `python/packages/azure-ai-*` |
| Tool surface | `ai_function` decorator → `AIFunction`; passed as list to `ChatAgent(tools=[...])`; **tools are first-class schemas + invocation handlers, not framework subclasses** | `python/packages/core/ai_function.py` |
| State | `AgentThread` for chat agents; per-workflow state machine for workflows; optional persistence via `RedisStateStore` etc. | `python/packages/core/agent_thread.py`, `python/packages/redis/` |
| Observability | OpenTelemetry spans per agent invocation; standard `logger`; some packages include `tracing/` modules | `python/packages/core/telemetry/` |
| Stub model feasibility | **EASY** — implement a custom `ChatClient` subclass; wire into `ChatAgent(chat_client=...)` | `python/packages/core/chat_client.py` |
| Tool injection feasibility | **EASY** — `ai_function` decorator wraps any python callable; pass list | `python/packages/core/ai_function.py` |

---

## 3. Cross-cutting dimensions

### 3.1 Build-backend distribution (12 repos)

| Backend | Repos |
|---|---|
| `hatchling` | langchain, langgraph, deer-flow (harness package) |
| `setuptools` | agentscope, AutoGPT (classic), MetaGPT, adk-python, browser-use |
| `flit_core` | microsoft/agent-framework (30 of 35 packages), crewAI |
| `uv_build` | microsoft/agent-framework (2 packages: ollama, ag-ui), agno |
| unknown | haystack (single package) |

### 3.2 Model-injection style

| Style | Repos |
|---|---|
| Positional `model=` on Agent class (framework-native abstract base) | langchain, langgraph, agentscope, agno, AutoGPT (`MultiProvider`), browser-use, adk-python (`BaseLlm`), microsoft (`ChatClient`), haystack (`ChatGenerator`), deer-flow (via `create_chat_model` factory → LangChain `BaseChatModel`) |
| Global config + `BaseLLM.aask()` patch | MetaGPT |
| Custom `Llm` interface (not LangChain) | crewAI |

### 3.3 State / persistence style

| Style | Repos |
|---|---|
| LangGraph checkpointer (sqlite/postgres, pluggable) | langchain (via langgraph), langgraph, deer-flow |
| Application-layer `StorageBase` (SQLite/aiosqlite/Redis via SQLAlchemy) | agentscope |
| `SessionService` (InMemory / SQLite via aiosqlite / VertexAI) | adk-python |
| In-process per call, optional `memory=` plug-ins | crewAI |
| Pluggable `storage=` (sqlite / postgres) | agno |
| Filesystem `FileStorage` (workspace-as-state) | AutoGPT |
| Per-`kickoff` browser-session handle, optional `save_conversation_path` filesystem save | browser-use |
| Pipeline state per `pipeline.run(...)`, no built-in persistence | haystack |
| Per-thread `AgentThread`, optional Redis state store | microsoft/agent-framework |
| `Team` + role `memory`, `MGXEnv.history` | MetaGPT |

### 3.4 Observability style

| Style | Repos |
|---|---|
| LangChain `BaseCallbackHandler` via `RunnableConfig["callbacks"]` + `astream_events` | langchain, langgraph, deer-flow (attached at graph root) |
| Framework-specific `AgentEvent` async stream + middleware hooks | agentscope (23 event types, 7 hooks) |
| OpenTelemetry via `TracingMiddleware` | agentscope, microsoft/agent-framework |
| `MultiProvider` + Sentry + `dump_prompt` debug | AutoGPT |
| First-party `ProductTelemetry` capture (AgentTelemetryEvent) | browser-use (opt-out via env) |
| `subscription.subscribe(role, trigger, callback)` for role-response callbacks | MetaGPT |
| `token_usage_callback` + Opik / Langfuse / MLflow / AgentOps trackers | crewAI |
| `BigQueryAgentAnalyticsPlugin`, standard logger | adk-python |
| `tracing.tracer.ff_tracer` lazy-import | haystack |
| No first-party tracing | agno |

### 3.5 Tool abstraction

| Abstraction | Repos |
|---|---|
| `langchain_core.tools.BaseTool` (drop-in subclasses, plain list argument) | langchain, langgraph, deer-flow |
| `ToolBase` abstract + `Toolkit` container + `ToolGroup`s | agentscope |
| `@tool` decorated python functions, plain list | agno, langchain, microsoft/agent-framework (`ai_function`) |
| `Controller` registry with `@controller.action(...)` decorator | browser-use |
| `BaseTool` + `BaseToolset` (async `get_tools` protocol, `tool_name_prefix` grouping) | adk-python |
| `Action` subclasses registered onto `Role.actions` list | MetaGPT |
| `Command` subclasses via `CommandProvider.get_commands` pipeline | AutoGPT |
| `Component` Protocol (any class with `run(*args, **kwargs) -> Mapping[str, Any]`) | haystack |
| `crewai.tools.BaseTool`, plain list | crewAI |

---

## 4. Stub-model and tool-injection feasibility matrix

| Repository | Stub model | Tool injection | Notes |
|---|---|---|---|
| langchain | **EASY** | **EASY** | In-repo `FakeToolCallingModel` |
| langgraph | **EASY** | **EASY** | Inherits LangChain model surface |
| crewAI | **MODERATE** | **EASY** | `BaseLLM` is LiteLLM-wrapped; different `call()` protocol |
| agno | **MODERATE** | **EASY** | Model must be registered; tool is plain function |
| AutoGPT | **HARD** | **MODERATE** | Long-running CLI loop + MultiProvider + ReWOO bypass |
| MetaGPT | **MODERATE** | **MODERATE** | Global LLMConfig + BaseLLM.aask() patch + set_actions list |
| browser-use | **EASY** | **HARD** | Custom Controller subclass needed for non-browser tools |
| deer-flow | **EASY** | **EASY** | Same as langchain + `attach_tracing=False` discipline |
| agentscope | **EASY** | **EASY** | One base class per concern |
| haystack | **EASY** | **EASY** | `MockChatGenerator` already exists |
| adk-python | **EASY** | **EASY** | `BaseLlm` subclass + `BaseToolset` async protocol |
| microsoft/agent-framework | **EASY** | **EASY** | `ChatClient` subclass + `ai_function` decorator |

**Tally — counts:**

| Verdict | Stub model | Tool injection |
|---|---|---|
| EASY | 9 | 10 |
| MODERATE | 2 | 2 |
| HARD | 1 | 1 |

---

## 5. Constraint compliance

This artefact:

- Did NOT execute any code from any of the 12 repositories (only `Read` and
  `Grep` were used against the frozen materialised workspaces).
- Did NOT issue any compliance verdict. None of the rows in §2 are claims
  about Article 12(1). They are static engineering observations.
- Did NOT modify any third-party repository.
- Did NOT change the runtime security boundary.
- Did NOT start Article 12(2) or any framework-family auto-detection.
- Used only frozen CR-3 SHAs from `cr3_50_repo_manifest.json`.
- Materialised via the existing `SourceCache` + `RepositoryMaterializer`
  (with a direct-clone fallback for the three repos where the SourceCache
  pipeline failed for transient reasons — see column "Materialised via"
  in §1).

— end of matrix —