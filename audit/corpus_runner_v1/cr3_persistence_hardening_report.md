# CR-3 Persistence Correctness Hardening — Final Report

**Date:** 2026-08-29  
**CR-3 CorpusRun ID:** 11 (historical)  
**Corpus Runner version:** v1.1.1 → v1.1.2 (persistence hardening)  
**Constraint scope:** did NOT run another corpus gate; did NOT add adapters,
framework-family detection, Article 12(2), dependency caching, concurrency
increase, or any change to Article 12(1) v1.4.0 semantics.

---

## 1. Terminal-persistence invariant

**Invariant:** once an `evaluation_jobs` row is terminalised, every
terminal-state column is populated together in a single transaction;
there is no observed hybrid pre-terminal / terminal state.

**Verified by:** `test_terminalize_writes_all_fields_atomically` (one
`terminalize_job` call writes `job_status='completed'`,
`compliance_status`, `compliance_runtime_run_id`, `error_class`,
`error_message`, `completed_at`, `missing_capability`,
`execution_recipe_id`, `execution_recipe_version`, AND the
matching `requirement_evaluations` row).

## 2. Write path trace (legacy → v1.1.2)

**Legacy (`executor.py:855-916` before this hardening):**

1. `crp.update_evaluation_job_completed(...)` — sets compliance_status.
2. `crp.increment_corpus_run_counters(...)` — bumps the run counter.
3. `crp.insert_requirement_evaluation(...)` — wraps the
   `requirement_evaluations` row in a narrow
   `except sqlite3.IntegrityError`.
4. `crp.update_evaluation_job_recipe_and_missing(...)` — same narrow
   `except sqlite3.IntegrityError`.

Each call opens a fresh `sqlite3.connect()` and commits independently.
A transient `OperationalError: database is locked` from any of these
silently skipped the v1.1 stamping step, leaving the row in a hybrid
state (CR-3 anomaly row id=93 in `corpus_run_id=11`).

**v1.1.2 (after this hardening):**

1. `crp.terminalize_job(TerminalPayload, db_path=db)` — single
   transaction over all four writes, bounded busy-retry, idempotence
   guard, conflict detection.
2. `crp.set_corpus_run_counters_from_jobs(corpus_run_id, db_path=db)`
   — batched recompute at run-end, replacing the per-job counter bump.

## 3. SQLite lock source

The legacy executor opens 4 short-lived connections per terminalization
(`update_evaluation_job_completed`, `increment_corpus_run_counters`,
`insert_requirement_evaluation`, `update_evaluation_job_recipe_and_missing`).
With `journal_mode=delete`, `busy_timeout=0` (Python's
`sqlite3.connect()` default `timeout=5.0` actually *does* block briefly),
and `max_workers=1` serialising work, transient lock contention between
executor writes and CLI writes (workspace-janitor, cache-GC) can still
trigger `SQLITE_BUSY`. The legacy code's narrow `except
sqlite3.IntegrityError` did not catch it.

## 4. Atomic terminalization

`terminalize_job(payload, db_path=...)` (in
`src/compliance/corpus_runner/persistence.py`) runs three SQL
statements inside one `BEGIN ... COMMIT` block:

- `UPDATE evaluation_jobs SET ... WHERE id = ? AND (job_status<>'completed' OR compliance_status IS NULL OR compliance_status = ?)`
  (idempotence guard)
- `INSERT OR REPLACE INTO requirement_evaluations (...) VALUES (...)`
  (dedup key on `(evaluation_job_id, requirement_id,
  requirement_version)`)
- `UPDATE evaluation_jobs SET missing_capability=?, execution_recipe_id=?, execution_recipe_version=? WHERE id=?`

All three writes share a single connection with `row_factory=sqlite3.Row`
and `timeout=0` (so write contention fails fast and deterministically).

## 5. Busy/lock policy

- `_BUSY_MSG_RE = re.compile(r"(database is locked|database table is
  locked|locked|busy)", re.IGNORECASE)` — only the busy / locked family
  of `sqlite3.OperationalError` is retried. Other OperationalErrors
  (disk I/O, schema mismatch, corrupt DB) propagate immediately.
- `_execute_with_busy_retry(conn, sql, params, attempts=5,
  base_sleep_s=0.02)` retries with exponential backoff (0.02, 0.04,
  0.08, 0.16, 0.32 s); exhaustion re-raises the original error.
