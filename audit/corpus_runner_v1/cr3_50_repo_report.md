# Reguard Corpus Runner v1.1.1 — 50-Repository Control-Plane Scale Gate

**Date:** 2026-08-29T16:29:25Z  
**CorpusRun ID:** 11  
**Requirement:** AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING v1.4.0  
**Scenario:** compliance.article12_1.simple  
**Executor:** container  
**Runtime:** v1.1.1  
**max_workers:** 1  
**max_attempts:** 2  
**Selection rule:** frozen five first, 45 by stars DESC, id ASC, exclude frozen five  
**Wall-clock:** 161.62 s

## 1. 50-repository selection
- Total selected: **50**
- Frozen five: 5
- Additional (45): 45
- Ordering rule: `frozen five first (in spec order); 45 by agent_repositories.STARS DESC, agent_repositories.id ASC`
- SHA policy: `frozen five use pinned historical SHAs; additional 45 resolved via git ls-remote HEAD with 40-hex validation`

## 2. SHA snapshot results
- Total manifest rows: 50
- Resolution classes: {"ok": 44, "pinned": 5, "sha_resolution_error": 1}
- Authoritative source: `corpus_run_repositories` (DB).

| # | Repository | Stars | Class | SHA |
|---:|---|---:|---|---|
| 0 | `SWE-agent/mini-swe-agent` | 6787 | pinned | `25941c89…` |
| 1 | `gptme/gptme` | 4399 | pinned | `c574b83d…` |
| 2 | `HKUDS/nanobot` | 47436 | pinned | `4d204ba0…` |
| 3 | `he-yufeng/CoreCoder` | 1678 | pinned | `a03ef364…` |
| 4 | `The-Pocket/PocketFlow` | 11135 | pinned | `f74d023f…` |
| 5 | `NousResearch/hermes-agent` | 236958 | sha_resolution_error | `(unresolved)` |
| 6 | `Significant-Gravitas/AutoGPT` | 186910 | ok | `32a43d00…` |
| 7 | `langchain-ai/langchain` | 145088 | ok | `5893459c…` |
| 8 | `browser-use/browser-use` | 111105 | ok | `2e32d260…` |
| 9 | `bytedance/deer-flow` | 80969 | ok | `bf740ffa…` |
| 10 | `shareAI-lab/learn-claude-code` | 75395 | ok | `0dcafa2a…` |
| 11 | `FoundationAgents/MetaGPT` | 70053 | ok | `11cdf466…` |
| 12 | `ZhuLinsen/daily_stock_analysis` | 64039 | ok | `03e11fe3…` |
| 13 | `crewAIInc/crewAI` | 57658 | ok | `da4daadb…` |
| 14 | `calesthio/OpenMontage` | 51443 | ok | `cd9f3c1f…` |
| 15 | `rohitg00/ai-engineering-from-scratch` | 49672 | ok | `39ea8a1c…` |
| 16 | `hugohe3/ppt-master` | 49660 | ok | `bf81f3ec…` |
| 17 | `zhayujie/CowAgent` | 46694 | ok | `ed5bb344…` |
| 18 | `agno-agi/agno` | 41938 | ok | `c96291cb…` |
| 19 | `langchain-ai/langgraph` | 40516 | ok | `11ee1859…` |
| 20 | `HKUDS/DeepTutor` | 37596 | ok | `07bb3c19…` |
| 21 | `ashishpatel26/500-AI-Agents-Projects` | 37035 | ok | `9beeb721…` |
| 22 | `MadsLorentzen/ai-job-search` | 36613 | ok | `93fb0e6c…` |
| 23 | `VectifyAI/PageIndex` | 35333 | ok | `9fee239b…` |
| 24 | `agentscope-ai/QwenPaw` | 34519 | ok | `1a4f4d8a…` |
| 25 | `HKUDS/Vibe-Trading` | 31807 | ok | `e90b6c6c…` |
| 26 | `CloakHQ/CloakBrowser` | 30853 | ok | `bb6f2f00…` |
| 27 | `agentscope-ai/agentscope` | 29730 | ok | `e90f1c75…` |
| 28 | `Fosowl/agenticSeek` | 27027 | ok | `ae57a235…` |
| 29 | `deepset-ai/haystack` | 26325 | ok | `e318778c…` |
| 30 | `google/adk-python` | 21303 | ok | `c3d37302…` |
| 31 | `hummingbot/hummingbot` | 19630 | ok | `2bfaccc4…` |
| 32 | `emcie-co/parlant` | 18270 | ok | `ea737442…` |
| 33 | `microsoft/agent-lightning` | 17867 | ok | `88528bf4…` |
| 34 | `TransformerOptimus/SuperAGI` | 17660 | ok | `c3c1982e…` |
| 35 | `browser-use/browser-harness` | 17167 | ok | `e3e8069c…` |
| 36 | `cft0808/edict` | 16604 | ok | `14a20755…` |
| 37 | `raga-ai-hub/RagaAI-Catalyst` | 16150 | ok | `ab678933…` |
| 38 | `xbtlin/ai-berkshire` | 15915 | ok | `fd83d063…` |
| 39 | `opensandbox-group/OpenSandbox` | 14742 | ok | `48b0215f…` |
| 40 | `img2threejs/img2threejs` | 14049 | ok | `9fbd0ca5…` |
| 41 | `lsdefine/GenericAgent` | 14044 | ok | `7ad2162f…` |
| 42 | `e2b-dev/E2B` | 13560 | ok | `5a56c87e…` |
| 43 | `microsoft/agent-framework` | 13137 | ok | `edfe115e…` |
| 44 | `neuml/txtai` | 12909 | ok | `546e7777…` |
| 45 | `simular-ai/Agent-S` | 12193 | ok | `bffdb59c…` |
| 46 | `ValueCell-ai/valuecell` | 11004 | ok | `9793e9c0…` |
| 47 | `kedro-org/kedro` | 10971 | ok | `b2fb60e9…` |
| 48 | `omnigent-ai/omnigent` | 9316 | ok | `1bcf2f42…` |
| 49 | `GetBindu/Bindu` | 9186 | ok | `7d5b6d25…` |

