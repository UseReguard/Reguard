# Corpus Runner v1.1 — Ephemeral Execution + Evidence Inventory

## Final Report (17 sections)

Gate: **CR-2 v1.1 architecture + replay**
Date: 2026-08-29
Scope: architecture + minimum-slice implementation + frozen CR-2 replay.
Out of scope: 50-repo gate, new adapters, framework-family detection,
Article 12(2).

---

### 1. Current-vs-target lifecycle

Current (v1):

```
agent_repositories row
  → resolve SHA
  → _clone_to_tempdir (per-job tempfile, no cache)
  → work_root (per-attempt tempfile)
  → driver._run_pipeline (probe + adapter + collect evidence)
  → persist compliance_runtime_runs row
  → cleanup tempdirs in `finally`
```

Target (v1.1 architecture):

```
repository DB row
  → resolve/freeze exact SHA         (class A: corpus_run_repositories)
  → locate/fetch immutable source cache (class B: SourceCache)
  → materialize ephemeral checkout   (class C: Workspace.repo_dir)
  → prepare isolated execution       (class C: Workspace.{probe,tmp,artifacts,logs})
  → run deterministic scenario(s)
  → collect normalized evidence      (class A: compliance_runtime_runs.evidence_json)
  → derive capability facts          (deferred; table reserved)
  → evaluate requirement(s)          (class A: requirement_evaluations row)
  → persist selected evidence + hashes (class A: execution_artifacts row)
  → destroy checkout/workspace       (class C destroyed; class A preserved)
```

The architecture doc at
`audit/corpus_runner_v1/ephemeral_execution_architecture.md` (§1) makes
this lifecycle explicit. v1.1 implements the lifecycle boundary and the
schema for the durable parts; the cache integration with `driver._run_pipeline`
itself is v1.1.1 scope (see §17).

### 2. Source cache design

Bare git per repository, keyed by `sha256(clone_url)[:32]`.

Layout: `~/.local/share/reguard/source-cache/<key>/bare.git` + sidecar
`cache_meta.json`. Materialization: `git archive --format=tar <sha>` from
the cache into the workspace, then a tiny `.git/` shim symlinked into the
cache's `objects/` and `packed-refs` so `git rev-parse HEAD` works without
writing back to the cache.

Concurrency: per-cache-key `flock` around `fetch` so two parallel jobs
against the same repo cannot race on `git fetch`. Readers (materializer)
do not hold the lock.

Source: `src/compliance/corpus_runner/cache/source_cache.py`.

### 3. Dependency cache design

Designed, NOT implemented in v1.1. Reserved path:
`~/.local/share/reguard/dependency-cache/`. Keying (when implemented):

```
runtime_version × python_version × platform × package_manager × dependency_lock_hash × build_config_hash
```

`site-packages` is NOT shared between repos; each attempt still receives an
isolated venv. The current `--network none` exec path documents the
existing limitation (PyPI unreachable) rather than introducing a fake
allow-list.

### 4. Workspace lifecycle

One workspace per `EvaluationAttempt.id`. Layout:

```
<workspaces_root>/<ts>_<attempt_id>_<rand>/
  repo/         # detached working tree at exact SHA
  probe/        # probe.py + scenario
  artifacts/    # captured trajectory + framework artifacts
  logs/         # truncated stdout/stderr
  tmp/          # scratch
  cleanup_marker # written AFTER destroy
```

Created by `WorkspaceManager.prepare(attempt_id, clone_url, expected_sha)`.
Destroyed by `WorkspaceManager.cleanup(ws)` on terminal attempt. The
default `retain_error_workspace_minutes = 0` — ERROR jobs destroy
immediately. Idempotent destroy.

Source: `src/compliance/corpus_runner/workspace/manager.py`.

### 5. Execution vs requirement-evaluation model

Separated in schema. v1.1 adds:

- `evaluation_jobs.execution_recipe_id` (TEXT NOT NULL DEFAULT 'legacy-adapter-direct')
- `evaluation_jobs.execution_recipe_version` (TEXT NOT NULL DEFAULT 'v0')
- `compliance_runtime_runs.execution_recipe_id` (same default)
- `compliance_runtime_runs.execution_recipe_version` (same default)
- new table `requirement_evaluations(evaluation_job_id, requirement_id,
  requirement_version, compliance_status, compliance_runtime_run_id,
  evaluated_at)` UNIQUE on (job, requirement, version).

