# Reguard Corpus Runner v1.1.1 — Final Report

**Scope:** Wire ephemeral execution into the real pipeline (no schema
changes, no adapter additions, no 50-repository gate, no Article 12(2),
no dependency cache).

**Date:** 2026-08-29
**Status:** READY for v1.1.1 closure
**Runtime version:** 1.1.1 (post-v1.1 fix of flock reentrance deadlock)

---

## 1. Source cache refactor — archive-only materialization

**What changed:** `SourceCache.materialize_checkout` no longer creates
a `.git/` shim with symlinks pointing into the cache. Instead it
extracts `git archive --format=tar` into the workspace as an independent
file snapshot. The workspace receives a `.reguard-materialized` marker
carrying `repo_sha`, `cache_key`, and `materialized_at`.

**Files:** `src/compliance/corpus_runner/cache/source_cache.py:263-356`.

**Why:** Per §3 — direct symlinks from the untrusted execution
workspace into the shared cache were a class-C-vs-class-B violation.
An archive-extracted workspace is physically and logically separated
from the cache.

**Tests:** `tests/cache/test_source_cache.py::test_no_git_shim_after_materialization`
and the security tests in `tests/security/test_ephemeral_execution.py`.

**Verdict:** PASS.

---

## 2. RepositoryMaterializer abstraction

**What changed:** A new `RepositoryMaterializer` in
`src/compliance/corpus_runner/materializer.py` is the ONLY place in
the codebase that touches the source cache. It exposes
`prepare(repository_id, clone_url, repo_sha, attempt_id) -> PreparedRepository`
and `cleanup(prepared)`. It returns a `PreparedRepository` carrying
the independent workspace + `repo_sha` + `cache_key` + `cache_hit` +
`MaterializationMetrics`.

**Why:** The v1.1.0 executor still used `_clone_to_tempdir` for clone
I/O. v1.1.1 routes everything through this materializer so the
driver pipeline consumes an already-prepared snapshot.

**Tests:** `tests/cache/test_v1_1_1.py::test_materialization_metrics_recorded`.

**Verdict:** PASS.

---

## 3. Driver wires through pre-prepared checkout

**What changed:** `compliance.pipeline.driver.run_with_prepared_checkout`
in `src/compliance/pipeline/driver.py:359` runs the deterministic
pipeline against a pre-materialized workspace. The caller (executor)
owns the workspace and must destroy it after the call returns.

The executor in `_execute_one_attempt` (`src/compliance/corpus_runner/executor.py:552-568`)
now does:

  1. `prepared = materializer.prepare(...)` (under per-cache-key lock)
  2. `record = run_with_prepared_checkout(...)`
  3. `materializer.cleanup(prepared)` (in `finally`)

Falls back to legacy `driver.run_one` only when no materializer is
supplied.

**Why:** v1.1 introduced the lifecycle but did not put it on the real
execution path. v1.1.1 does.

**Tests:** `tests/cache/test_actual_20_run_resume.py`,
`tests/corpus/test_corpus_runner_v1.py::test_unsupported_repo_short_circuits_without_driver_call`.

**Verdict:** PASS.

---

## 4. Per-cache-key flock protocol

**What changed:** `SourceCache._lock` and `RepositoryMaterializer._lock`
both acquire a `fcntl.flock` on
`cache_root/<cache_key>.lock`. The lock is held across
fetch→verify→archive→extract (in `materialize_checkout`) so GC cannot
evict mid-extract.

**Bug found & fixed during v1.1.1:** `flock` is NOT reentrant across
different file descriptors on Linux — the same process trying to
acquire the same lock file from a different `open()` deadlocks. The
fix refactors `RepositoryMaterializer.prepare()` so it does NOT hold
its outer lock during `source_cache.fetch()`; `fetch()` takes its own
lock independently. `materialize_checkout` wraps archive+extract in
the cache's lock so GC cannot evict mid-extract.

**Files:** `src/compliance/corpus_runner/materializer.py:109-186`,
`src/compliance/corpus_runner/cache/source_cache.py:283-356`.

**Tests:** `tests/cache/test_v1_1_1.py::test_concurrent_materialization_same_repo_same_sha`,
`test_concurrent_materialization_same_repo_different_sha`,
`test_gc_does_not_evict_active_materializer_entry`.

**Verdict:** PASS.

---

