# CR-3 Numerical / Persistence Reconciliation

**Audit run ID:** 11

**Constraints honoured:**

- did NOT run another corpus gate
- did NOT add adapters or framework-family detection
- did NOT change Article 12(1)
- did NOT mutate any persisted result row

---

## 1. Exact 50-row reconciliation
DB returned **50** rows; all have exactly one corresponding `evaluation_jobs` row.

| # | full_name | sha_resolved | sha_class | adapter | job_status | compliance_status | missing_capability | error_class | attempt_count | recipe_version |
|---:|---|---|---|---|---|---|---|---|---:|---|
| 0 | `SWE-agent/mini-swe-agent` | `25941c89` | pinned | `minisweagent` | completed | `PASS` | `` | `` | 1 | `v1.1` |
| 1 | `gptme/gptme` | `c574b83d` | pinned | `gptme` | completed | `PASS` | `` | `` | 1 | `v1.1` |
| 2 | `HKUDS/nanobot` | `4d204ba0` | pinned | `nanobot` | completed | `FAIL` | `` | `` | 1 | `v1.1` |
| 3 | `he-yufeng/CoreCoder` | `a03ef364` | pinned | `corecoder` | completed | `FAIL` | `` | `` | 1 | `v1.1` |
| 4 | `The-Pocket/PocketFlow` | `f74d023f` | pinned | `pocketflow` | completed | `FAIL` | `` | `` | 1 | `v1.1` |
| 5 | `NousResearch/hermes-agent` | `—` | sha_resolution_error | `__MISSING__` | completed | `<NULL>` | `` | `SHA_RESOLUTION_ERROR` | 0 | `v0` |
| 6 | `Significant-Gravitas/AutoGPT` | `32a43d00` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 7 | `langchain-ai/langchain` | `5893459c` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 8 | `browser-use/browser-use` | `2e32d260` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 9 | `bytedance/deer-flow` | `bf740ffa` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 10 | `shareAI-lab/learn-claude-code` | `0dcafa2a` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 11 | `FoundationAgents/MetaGPT` | `11cdf466` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 12 | `ZhuLinsen/daily_stock_analysis` | `03e11fe3` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `` | `` | 1 | `v0` |
| 13 | `crewAIInc/crewAI` | `da4daadb` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 14 | `calesthio/OpenMontage` | `cd9f3c1f` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 15 | `rohitg00/ai-engineering-from-scratch` | `39ea8a1c` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 16 | `hugohe3/ppt-master` | `bf81f3ec` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 17 | `zhayujie/CowAgent` | `ed5bb344` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 18 | `agno-agi/agno` | `c96291cb` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 19 | `langchain-ai/langgraph` | `11ee1859` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 20 | `HKUDS/DeepTutor` | `07bb3c19` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 21 | `ashishpatel26/500-AI-Agents-Projects` | `9beeb721` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 22 | `MadsLorentzen/ai-job-search` | `93fb0e6c` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 23 | `VectifyAI/PageIndex` | `9fee239b` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 24 | `agentscope-ai/QwenPaw` | `1a4f4d8a` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 25 | `HKUDS/Vibe-Trading` | `e90b6c6c` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 26 | `CloakHQ/CloakBrowser` | `bb6f2f00` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 27 | `agentscope-ai/agentscope` | `e90f1c75` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 28 | `Fosowl/agenticSeek` | `ae57a235` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 29 | `deepset-ai/haystack` | `e318778c` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 30 | `google/adk-python` | `c3d37302` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 31 | `hummingbot/hummingbot` | `2bfaccc4` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 32 | `emcie-co/parlant` | `ea737442` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 33 | `microsoft/agent-lightning` | `88528bf4` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 34 | `TransformerOptimus/SuperAGI` | `c3c1982e` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 35 | `browser-use/browser-harness` | `e3e8069c` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 36 | `cft0808/edict` | `14a20755` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 37 | `raga-ai-hub/RagaAI-Catalyst` | `ab678933` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 38 | `xbtlin/ai-berkshire` | `fd83d063` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 39 | `opensandbox-group/OpenSandbox` | `48b0215f` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 40 | `img2threejs/img2threejs` | `9fbd0ca5` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 41 | `lsdefine/GenericAgent` | `7ad2162f` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 42 | `e2b-dev/E2B` | `5a56c87e` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 43 | `microsoft/agent-framework` | `edfe115e` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 44 | `neuml/txtai` | `546e7777` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 45 | `simular-ai/Agent-S` | `bffdb59c` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 46 | `ValueCell-ai/valuecell` | `9793e9c0` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 47 | `kedro-org/kedro` | `b2fb60e9` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 48 | `omnigent-ai/omnigent` | `1bcf2f42` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |
| 49 | `GetBindu/Bindu` | `7d5b6d25` | ok | `__MISSING__` | completed | `UNSUPPORTED` | `compatible_execution_recipe` | `` | 1 | `v1.1` |

## 2. Corrected adapter coverage
**Mutually exclusive dimensions:**

- **Adapter-supported:** 5 repos (frozen five) — looked up via `get_adapter(...)`, found in `ADAPTER_REGISTRY`
- **Adapter-missing:** 45 repos — `get_adapter(...)` raised `KeyError`, stamped `__MISSING__`
  - Of those 45: 44 went on to terminalise as `compliance_status='UNSUPPORTED'` (after one execution attempt).
  - The remaining 1 (`NousResearch/hermes-agent`) terminalised as `compliance_status=NULL` / `error_class=SHA_RESOLUTION_ERROR` at `build_jobs_for_run` time, **before** the adapter lookup ever ran.

- **SHA-resolution-failure:** 1 repo — distinct dimension. The runner does not silently discard it; it surfaces as an ERROR-class terminal outcome.