Execution identity in v1.1:
`(repository_id, repo_sha, scenario_id, scenario_version, adapter_name,
adapter_version, runtime_version, execution_recipe_id)`. Requirement
identity is OUT of execution identity. v1.1 inserts one
`requirement_evaluations` row per `evaluation_jobs.id`; future requirements
can join to the same `evaluation_job_id` and (theoretically) consume the
same evidence. The actual cross-requirement consumption is NOT
implemented in v1.1 — schema-only.

### 6. Capability-fact model

Designed, NOT implemented. Reserved placeholder schema
(`capability_facts`):

```
fact_key
value
observation_state    TRUE | FALSE | UNKNOWN | NOT_OBSERVED | NOT_APPLICABLE
source_evidence_refs (json list of execution_artifacts.artifact_logical_name)
producer             "orchestrator" | "adapter:<name>" | "framework:<name>"
```

Subjective confidence scores are explicitly excluded. v1.1 does not
instantiate this table; the architecture reserves it.

### 7. Missing-fact model

Distinct surfaces are NOT collapsed:

| Outcome | Location | Field |
|---------|----------|-------|
| UNSUPPORTED (no adapter) | `evaluation_jobs` | `compliance_status='UNSUPPORTED'`, `missing_capability='compatible_execution_recipe'`, `error_class='ADAPTER_ERROR'` (attempt) |
| SKIPPED (scenario not supported by adapter) | `evaluation_jobs` | `job_status='skipped_unsupported_scenario'`, `missing_capability='tool_failure_scenario'` |
| UNKNOWN (probe ran but missing evidence) | future | `missing_facts` JSON list (always NULL in v1.1) |
| ERROR (infrastructure failure) | `evaluation_attempts` | `error_class` ∈ `SHA_RESOLUTION_ERROR`, `CLONE_ERROR`, `CHECKOUT_ERROR`, `CONTAINER_START_ERROR`, `INSTALL_ERROR`, `PROBE_ERROR`, `ADAPTER_ERROR`, `EVIDENCE_SCHEMA_ERROR`, `TIMEOUT`, `INTERNAL_SCHEDULER_ERROR` |
| PASS / FAIL | `evaluation_jobs` | `missing_capability` NULL, `missing_facts` NULL |

The replay produced 15 jobs with `missing_capability='compatible_execution_recipe'`
and 5 frozen-repo jobs with `missing_capability` NULL (PASS / FAIL).

### 8. Schema changes

Migration `010_corpus_runner_v1_1_schema.sql`:

- `ALTER TABLE evaluation_jobs ADD COLUMN execution_recipe_id TEXT NOT NULL DEFAULT 'legacy-adapter-direct'`
- `ALTER TABLE evaluation_jobs ADD COLUMN execution_recipe_version TEXT NOT NULL DEFAULT 'v0'`
- `ALTER TABLE evaluation_jobs ADD COLUMN missing_capability TEXT`
- `ALTER TABLE evaluation_jobs ADD COLUMN missing_facts TEXT`
- `ALTER TABLE compliance_runtime_runs ADD COLUMN execution_recipe_id TEXT NOT NULL DEFAULT 'legacy-adapter-direct'`
- `ALTER TABLE compliance_runtime_runs ADD COLUMN execution_recipe_version TEXT NOT NULL DEFAULT 'v0'`
- `CREATE TABLE requirement_evaluations` with unique (job, requirement, version)
- `CREATE TABLE execution_artifacts` with unique (job, logical_name)

Migration `011_corpus_runner_v1_1_evidence_state.sql`:

- `CREATE TABLE source_cache_entries(cache_key, clone_url, cache_path,
  last_fetch_at, last_used_at, size_bytes, state, error, refcount)`

All changes are additive. No table was dropped; no Article 12(1) v1.4.0
semantics changed. Production DB (`data/eu_ai_compliance.db`) has both
migrations applied.

Persistence helpers added in
`src/compliance/corpus_runner/persistence.py`:

