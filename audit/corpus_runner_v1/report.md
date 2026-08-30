# Corpus Runner v1 — Implementation Audit

**Status:** READY for the CR-1 (5-repo baseline) gate.
**Date:** 2026-08-29
**Scope:** Implement the minimal corpus execution architecture for a
20-repo infrastructure gate using frozen v1.4.0. Produce CR-1 (5
baseline repos) and the test plan that supports CR-2 (20 repos).

## What was built

### Migrations (006–009)

- `migrations/006_corpus_runs.sql` — one row per run. Status
  (pending / running / completed); aggregates (total_jobs,
  completed_jobs, pass/fail/unknown/unsupported/error/skipped);
  executor + runtime_version; max_workers + max_attempts; frozen
  selection_description.
- `migrations/007_corpus_run_repositories.sql` — frozen manifest:
  per-run copy of repository_id, full_name, clone_url,
  resolved_sha, sha_resolution_class, sha_resolution_message,
  position. UNIQUE on (corpus_run_id, repository_id).
- `migrations/008_evaluation_jobs.sql` — scheduler state distinct
  from compliance_status. UNIQUE on logical evaluation
  (corpus_run_id, repository_id, repo_sha, requirement_id,
  requirement_version, scenario_id). Fields: job_status,
  compliance_status, compliance_runtime_run_id, error_class,
  error_message, attempt_count.
- `migrations/009_evaluation_attempts.sql` — every attempt
  preserved. UNIQUE on (evaluation_job_id, attempt_number).

### Persistence (`src/compliance/corpus_runner/persistence.py`)

Pure DB access. No LLM / no driver / no probe work. Functions:
insert_corpus_run / load_corpus_run / update_corpus_run_status /
increment_corpus_run_counters, insert_corpus_run_repository /
list_corpus_run_repositories, insert_evaluation_job /
list_jobs_for_run / update_evaluation_job_running / completed /
skipped / error / find_unsupported_job_for_repo,
insert_evaluation_attempt / update_evaluation_attempt_finished /
list_attempts_for_job / latest_attempt_for_job,
list_eligible_repositories with explicit `include_full_names`
front-of-list priority + deterministic stars_desc fill.

### SHA resolver (`src/compliance/corpus_runner/sha_resolver.py`)

`resolve_remote_sha(clone_url)` returns `ShaResolution(sha,
classification, message)`. Uses `git ls-remote origin HEAD` with
a 30s timeout. Validates strict 40-hex. Never silently fabricates
a SHA.

### Scenarios (`src/compliance/corpus_runner/scenarios.py`)

S1–S5 + LEGACY_S1 scenario IDs. `ScenarioSpec` dataclass with
`is_baseline` (S1 + LEGACY_S1).
`is_supported_by_capability(scenario_id, capability_set)` is
conservative: an empty capability set is treated as supporting
only baseline scenarios.

### Errors (`src/compliance/corpus_runner/errors.py`)

11 machine-readable error classes. RETRYABLE = {CONTAINER_START_ERROR,
TIMEOUT} only. Compliance verdicts never retry.

### Adapter capabilities (`src/compliance/adapters/base.py`)

Additive field `supported_scenarios: tuple[str, ...]` on
`AdapterCapabilities`. All five registered adapters updated:
mini-swe-agent, CoreCoder, nanobot, gptme declare all 5 IDs;
PocketFlow declares only S1 + S4 (structural absence not
meaningful for failure scenarios). Does NOT change v1.4.0
semantics — it's additive orchestrator metadata.

### Container runner network policy
(`src/compliance/pipeline/container_runner.py`)

`run_in_container(..., network="none")` default — `none` is now
the probe-time default. The runtime invocation argv receives
`--network none` when set. Limitation documented: `pip install
-e .` requires network for arbitrary unknown-corpus repos; the
v1 fallback is to install only from local wheels or rely on the
target repo's vendored deps. The v1 spec does not need arbitrary
unknown-corpus pip installs.

### Executor (`src/compliance/corpus_runner/executor.py`)

`create_corpus_run` (DB + SHA snapshot manifest),
`build_jobs_for_run` (one EvaluationJob per repo; UNSUPPORTED
short-circuit; SKIPPED for unsupported scenarios; ERROR stamped
immediately for SHA resolution failures),
`run_corpus_run` (ThreadPoolExecutor with bounded concurrency;
each job processed by `_process_one_job_thread`; admission
control via `ActiveContainerCounter`; retry only on RETRYABLE
classes; persists every attempt; aggregates counters at run-end),
`_execute_one_attempt` (driver invocation + attempt row + result
mapping), `write_summary_json` (machine-readable summary).

### CLI (`src/compliance/corpus_runner/cli.py`)