## 3. Job construction / idempotence
- After 1st `build_jobs_for_run`: 50
- After 2nd `build_jobs_for_run`: 50
- After 3rd `build_jobs_for_run`: 50
- Duplicate rows created across calls: 0

## 4. Adapter coverage (mutually exclusive)
- Adapter-supported repos: **5** (frozen five: SWE-agent/mini-swe-agent, gptme/gptme, HKUDS/nanobot, he-yufeng/CoreCoder, The-Pocket/PocketFlow)
- Adapter-missing repos: **45** (44 reached `get_adapter` lookup and got `__MISSING__`; 1 reached SHA-resolution failure before any adapter lookup)
- Ratio supported/selected: `5/50`

## 5. Frozen-five regression result
| Repository | Expected | Actual | SHA unchanged? |
|---|---|---|:-:|
| `SWE-agent/mini-swe-agent` | PASS | PASS | ✅ |
| `gptme/gptme` | PASS | PASS | ✅ |
| `HKUDS/nanobot` | FAIL | FAIL | ✅ |
| `he-yufeng/CoreCoder` | FAIL | FAIL | ✅ |
| `The-Pocket/PocketFlow` | FAIL | FAIL | ✅ |

**Matches expected:** `True`

## 6. Source-cache metrics
- Cache root: `/tmp/reguard_cr3_cache`
- Cache size before: 0 bytes
- Cache size after: 478,849,255 bytes
- Cache entries on disk: 5
- Cache entries in DB (source_cache_entries): 0

## 7. Workspace metrics
- Workspace root: `/tmp/reguard_cr3_ws`
- Workspaces before: 0
- Workspaces after: 5
- Workspace bytes before: 0
- Workspace bytes after: 160
- Orphaned workspaces: 0
- Survivors with materialized marker: 0

## 8. Security observations
- Materializer used archive-only materialization (no `.git/` shim, no symlinks into cache).
- Container executor ran with `--cap-drop ALL`, `--security-opt no-new-privileges`, `--user 10001:10001`.
- `/input` mounted read-only, `/artifacts` writable, probe network `none`.
- No Docker/Podman socket, no host credentials exposed.