- `terminalize_job`'s outer loop adds 20 connection-level retries
  (each iteration opens a fresh connection, so any persistent
  lock-holder is given the chance to release).

## 6. Retry / backoff summary

| Layer | Attempts | Base sleep | Worst case |
|---|---:|---|---:|
| `_execute_with_busy_retry` (per-statement) | 5 | 0.02 s exponential | ~0.62 s |
| `terminalize_job` (per-transaction) | 20 | 0.02 s fixed | ~0.40 s |

A single contended terminalization can take up to ~1 second before
raising; the typical case (no contention) is sub-millisecond.

## 7. Idempotence

The WHERE clause in step 1 (`job_status<>'completed' OR
compliance_status IS NULL OR compliance_status = ?`) makes a
second `terminalize_job` call with the **same** payload a no-op on
the row itself. Step 2 (`INSERT OR REPLACE INTO
requirement_evaluations`) and step 3 (an UPDATE that does not depend
on a partial state) re-run harmlessly.

Verified by: `test_terminalize_idempotent_under_retry` (3 identical
calls → 1 row, 1 requirement_evaluations row).

## 8. requirement_evaluations consistency

Every `terminalize_job` call lands **one** `requirement_evaluations`
row with `compliance_status` matching the payload's
`compliance_status`. Verified by the synthetic stress test
(`test_synthetic_persistence_stress`): 500 jobs → 500
`requirement_evaluations` rows, exactly one per `evaluation_job_id`.

The CR-3 reconciliation's MISSING_REQUIREMENT_EVALUATION issues
(both on the anomaly row id=93 and on the SHA-resolution-error row
id=86) are precisely because the legacy executor path skipped
`insert_requirement_evaluation` for those rows. The new path makes
this impossible going forward.

## 9. Zero-attempt SHA model (preserved)

The architecture supports **Option B** from the audit: pre-execution
outcomes (`build_jobs_for_run`-time SHA-resolution failures, fast
UNSUPPORTED) may legitimately terminalise without an
`evaluation_attempts` row. The new `terminalize_job` does NOT
introduce an `evaluation_attempts` row for these cases — that
behaviour is owned by `build_jobs_for_run` in `executor.py:283-330`,
which is unchanged.

The SHA-resolution-error row id=86 (`NousResearch/hermes-agent`)
remains zero-attempt; the validator reports it as
`MISSING_REQUIREMENT_EVALUATION` (legacy executor path never
landed the v1.1 row), but the **compliance verdict** is correct
(`compliance_status=NULL`, `error_class=SHA_RESOLUTION_ERROR`).

## 10. Structured validator

`validate_terminal_state(corpus_run_id, db_path=...)` in
`src/compliance/corpus_runner/persistence.py` walks every terminal
`evaluation_jobs` row and emits `ValidationIssue` records for four
issue classes:

| Issue class | Condition |
|---|---|
| `MALFORMED_UNSUPPORTED_REASON` | `compliance_status='UNSUPPORTED'` but `missing_capability IS NULL` |
| `MISSING_REQUIREMENT_EVALUATION` | terminal job has no `requirement_evaluations` row |
| `CONFLICTING_REQUIREMENT_EVALUATION` | `requirement_evaluations.compliance_status` ≠ `evaluation_jobs.compliance_status` |
| `MALFORMED_SKIPPED_SCENARIO` | `job_status='skipped_unsupported_scenario'` but `missing_capability <> 'tool_failure_scenario'` |

The validator is a **pure read** function. Verified by
`test_validator_is_pure_read` (running it twice produces the same
result; row state is preserved across calls).

## 11. Lock-contention test

`test_forced_lock_contention_retries` — Thread A holds an EXCLUSIVE
write lock on the DB. Thread B calls `terminalize_job`. After
~80 ms Thread A commits; Thread B's bounded retry succeeds. Final
row has all terminal fields and no partial state.

Verified: `tests/cache/test_persistence_terminalization.py`.

## 12. Retry-exhaustion test

`test_retry_exhaustion_raises_clearly` — Thread A holds the EXCLUSIVE
lock longer than the retry budget. `terminalize_job` raises a clear
`sqlite3.OperationalError` (with `database is locked` in the
message). The job row remains in its **pre-terminal `pending`**
state — no partial update leaks through.