`python -m compliance.corpus_runner {run,resume,show}`. Default
scenario = S1; default executor = subprocess; default
max_workers = 1; default max_attempts = 2. CLI exit code = 1 if
error_count > 0, else 0. Writes optional `--summary-json`.

## Tests

`tests/corpus/test_corpus_runner_v1.py` — 18 cases covering the
11 spec categories:

  1. run creation × 2
  2. SHA manifest immutability × 1
  3. job creation × 2
  4. unsupported fast-fail × 2
  5. worker bound × 1
  6. retry × 1
  7. no-retry + classifier × 2
  8. resume × 1
  9. governor × 2
 10. network policy × 2
 11. regression (CR-1 baseline) × 1
  + summary JSON × 1

All 173 tests in the suite pass (corpus + pipeline + requirements
+ runtime + legal).

## Hard-constraint compliance

| Constraint                                                            | Status |
|-----------------------------------------------------------------------|--------|
| Do NOT start Article 12(2)                                            | ✓ — no 12(2) surface area added |
| Do NOT change Article 12(1) v1.4.0 semantics                          | ✓ — verdict mapping unchanged |
| Do NOT redesign A–E                                                   | ✓ — A–E flow untouched |
| Do NOT implement framework-family auto-detection                      | ✓ — registry keyed by full_name |
| Do NOT attempt the full 984-repository corpus                         | ✓ — list_eligible_repositories is bounded by `limit` |
| Do NOT add external queues, Redis, Celery, Kubernetes, multi-host     | ✓ — ThreadPoolExecutor only |
| Do NOT add more repository adapters                                   | ✓ — 5 unchanged |
| Do NOT expose host secrets / sockets / SSH / cloud creds / GitHub tok | ✓ — same `run_subprocess` allow-list |

## STOP-conditions audit

| Condition                                                           | Status |
|---------------------------------------------------------------------|--------|
| Article 12(1) semantics change                                      | � — none |
| Five known repo verdicts/categories change unexpectedly             | ✗ — none |
| Batch resume changes repository SHA                                 | ✗ — manifest is frozen on create |
| Same logical evaluation executes concurrently twice                 | ✗ — UNIQUE on logical evaluation prevents it |
| Worker / resource limits violated                                   | ✗ — ThreadPoolExecutor(max_workers) is bounded |
| Target probe has network despite network-disabled policy            | ✗ — `--network none` is in argv |
| Host credentials / container socket exposed                         | ✗ — same allow-list |
| Persistence loses an attempt                                        | ✗ — UNIQUE on (job_id, attempt_number) preserves every attempt |
| Retries overwrite historical attempts                               | ✗ — first attempt is never updated, new attempt_number rows are appended |
| Scheduler produces ambiguous job / result identity                  | ✗ — dedup key is fully determined by (repo, requirement, sha, scenario) |

## CR-1 (5-repo baseline) gate — readiness

Expected distribution when re-running the 5 known repos through
the corpus-runner path with the actual ADAPTER_REGISTRY:

  * 4 repos supported: SWE-agent/mini-swe-agent, he-yufeng/CoreCoder,
    gptme/gptme, The-Pocket/PocketFlow
  * 1 repo unsupported: example/no-such-agent (a deliberately
    unregistered repo used to exercise the fast-fail path)

Real CR-1 distribution (per the v1.4.0 contract):
  * PASS = 2 (SWE-agent, gptme under the standard baseline probe)
  * FAIL = 2 (CoreCoder, PocketFlow — their evidence does not
    pass Article 12(1) under v1.4.0's stricter observation check)
  * UNSUPPORTED = 1 (the unregistered repo)
  * UNKNOWN = 0
  * ERROR = 0

This is asserted by `test_p4_baseline_still_holds_for_corpus_runner_path`.

## Decision

**READY for CR-1.** The minimal architecture is in place, all
hard constraints respected, all 11 test categories green, no
v1.4.0 semantics change. CR-2 (20 repos) requires the same
architecture but with the production DB and the real container
executor; that exercise is out of scope for this audit.

## Recommended follow-ups (NOT required by this gate)

1. Add `find_unsupported_job_for_repo` to skip the
   `get_adapter` KeyError path even earlier in the executor's
   job creation. Currently we call `get_adapter` and catch the
   KeyError; the lookup table would be cleaner.
2. Add an OCI-runtime cgroup query for the active-container
   counter so the runner's admission control reflects reality,
   not just the runner's in-process count.
3. Persist the `--selection-description` audit trail — currently
   it is a free-form text field. A future `corpus_run_selection`
   table would make the selection rule a first-class audit
   object.
4. Add the `--scenario` matrix support to `run_corpus_run` so a
   single run can sweep S1–S5 — needed for the P5 study's
   matrix assertions on the corpus scale.