## 9. Actual 50-run interruption / resume
- Pre-exec (subprocess entered): {'attempts': 0, 'completed': 1, 'pending': 49, 'running': 0, 'skipped': 0, 'total': 50}
- At SIGTERM: {'attempts': 12, 'pending': 37, 'running': 0, 'terminal': 13}
- After SIGTERM (before reset): {'attempts': 12, 'completed': 13, 'pending': 37, 'running': 0, 'skipped': 0, 'total': 50}
- `running` → `pending` reset count: 0
- After reset (resume pending): {'attempts': 12, 'completed': 13, 'pending': 37, 'running': 0, 'skipped': 0, 'total': 50}
- After resume complete: {'attempts': 49, 'completed': 50, 'pending': 0, 'running': 0, 'skipped': 0, 'total': 50}
- Peak active containers: 1
- Error class counts across the run: {}

## 10. Retry behavior
- Configured max_attempts (from `corpus_runs.max_attempts`): **2**
- Maximum `attempt_count` actually observed on any single job: **1**
- Any retry fired: **False**
- Retried jobs (attempt_count > 1): 0
- Successful after retry: 0
- Failed after retry: 0
- Total `evaluation_attempts` rows: 49
- Attempt-count distribution: {"0": 1, "1": 49}

**Interpretation:** every job terminalised on its first attempt, so the configured ceiling of `max_attempts=2` was never reached. The 'max attempts=1 observed' phrasing in the previous report was the observed value, not the configured ceiling.

## 11. Terminal result distribution
- `evaluation_jobs.compliance_status` distribution: {"<NULL>": 1, "FAIL": 3, "PASS": 2, "UNSUPPORTED": 44}
- `corpus_runs` aggregate counters: {"completed_jobs": 50, "error_count": 1, "fail_count": 3, "pass_count": 2, "skipped_count": 0, "total_jobs": 50, "unknown_count": 0, "unsupported_count": 44}
- Sum of corpus_runs buckets: **pass + fail + unknown + unsupported + error + skipped = 50** (matches 50)

**Note on bucket alignment:** the `corpus_runs.error_count=1` is the SHA-resolution-error row (terminalised at `build_jobs_for_run` time without an `evaluation_attempts` row). Its `evaluation_jobs.compliance_status` is NULL; only the run-level aggregate counter carries the ERROR bucket. The other 49 rows have non-null `compliance_status` and 49 `evaluation_attempts` rows.

## 12. Structured missing-capability inventory (corrected)
```
{
  "<NULL>": 7,
  "compatible_execution_recipe": 43
}
```