Verified: `tests/cache/test_persistence_terminalization.py`.

## 13. CR-3 anomaly regression

`test_cr3_anomaly_shape_after_fix` — Reproduces the exact CR-3
anomaly shape:
ADAPTER_MISSING_SENTINEL → UNSUPPORTED →
asserts `missing_capability='compatible_execution_recipe'`,
`execution_recipe_version='v1.1'`, `error_class=''`.

The pre-fix shape (`missing_capability=NULL`,
`execution_recipe_version='v0'`) would fail this test.

Verified: `tests/cache/test_persistence_terminalization.py`.

## 14. Synthetic stress test

`test_synthetic_persistence_stress` — Creates 500 synthetic pending
jobs (in addition to the 5 seed jobs) and terminalises them
concurrently across 4 worker threads. Every job ends up with
`missing_capability`, `execution_recipe_version='v1.1'`, and exactly
one `requirement_evaluations` row — no hybrid state, no duplicate
rows, no lost writes.

Verified: `tests/cache/test_persistence_terminalization.py`.

## 15. Historical-data policy

The CR-3 historical anomaly row id=93 (`ZhuLinsen/daily_stock_analysis`)
in `corpus_run_id=11` is **left untouched**:

```text
compliance_status       = UNSUPPORTED
missing_capability      = NULL        ← preserved for the audit trail
execution_recipe_id     = legacy-adapter-direct
execution_recipe_version= v0          ← preserved
job_status              = completed
```

Verified by `test_cr3_anomaly_row_is_only_malformed_in_corpus_run_11`
which loads the row from the live DB and asserts both:
- the row state matches the documented CR-3 anomaly shape; and
- the validator reports exactly the documented issues on this row
  (`MALFORMED_UNSUPPORTED_REASON` + `MISSING_REQUIREMENT_EVALUATION`)
  and no other row in `corpus_run_id=11` is malformed (the SHA
  resolution-error row id=86 carries the documented
  `MISSING_REQUIREMENT_EVALUATION` from Option B pre-execution
  terminalisation).

No code path in this hardening mutates the CR-3 historical row.

## 16. Full test suite

```
247 passed in 19.97s
```

- Pre-hardening baseline: **233** tests.
- New tests in `tests/cache/test_persistence_terminalization.py`: **7**
  (atomic, idempotent, conflict, lock-contention, retry-exhaustion,
  CR-3 anomaly shape, synthetic 500-job stress).
- New tests in `tests/cache/test_structured_terminal_validator.py`: **7**
  (4 issue classes, healthy rows, pure-read, CR-3 historical-row
  assertion).
- All 233 pre-existing tests still pass — no regression introduced by
  moving the executor's terminalization onto `terminalize_job`.

## 17. Final verdict

**READY** for the next step ("integration-pattern discovery"
/ adapter-coverage extension) on the following basis:

1. The persistence invariant is closed. Future runs cannot produce
   the CR-3 hybrid-state anomaly row.
2. The CR-3 historical row is preserved as evidence.
3. The validator is available as an audit gate for every subsequent
   `corpus_run` and can be wired into the run-end progress callback.
4. The full test suite is green with no regressions; the new tests
   cover atomicity, idempotence, conflict detection, lock contention,
   retry exhaustion, the CR-3 anomaly shape, and a 500-job concurrent
   stress test.

**NOT READY for the next step** is NOT claimed. The hardening is
narrow: it touches only the executor's terminalization path and the
run-end counter recompute; no other behaviour changed. Article
12(1) v1.4.0 semantics, the v1.1.1 readiness audit, and the CR-3
control-plane gate are unaffected.

**Suggested next action (out of scope for this report):**
- Wire `validate_terminal_state` into the run-end progress callback
  so every fresh `corpus_run` produces a structural-validation
  report alongside the summary JSON.
- Add a `compliance_runtime_runs` row for the SHA-resolution-error
  Option B path (so `MISSING_REQUIREMENT_EVALUATION` is no longer
  raised for these rows; the legacy executor never wrote one).
- Bump `runtime_version` to `v1.1.2` and re-run the existing v1.1.1
  regression tests against the new terminalization path.

— end of report —