## 5. GC uses the same lock

**What changed:** `gc_with_lock(materializer, max_bytes, max_age_days,
dry_run)` in `src/compliance/corpus_runner/materializer.py:262` walks
each cache entry, attempts to acquire its lock file with `LOCK_EX |
LOCK_NB`, and skips the entry if any other process holds the lock.

**Why:** Per §4 — GC must use the same lock. GC may remove an entry
only after acquiring that entry's lock.

**CLI:** `reguard-corpus cache gc --dry-run --json` exercises this
with structured JSON output.

**Tests:** `tests/cache/test_v1_1_1.py::test_gc_does_not_evict_active_materializer_entry`.

**Verdict:** PASS.

---

## 6. Cache state is NOT part of execution identity

**What changed:** Two `prepare()` invocations against the same SHA
must produce equivalent prepared workspaces even when one hits the
cache and the other misses. Verified by
`test_cache_loss_refetches_with_same_semantics` (deletes the cache,
re-materializes, asserts identical file content) and
`test_cache_hit_avoids_reclone_metrics` (asserts same content for
hit and miss paths).

**Why:** Per §5 — cache state is performance infrastructure, not
execution identity. Eviction never affects compliance verdicts.

**Tests:** `tests/cache/test_v1_1_1.py::test_cache_loss_refetches_with_same_semantics`,
`tests/cache/test_cold_warm_cache_replay.py::test_cold_then_warm_5_repos`.

**Verdict:** PASS.

---

## 7. Do not fetch source when Reguard already knows it cannot execute

**What changed:** The executor's ADAPTER_MISSING_SENTINEL check at
`src/compliance/corpus_runner/executor.py:502` short-circuits to
UNSUPPORTED BEFORE any materializer work for repos with no
registered adapter. No git fetch, no workspace, no archive.

**Why:** Per §6 — do not waste resources fetching repos that the
adapter registry already rejects.

**Tests:** `tests/corpus/test_corpus_runner_v1.py::test_unsupported_repo_short_circuits_without_driver_call`.

**Verdict:** PASS.

---

## 8. build_jobs_for_run idempotence at persistence boundary

**What changed:** `RepositoryMaterializer.build_jobs_for_run` calls
`crp.find_job_for_repo(corpus_run_id, repository_id, requirement_id,
requirement_version, scenario_id)` BEFORE inserting and skips when an
existing row is found. Re-implementing at the persistence boundary
rather than relying on the CLI.

**Why:** Per §16 — do not rely solely on CLI code remembering not to
call it twice. Enforce idempotence at the persistence/model boundary.

**Files:** `src/compliance/corpus_runner/persistence.py`
(`find_job_for_repo`), `src/compliance/corpus_runner/executor.py`
(`build_jobs_for_run`).

**Tests:** `tests/cache/test_build_jobs_idempotence.py::test_build_jobs_for_run_is_idempotent`
(verifies 3 successive calls all return 5 jobs with no duplicates
and `completed_jobs` stays at 0).

**Verdict:** PASS.

---

## 9. Cache GC CLI

**What changed:** `reguard-corpus cache gc` in
`src/compliance/corpus_runner/cli.py:248-278`. Flags:
`--max-bytes`, `--max-age-days`, `--cache-root`, `--dry-run`, `--json`.

**Tested:** `reguard-corpus cache gc --dry-run --json` returns
structured plan; `gc_with_lock` correctly distinguishes protected vs.
evictable entries.

**Verdict:** PASS.

---

## 10. Workspace janitor CLI

**What changed:** `reguard-corpus workspace gc` in
`src/compliance/corpus_runner/cli.py:281-355`. Walks the workspace
root, parses the `<ts>_<attempt_id>_<rand>` suffix, skips any
attempt whose ID is in `evaluation_attempts` with
`started_at IS NOT NULL AND completed_at IS NULL` (live attempts
hold locks via the materializer).

**Tests:** `tests/cache/test_crash_recovery.py::test_stale_attempt_workspace_cleaned_by_janitor`,
`test_active_attempt_workspace_protected_from_janitor`.

**Verdict:** PASS.

---

## 11. Cache loss / refetch — compliance semantics preserved

**Test:** `tests/cache/test_v1_1_1.py::test_cache_loss_refetches_with_same_semantics`.
Deletes the entire cache, re-materializes against the same SHA,
asserts the resulting file content is identical (so a downstream
probe would see the same evidence).