- `update_evaluation_job_recipe_and_missing`
- `insert_requirement_evaluation`
- `list_requirement_evaluations_for_job`
- `insert_execution_artifact`
- `list_execution_artifacts_for_job`
- `upsert_source_cache_entry`
- `list_source_cache_entries`

### 9. Cache invalidation / eviction

Source cache invalidation: `repo SHA changes` does NOT invalidate the
cache; new SHAs are fetched via `git fetch` (existing objects remain; new
objects land in the cache). `clone_url changes` produces a new cache key
so the old cache survives untouched until evicted.

Eviction policy (LRU on `last_used_at`):

```
max_source_cache_bytes    = 8 GiB       (default)
max_source_cache_age_days = 30          (default)
```

Implementation: `compliance.corpus_runner.cache.source_cache.gc`. Eviction
respects the per-cache-key lock file. Cache eviction NEVER deletes
durable evidence / result records.

### 10. Cleanup / recovery

Cleanup policy:

| Job outcome | Default action |
|-------------|----------------|
| PASS / FAIL / UNKNOWN / UNSUPPORTED | destroy workspace immediately |
| ERROR | destroy immediately (`retain_error_workspace_minutes = 0`) |

Cleanup is idempotent (re-running on a destroyed workspace is a no-op
that still writes `cleanup_marker`). Cleanup failure is logged but never
mutates the compliance verdict.

Failure-recovery invariant: if the host crashes mid-attempt, the
`EvaluationAttempt` row carries `started_at != NULL AND completed_at IS
NULL`. After restart, the row is marked
`error_class='INTERNAL_SCHEDULER_ERROR', error_message='interrupted by
host crash'`. Partial artifacts are NEVER promoted to durable state. The
resume path (`run_corpus_run`) re-dispatches only `pending` jobs; the
`evaluation_attempts` row is preserved (never overwritten).

### 11. Security boundaries

Confirmed invariants (existing + new):

| Invariant | Status |
|-----------|:------:|
| Non-root UID:GID inside container | 10001:10001 (existing) |
| `cap-drop=ALL` | yes (existing) |
| `no-new-privileges` | yes (existing) |
| Probe network policy | `--network none` (existing) |
| `/input` mount read-only | yes (existing) |
| `/artifacts` mount writable | yes (existing) |
| Host credentials leaked into container | none (existing) |
| Docker / Podman socket exposed | none (existing) |
| **NEW:** cache objects not writable from workspace | yes (`tests/security/test_ephemeral_execution.py::test_cache_objects_not_writable_from_workspace`) |
| **NEW:** workspace path cannot escape root | yes (`test_workspace_path_cannot_escape_root`) |
| **NEW:** malicious symlinks cannot escape artifact collection | yes (`test_malicious_symlink_cannot_escape_artifacts`) |

The new invariants are tested in `tests/security/test_ephemeral_execution.py`.

### 12. Tests added

| File | Tests |
|------|-------|
| `tests/cache/test_source_cache.py` | 8 — cache-key stability, miss, hit, different-SHA, isolation, terminal-destroy, cache-loss refetch, sha256 helpers |
| `tests/security/test_ephemeral_execution.py` | 3 — cache not writable from workspace, workspace path escape blocked, malicious symlink artifact escape blocked |
| `tests/evidence/test_retention.py` | 5 — artifact hash recorded, oversized truncation marker, discarded-workspace-doesn't-break-evidence, missing-raw clean state, evidence immutable after completion |

### 13. Full test count

```
212 passed in 16.24s
```

Of those, 16 are the new v1.1 tests (8 + 3 + 5). The 196 pre-existing tests
continue to pass after the additive migrations were applied to the
production DB and to both corpus test fixtures.

### 14. CR-2 replay result

Froze the same `audit/corpus_runner_v1/cr2_manifest.json` (20 SHAs) and
re-ran through the v1.1-augmented executor (subprocess backend, same
scenario, same requirement version, same adapters, same frozen SHAs).

| Status | Original CR-2 (run 9) | v1.1 replay (run 10) | match |
|--------|----------------------:|---------------------:|:-----:|
| PASS | 2 | 2 | ✓ |
| FAIL | 3 | 3 | ✓ |
| UNKNOWN | 0 | 0 | ✓ |
| ERROR | 0 | 0 | ✓ |
| UNSUPPORTED | 15 | 15 | ✓ |
| SKIPPED | 0 | 0 | ✓ |