- 43 UNSUPPORTED rows have `missing_capability='compatible_execution_recipe'`.
- 1 UNSUPPORTED row (`ZhuLinsen/daily_stock_analysis`) has `missing_capability=NULL` — see §19.
- 5 PASS/FAIL rows have `missing_capability=NULL` (correct — those rows are not UNSUPPORTED and the executor only stamps the field for `last_status == UNSUPPORTED`).
- 1 SHA-resolution-error row has `missing_capability=NULL` (correct — the executor's stamping code was never reached for this row).

## 13. ERROR breakdown
- Job-level `error_class` distribution: {"SHA_RESOLUTION_ERROR": 1}
- Attempt-level `error_class` distribution: {}
- The single ERROR row is `NousResearch/hermes-agent` with `error_class=SHA_RESOLUTION_ERROR`.

## 14. Timing observations
- Overall wall-clock (selection → completion): 161.62 s
- Run started_at: 2026-08-29T16:27:45Z
- Run completed_at: 2026-08-29T16:29:25Z
- Per-job timing instrumentation was not added during this gate (kept minimal).

## 15. DB / storage growth
- DB size before: 14,041,088 bytes
- DB size after: 14,090,240 bytes
- `execution_artifacts` rows: 0
- `requirement_evaluations` rows: 68
- `evaluation_attempts` rows: 109
- `compliance_runtime_runs` rows: 14

## 16. Cache-GC dry-run
```
{
  "bytes_reclaimable": 0,
  "bytes_reclaimed": 0,
  "dry_run": true,
  "entries_considered": 5,
  "entries_evicted": 0,
  "entries_protected": 0
}
```

## 17. Workspace-janitor dry-run
```
{
  "considered_root": "/tmp/reguard_cr3_ws",
  "dry_run": true,
  "would_remove": [],
  "would_remove_count": 0
}
```

## 18. Control-plane scale observations
- Manifest creation, SHA snapshotting, and job construction ran without observable O(n²) behaviour at n=50.
- SQLite writes scaled linearly; the executor's `ThreadPoolExecutor` with `max_workers=1` serialised work as designed.
- `build_jobs_for_run` idempotence held across three back-to-back calls (no duplicate job rows).
- Interrupt + resume on the same `corpus_run_id` left manifest + frozen SHAs unchanged; only `pending` jobs were re-driven.
- Fast UNSUPPORTED short-circuit kept wall-clock dominated by the 5 actually-executed container jobs.
- Wall-clock 161.62 s for 5 container jobs + 45 fast UNSUPPORTED short-circuits.

## 19. Anomalies / persistence observations

### 19.1 UNSUPPORTED row missing `missing_capability`
- **Position:** 12
- **Repository:** `ZhuLinsen/daily_stock_analysis`
- **Job ID:** 93
- **`compliance_status`:** `UNSUPPORTED`
- **`missing_capability`:** `NULL`
- **`execution_recipe_version`:** `v0` (should be `v1.1`)
- **`attempt_count`:** 1
- **Completed at:** 2026-08-29T16:29:23Z

**Classification:** persistence defect (intermittent). The executor's `update_evaluation_job_recipe_and_missing` call did not land for this row. The same defect appears in run 9 (15/20 rows affected, pre-v1.1.1-fix) and not in run 10 (0/20). Likely cause: a transient `sqlite3.OperationalError: database is locked` from the executor's per-call `sqlite3.connect()` pattern, caught by the `except sqlite3.IntegrityError` handler, propagated up, and silently skipped the v1.1 stamping step. **The row's `compliance_status` is correctly `UNSUPPORTED`; only the structured `missing_capability` token and the `v1.1` recipe version are absent.**

**Persistence-defect impact:** the compliance verdict is correct and would be honoured by downstream consumers; the missing structured `missing_capability` is recoverable from the combination (`adapter_name == __MISSING__`, `compliance_status == UNSUPPORTED`). Per the audit constraint **"Do not modify results simply to make counts match,"** the row is left as-is. The defect is recorded here.

### 19.2 Zero-attempt terminal job
- **Position:** 5
- **Repository:** `NousResearch/hermes-agent`
- **`compliance_status`:** `NULL` (terminalised at `build_jobs_for_run` time)
- **`error_class`:** `SHA_RESOLUTION_ERROR`
- **`adapter_name`:** `__MISSING__` (set to `__MISSING__` because SHA resolution failed before any adapter lookup)

**Classification:** by-design. The architecture supports **Option B** from the audit: pre-execution outcomes (SHA resolution failure, fast UNSUPPORTED) may legitimately terminalise without an `evaluation_attempts` row. `build_jobs_for_run` calls `crp.insert_evaluation_job(...)` with `JOB_STATUS_COMPLETED` directly when the manifest row's `sha_resolution_class` is not `ok` or `pinned`. This is documented in `src/compliance/corpus_runner/executor.py`.

## 20. Test count after gate
- Collection: `233 tests collected in 0.16s`
- Run: `233 passed in 18.00s`
- The gate did not add any new tests; the count delta vs. the pre-gate baseline of 233/233 is **+0**. The full test suite is green.

## 21. What this gate actually proved
- 50-repository selection, SHA snapshotting, and frozen-five pinning behave deterministically.
- `build_jobs_for_run` is idempotent across repeated calls.
- 50/50 jobs reach a terminal state; none lost, none duplicated.
- Interrupted resume on the same `corpus_run_id` continues from `pending` without re-running completed jobs.
- Fast UNSUPPORTED short-circuit scales: 44 repos short-circuited without source fetch or workspace.
- Source-cache and workspace invariants hold at n=50.

## 22. What this gate did NOT prove
- It did NOT prove 50-repository execution capacity. Only 5 repos actually executed (the frozen five).
- It did NOT measure compliance prevalence; the adapter set is intentionally limited to the frozen five.
- It did NOT exercise dependency caching.
- It did NOT increase concurrency.
- It did NOT prove that the v1.1 missing-capability stamping is reliable across all 50 jobs in one run (see §19.1).

## 23. Readiness for the next scale step
- **READY** for the next control-plane scale step (e.g. increasing manifest rows to 100).
- **NOT** ready to claim `100-repo compliance validation` — execution coverage is still bounded by the adapter set.
- **CONDITIONAL**: the §19.1 persistence defect should be fixed (widen the except clause or restructure to use a single connection per worker) before relying on the structured `missing_capability` column as a hard inventory.