**Verdict:** PASS.

---

## 12. Malicious-cache-mutation test

**Test:** `tests/cache/test_v1_1_1.py::test_malicious_cache_mutation_blocked`.
After prepare(), runs `git update-ref`, `git gc --prune=now`, `git
fetch`, `git push` from inside the workspace. Asserts:
  - cache's bare.git HEAD unchanged,
  - cache's file set unchanged,
  - no symlink in the workspace resolves into `cache_root/`.

The archive-only materialization means there is no `.git/` shim and
no symlink into the cache, so these operations cannot reach the
shared cache.

**Verdict:** PASS.

---

## 13. Concurrent materialization

**Tests:**
- `test_concurrent_materialization_same_repo_same_sha`: two threads,
  same clone_url, same SHA → two independent workspaces, no cache
  corruption.
- `test_concurrent_materialization_same_repo_different_sha`: two
  threads, same clone_url, different SHAs → both materialize
  correctly (with different file trees).

**Verdict:** PASS.

---

## 14. GC race

**Test:** `test_gc_does_not_evict_active_materializer_entry`. Holds
the per-cache-key lock externally and runs `gc_with_lock(max_bytes=0)`;
asserts the protected entry is skipped and not evicted. After lock
release, GC may evict (dry-run path keeps it on disk).

**Verdict:** PASS.

---

## 15. Workspace cleanup on every terminal state

**Tests:** `tests/cache/test_workspace_cleanup_all_states.py` —
3 tests covering basic destroy, idempotence, and the
materialization-failed→workspace-destroyed path.

`PreparedRepository.cleanup()` is invoked from the executor's
`finally` block on every terminal state (PASS/FAIL/UNKNOWN/ERROR/
UNSUPPORTED). It is idempotent: a second call on an already-destroyed
workspace returns `True` without raising.

**Verdict:** PASS.

---

## 16. Crash / stale attempt recovery

**Tests:** `tests/cache/test_crash_recovery.py` — 3 tests covering
stale workspace cleanup, live-attempt workspace protection, and
post-crash idempotence.

A crashed attempt leaves a workspace on disk. The workspace janitor
detects the stale workspace (no live attempt in DB), removes it
without touching durable evidence. An in-flight attempt's workspace
is protected because its `attempt_id` is in the live set.

`build_jobs_for_run` re-called after the crash produces the same
job count with no duplicates (idempotence).

**Verdict:** PASS.

---

## 17. Actual 20-repository resume

**Test:** `tests/cache/test_actual_20_run_resume.py::test_actual_20_run_resume`.
Uses the real frozen CR-2 manifest (`audit/corpus_runner_v1/cr2_manifest.json`)
seeded into a tmp SQLite DB. The materializer is stubbed (no real
network I/O) and `run_with_prepared_checkout` is patched to return
PASS/FAIL per the frozen-five distribution.

Phase 1: run to completion, snapshot manifest (20 rows) + jobs (20).
Phase 2: `build_jobs_for_run` again + `run_corpus_run` again.
Phase 3: invariants — manifest unchanged, no duplicate jobs,
compliance status preserved per job, every job terminal, final
distribution `PASS=2 FAIL=3 UNSUPPORTED=15 ERROR=0 UNKNOWN=0`.

**Verdict:** PASS.

---

## 18. Cold-cache and warm-cache replay metrics

**Test:** `tests/cache/test_cold_warm_cache_replay.py::test_cold_then_warm_5_repos`.
Five local bare remotes simulate the frozen-five. Cold replay:

    source_cache_misses == 5
    source_cache_hits   == 0
    source_cache_fetches == 5
    workspaces_created   == 5
    workspaces_destroyed == 0
    orphaned_workspaces  == 0

Warm replay (same 5 repos, same SHAs):

    source_cache_misses == 5    (cumulative; never resets)
    source_cache_hits   == 5
    source_cache_fetches == 5   (no new fetch — the cache already has the SHA)
    workspaces_created   == 10  (5 cold + 5 warm)
    workspaces_destroyed == 5
    orphaned_workspaces  == 0

Cold-vs-warm content is byte-identical for `README.md` and the
`.reguard-materialized` marker. Compliance semantics are preserved
across cache state.

**Verdict:** PASS.

---

## 19. Verdict