Sum: 5 + 44 + 1 = 50 ✓

The earlier report statement `supported=5, no adapter=40, SHA=1` was a report-generation arithmetic bug. The correct figure is `no adapter=44, plus 1 SHA-resolution-failure that never reached the adapter lookup`.

## 3. Corrected missing-capability inventory
```
{
  "<NULL>": 7,
  "compatible_execution_recipe": 43
}
```

**Anomaly (1 row):** `ZhuLinsen/daily_stock_analysis` has `compliance_status='UNSUPPORTED'` but `missing_capability=NULL` (and `execution_recipe_version='v0'` instead of `'v1.1'`). The executor code in `_process_one_job_thread` that should stamp this row did not run for this job. The verdict itself is correct; only the structured `missing_capability` token is missing.

**Likely root cause:** `update_evaluation_job_recipe_and_missing` is wrapped in `except sqlite3.IntegrityError`. A transient `sqlite3.OperationalError: database is locked` from concurrent connections would propagate up and skip the stamping step. This defect was also observed in run 9 (15/20 rows affected, pre-v1.1.1 fix); run 10 (0/20) was clean; run 11 has 1/50.

Per the audit constraint "Do not modify results simply to make counts match," this row is **not mutated** in the DB.

## 4. Attempt-count explanation
- Total `evaluation_attempts` rows for this run: **49**
- Attempt-count distribution: {"0": 1, "1": 49}

**Zero-attempt jobs:** 1 (`NousResearch/hermes-agent`, `error_class=SHA_RESOLUTION_ERROR`). This is the **Option B** architecture from the audit: pre-execution outcomes (`build_jobs_for_run`-time SHA-resolution failures, fast UNSUPPORTED) may legitimately terminalise without an `evaluation_attempts` row. The executor inserts the evaluation_job row with `JOB_STATUS_COMPLETED` directly, bypassing the `crp.insert_evaluation_attempt(...)` call. This is documented in `src/compliance/corpus_runner/executor.py` (the SHA-resolution path) and in `src/compliance/corpus_runner/executor.py:907` (the v1.1 stamping step).

**One-attempt jobs:** 49 (every other job, including the 44 fast UNSUPPORTED and the 5 executed frozen five).

**Multi-attempt jobs:** 0 (no retry fired).

## 5. Configured vs observed retry counts
| | value |
|---|---|
| Configured `max_attempts` (from `corpus_runs`) | **2** |
| Maximum `attempt_count` observed on any single job | **1** |
| Any retry fired | **no** |

The earlier report statement `max attempts=1 observed` was the **observed** value (every job terminalised on the first attempt) and was presented without the configured ceiling. This audit reports both.

## 6. Corrected terminal distribution
### 6.1 `evaluation_jobs.compliance_status`
```
{
  "<NULL>": 1,
  "FAIL": 3,
  "PASS": 2,
  "UNSUPPORTED": 44
}
```
Sum: 50 = 50 ✓

### 6.2 `corpus_runs` aggregate counters
```
{
  "completed_jobs": 50,
  "error_count": 1,
  "fail_count": 3,
  "pass_count": 2,
  "skipped_count": 0,
  "total_jobs": 50,
  "unknown_count": 0,
  "unsupported_count": 44
}
```
Sum (pass + fail + unknown + unsupported + error + skipped): **50 = 50 ✓**

### 6.3 Independent dimensions (must NOT be mixed)
- **SHA-resolution success/failure:** {"ok": 44, "pinned": 5, "sha_resolution_error": 1}
- **Adapter support/missing:** supported=5, missing=45
- **Execution attempted/not attempted:** attempted=49 (had an `evaluation_attempts` row), not-attempted=1 (SHA-resolution error)
- **Missing-capability counts:** {"<NULL>": 7, "compatible_execution_recipe": 43}
- **Error-class counts (attempt-level):** {}
- **Attempt-count distribution:** {"0": 1, "1": 49}

## 7. Was persisted data modified?
**No.** No `evaluation_jobs`, `evaluation_attempts`, `corpus_run_repositories`, or `corpus_runs` row was inserted, updated, or deleted by this audit. The persistence defect in §19.1 is documented but not repaired (per the audit constraint).

## 8. Was report-generation logic modified?
**Yes.** The summary JSON and report markdown were regenerated to:
- surface the **configured vs observed** retry distinction
- split **adapter coverage** into mutually exclusive dimensions
- split **SHA-resolution** into its own dimension
- surface the **§19.1 anomaly** explicitly
- document the **zero-attempt job** as Option B (pre-execution terminalization)
- correct the `corpus_runs.error_count=1` bucket alignment (it carries the SHA-resolution-error row, whose `compliance_status` is NULL)

## 9. CR-3 final verdict

- All 50 rows present. ✓
- Sum pfukes = 50 ✓.
- Frozen-five regression intact. ✓
- Interrupt + resume preserved manifest identity. ✓
- Source-cache and workspace invariants hold. ✓
- One persistence defect identified (§19.1): 1 row out of 44 UNSUPPORTED lacks the structured `missing_capability` token. The compliance verdict is correct; the structured field is absent. The defect is intermittent (run 9 = 15/20, run 10 = 0/20, run 11 = 1/50) and is most likely caused by a `sqlite3.OperationalError: database is locked` from the executor's per-call `sqlite3.connect()` pattern that is not caught by the `except sqlite3.IntegrityError` handler.
- One architectural correctness item: zero-attempt job for the SHA-resolution-error row (Option B; documented).

**Verdict: PASS.**

The compliance verdicts are sound and durable. The single persistence defect is structural (caught by the reconciliation, not by the executor) and should be repaired by widening the exception handler or restructuring the connection pattern in a follow-up — not by mutating historical rows.