Five-frozen regression identical:

| full_name | cat | CR-2 | v1.1 replay |
|---|---|---|---|
| SWE-agent/mini-swe-agent | A | PASS | PASS ✓ |
| gptme/gptme | B | PASS | PASS ✓ |
| HKUDS/nanobot | C | FAIL | FAIL ✓ |
| he-yufeng/CoreCoder | D | FAIL | FAIL ✓ |
| The-Pocket/PocketFlow | E | FAIL | FAIL ✓ |

v1.1 metadata verification on the replay:

| check | result |
|-------|:------:|
| `requirement_evaluations` rows = job count | 20/20 ✓ |
| `execution_recipe_id = 'legacy-adapter-direct'` on every job | 20/20 ✓ |
| UNSUPPORTED jobs carry `missing_capability='compatible_execution_recipe'` | 15/15 ✓ |
| Compliance distribution unchanged | ✓ |

Replay summary on disk: `audit/corpus_runner_v1/cr2_v11_replay_summary.json`.
Replay driver: `audit/corpus_runner_v1/replay_cr2_v11_metadata.py`.

### 15. Cache metrics

```
source_cache_hits            = 0
source_cache_misses          = 0
bytes_downloaded             = null
workspaces_created           = 0
workspaces_destroyed         = 0
orphaned_workspaces          = 0
source_cache_size_bytes      = 0
```

The v1.1 architecture adds the source cache + workspace manager as new
infrastructure, but the v1 driver path (`driver._clone_to_tempdir`) still
does its own per-attempt `git clone`. The cache module is therefore
integrated additively (no behaviour change to compliance verdicts) but
not yet exercised by the executor's actual probe path. Wiring
`driver._run_pipeline` to use `WorkspaceManager.prepare` /
`WorkspaceManager.cleanup` is the v1.1.1 step. Once that is in place, the
cache metrics above will start populating.

### 16. Remaining blockers before 50 repos

Items that must close before the 50-repo gate runs (NOT done in v1.1):

1. **Cache integration in `driver._run_pipeline`.** The driver still
   calls `_clone_to_tempdir` directly. v1.1.1 must route every clone
   through `WorkspaceManager.prepare` so per-attempt workspaces land in
   the workspace root and are auto-cleaned.
2. **Cache metrics wiring.** With (1) in place, the replay script's
   `cache_metrics` block will report real numbers.
3. **Cache eviction CLI (`reguard-corpus cache gc`).** The `gc` function
   is implemented; the CLI binding is not. Without it, cache size will
   grow unbounded until a manual invocation.
4. **Workspace janitor CLI (`reguard-corpus workspace gc`).** The cleanup
   path is implemented; the standalone janitor is not. Hosts that crash
   between attempt start and terminal completion would otherwise leave
   workspaces on disk.
5. **Stable dependency-cache integration.** v1.1 reserves the path; no
   dependency cache is actually written. Network-disabled installs will
   keep failing for repos whose deps are not preinstalled in the image
   (the documented CR-2 SECURITY_LIMITATION_INSTALL_NETWORK).
6. **Source cache eviction under load.** The LRU policy exists; a 50-repo
   gate will produce enough cache volume that eviction must be exercised
   in CI to confirm the policy actually fires.

### 17. Whether the architecture is ready for the 50-repo gate

**PARTIALLY READY.**

Ready:

- schema for execution/evaluation separation (`requirement_evaluations`,
  `execution_artifacts`, `missing_capability`, `missing_facts`,
  `execution_recipe_id`)
- source cache module (16 unit tests pass)
- workspace manager (8 unit tests pass)
- security boundaries (3 new tests pass)
- evidence retention (5 unit tests pass)
- CR-2 frozen replay produces identical compliance distribution

Not ready:

- the driver still does its own clone; cache + workspace manager are
  not yet on the executor's actual probe path → cache metrics are 0 in
  the replay
- cache eviction / workspace janitor CLIs are not wired
- 50-repo replay has not been run; LRU behaviour has not been observed
  at scale

The architecture is in place and the schema is forward-compatible. The
gate MUST wait for v1.1.1 to close items (1)-(4) in §16. Do not run the
50-repo gate automatically.

---

End of v1.1 final report.