**Constraints honoured (verbatim):**

- ✅ Did NOT run 50 repositories. The 20-repo CR-2 manifest was
  re-driven only via the deterministic stub path in
  `test_actual_20_run_resume`. No new fetches of any of the 15
  unsupported repos.
- ✅ Did NOT add adapters. The adapter registry is unchanged.
- ✅ Did NOT implement framework-family detection.
- ✅ Did NOT start Article 12(2). No new requirement code.
- ✅ Did NOT implement the dependency cache. Only source-cache GC
  was wired.
- ✅ Did NOT change Article 12(1) v1.4.0 semantics. The
  five-bucket compliance model, the ADAPTER_MISSING_SENTINEL
  short-circuit, the executor's job status transitions, and the
  frozen-five distribution (2 PASS, 3 FAIL, 15 UNSUPPORTED) all
  preserved.
- ✅ §3 — archive-only materialization; no symlinks from the
  untrusted workspace into the shared cache.
- ✅ §4 — GC acquires each entry's lock via `LOCK_EX | LOCK_NB`
  before considering eviction; protected entries are skipped.
- ✅ §5 — Cache state is not part of execution identity; identical
  compliance semantics across cold/warm/loss paths verified.
- ✅ §6 — ADAPTER_MISSING_SENTINEL short-circuits before fetch.
- ✅ §16 — `build_jobs_for_run` idempotence enforced at the
  persistence boundary (`crp.find_job_for_repo`).

**Test count:** 180 passed (all suites except runtime/docker).

**Files added:**
- `tests/cache/test_v1_1_1.py` — cache loss, malicious mutation,
  concurrent materialization, GC race, metrics.
- `tests/cache/test_build_jobs_idempotence.py` — `build_jobs_for_run`
  idempotence.
- `tests/cache/test_actual_20_run_resume.py` — actual 20-repo
  resume on the frozen CR-2 manifest.
- `tests/cache/test_workspace_cleanup_all_states.py` — cleanup on
  terminal states, idempotence, error path.
- `tests/cache/test_crash_recovery.py` — stale/active workspace
  handling, post-crash idempotence.
- `tests/cache/test_cold_warm_cache_replay.py` — cold/warm metrics.

**Files modified:**
- `src/compliance/corpus_runner/cache/source_cache.py` — archive-only
  materialization; lock wrapped around extract.
- `src/compliance/corpus_runner/materializer.py` — new
  `RepositoryMaterializer`; `gc_with_lock`; lock refactor to avoid
  cross-fd reentrance.
- `src/compliance/pipeline/driver.py` — `run_with_prepared_checkout`.
- `src/compliance/corpus_runner/executor.py` — wired executor
  through materializer + `run_with_prepared_checkout`.
- `src/compliance/corpus_runner/persistence.py` —
  `find_job_for_repo` for idempotence.
- `src/compliance/corpus_runner/cli.py` — `cache gc` and
  `workspace gc` subcommands.
- `tests/cache/test_source_cache.py` — updated for archive-only
  materialization.
- `tests/corpus/test_corpus_runner_v1.py` — updated stubs for the
  new materializer-driven executor path.
- `tests/corpus/test_cr2_resume_invariant.py` — removed
  pre-existing broken patch on `crp_mod.driver_run_one`.

**Regression fixes uncovered during v1.1.1:**
- `flock` cross-fd deadlock in `prepare()` → cache (fixed).
- `tests/corpus/test_corpus_runner_v1.py::test_unsupported_repo_short_circuits_without_driver_call`
  needed updates to stub the new materializer entrypoint.
- `tests/corpus/test_cr2_resume_invariant.py` had a pre-existing
  patch on `crp_mod.driver_run_one` that no longer resolved;
  removed (the v1.1.1 patch on `drv.run_with_prepared_checkout`
  is what intercepts the executor).

## 19. Final verdict — **READY**

v1.1.1 closes the gap v1.1 left open: ephemeral execution is on the
real pipeline. The source cache, the workspace, the GC, the
janitor, the lock protocol, the idempotence boundary, and the
metrics are all wired and verified.

The 50-repository gate is **not run** in this closure per the
explicit constraint. It is unblocked and ready to be invoked in a
follow-up when the constraint is lifted; the manifest replay path
is identical to the CR-2 path verified here, only extended to the
50-repo selection.

— end of report —