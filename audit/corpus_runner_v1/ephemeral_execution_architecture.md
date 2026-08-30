# Corpus Runner v1.x — Ephemeral Execution + Evidence Inventory Architecture

Status: design + minimum-slice implementation for v1.1
Scope: architecture + first-slice implementation only. No Article 12(2). No
new adapters. No family detection. No 50-repo gate.

---

## 0. Core principle

> Repository checkouts are disposable execution inputs.
> Evidence and evaluation records are durable truth.
> Caches are optional performance infrastructure.

This document separates three orthogonal concerns that the current v1 codebase
entangles:

1. **Durable application state** — the audit trail. Authoritative.
2. **Performance cache** — disposable. Deleting it affects speed only.
3. **Ephemeral execution workspace** — must not survive a terminal attempt.

It also separates **execution** from **requirement evaluation**: today the
runner couples them, which prevents future requirements from reusing existing
execution evidence. The minimum slice is enough to make the separation
visible in code and schema; the cross-requirement reuse itself is *not*
implemented in v1.1.

---

## 1. Target lifecycle

```
repository DB row
  → resolve/freeze exact SHA
  → locate/fetch immutable source cache
  → materialize ephemeral checkout (per-attempt)
  → prepare isolated execution (per-attempt workspace)
  → run deterministic scenario(s)
  → collect normalized evidence
  → derive capability facts
  → evaluate requirement(s)
  → persist selected evidence/results + selected artifact hashes
  → destroy checkout / workspace
```

The working checkout, the per-attempt virtualenv, the container scratch
filesystem, and unneeded stdout/stderr are destroyed after a terminal job.
The audit trail is in the DB, not on disk.

---

## 2. Three storage classes

| Class | Examples | Retention | Owned by | Why |
|-------|----------|-----------|----------|-----|
| A. Durable application state | repository identity, frozen SHA, CorpusRun, EvaluationJob, EvaluationAttempt, ExecutionRecord, ObservedEvidence, CapabilityFact, RequirementEvaluation, ExecutionArtifact hash | Indefinite | DB | Audit trail. Survives cleanup. |
| B. Performance cache | bare git object cache, downloaded wheels, sdists, pip download cache | Bounded (LRU + size cap) | Filesystem | Pure perf. Deletable without loss of truth. |
| C. Ephemeral execution workspace | materialized checkout, venv, generated probe files, container scratch, transient logs | Single attempt | Filesystem, destroyed on terminal | Never authoritative. |

This separation is enforced by directory boundaries:

- `~/.local/share/reguard/source-cache/`  — class B
- `~/.local/share/reguard/dependency-cache/`  — class B
- `$XDG_RUNTIME_DIR/reguard/workspaces/<attempt-id>/`  — class C (best-effort;
  falls back to `/tmp/reguard/workspaces/`)

DB rows reference **hashes and logical names**, never raw bytes. Raw bytes
live under class B/C. Selected bytes get promoted to a class-A artifact
record by the orchestrator and stay as long as the parent record says.

---

## 3. Source cache design

Shape: one bare git repo per cached repository.

```
source-cache/
  <cache_key>/
    bare.git/                # `git clone --mirror <url> bare.git`
    cache_meta.json          # last_fetch_at, last_used_at, size_bytes, state, error
```

`cache_key` is `sha256(clone_url)[:32]` (stable, host-independent). One
cache entry per repository; the immutable object store holds every commit
the host has ever fetched, so subsequent SHAs are usually a fetch, not a
re-clone.

Working jobs never mutate the shared cache:

- The materialized checkout is created with `git --work-tree=<workspace>
  --git-dir=<cache>/bare.git checkout --detach <exact-sha>`, which produces
  a per-workspace working tree whose state is fully isolated.
- The cache's `bare.git` directory is opened read-only by the materializer
  (verified via a `git config core.bare` sanity check + the OS read-only
  bit when possible).
- Exact-SHA verification runs before the workspace is handed to the probe:
  the materializer aborts if the requested SHA is not reachable from the
  cache (forcing a fetch) or if the resulting `HEAD` differs from the
  requested SHA.

Concurrent readers are safe: a bare git repo supports many simultaneous
readers. The only writer is the cache manager during a fetch; writers are
serialised through a per-cache-key `flock` so two parallel jobs against the
same repo cannot race on `git fetch`.

Cache loss is recoverable: deleting the cache directory and re-running the
same SHA produces semantically equivalent execution (same final checkout
contents, same evidence, same compliance verdict). A cache hit and a cache
miss for the same SHA must produce identical evidence. The first-slice
implementation enforces this by ensuring the materializer reuses the
*exact* same `git checkout` arguments regardless of cache state.

### Git mechanism choice

Chosen: **bare mirror + per-workspace detached working tree**.

Considered:

| mechanism | verdict | reason |
|-----------|---------|--------|
| bare clone + worktree | yes | simplest; checkout path is already detached per worktree |
| mirror clone + archive | no | archive cost; loses future SHA advantage |
| full clone per job | rejected | O(n) disk per SHA; clobbers shared cache |

The bare+worktree shape is the smallest safe choice for a single-process
runner on local disk.

---

## 4. Source cache metadata

Persisted as a JSON sidecar `cache_meta.json` next to each `bare.git/`, AND
optionally mirrored into a new `source_cache_entries` DB table (deferred;
sidecar is enough for v1.1).

```
repository_id          optional, links to agent_repositories.id
cache_key              sha256(clone_url)[:32]
clone_url
cache_path             absolute path to bare.git
last_fetch_at          ISO 8601
last_used_at           ISO 8601
size_bytes
state                  ok | fetching | corrupt | error
error                  last error message
```

The cache is NOT part of evaluation identity. Cache hit and cache miss for
the same SHA produce identical verdicts. The cache metadata is for
operators only.

---

## 5. Dependency cache design

Not built in v1.1. The current architecture runs probes inside either a
fresh per-attempt `venv` (subprocess path) or the runtime image (container
path, with `pip install -e .` baked into the runtime entrypoint or skipped
via `--no-auto-setup`).

The slot for a dependency cache exists in the architecture even though the
v1.1 minimum slice does not fill it. When implemented, the cache will key
on:

```
runtime version
python version
platform
package manager
lockfile/content hash
build configuration
```

`site-packages` will NOT be shared between repositories. Each attempt will
still receive an isolated virtualenv.

---

## 6. Network / install architecture

Three explicit phases:

| Phase | Allowed | Goal |
|-------|---------|------|
| A. dependency acquisition | yes, controlled policy | obtain third-party artifacts |
| B. target project build/install | network disabled preferred | execute repo build hooks |
| C. compliance probe | network disabled (hard) | observe framework behaviour |

Documented limitation (pre-existing): the current `exec` container mode
runs `pip install -e .` with whatever network policy the host passes. CR-2
ran with `--network none`, which makes Phase A fail inside the container.
The architectural improvement would be a wheelhouse — fetch with network in
a separate Phase A worker, hand the wheels into a Phase B/C `exec` with
`--network none` and `pip install --no-index --find-links=...`. The v1.1
minimum slice does NOT implement this; it preserves the existing
limitation rather than introduce a fake allow-list. The rejection of "fake
PyPI allow-lists that still let build hooks run with unrestricted network"
is explicit in the spec.

---

## 7. Workspace design

One workspace per EvaluationAttempt:

```
<workspaces-root>/<attempt-id>/
  input/
    <cache-bare.git>        # symlink to source-cache/<key>/bare.git (read-only)
  repo/                     # materialized detached working tree at exact SHA
  probe/                    # probe.py + scenario artifacts
  artifacts/                # captured trajectory, framework artifacts
  logs/                     # stdout/stderr (truncated on retention)
  tmp/                      # scratch, may contain venv
  cleanup_marker            # present only AFTER successful destroy
```

Requirements:

- unique per attempt (uses the `evaluation_attempts.id` as the suffix)
- not shared between jobs
- destroyed on terminal completion (PASS / FAIL / UNKNOWN / UNSUPPORTED)
- optionally retained on ERROR for `retain_error_workspace_minutes`
  (default 0 — destroy immediately; spec says "configurable short
  debugging retention" but does not require a non-zero default)
- cleanup is idempotent (re-running on an already-destroyed workspace is
  a no-op)
- cleanup failure does NOT mutate the compliance verdict: a corrupt
  cleanup logs a warning and the audit trail still reflects the verdict.

No durable compliance state depends on the workspace continuing to exist.

---

## 8. Artifact retention policy

Classify every artifact the orchestrator touches:

### Always persist metadata (DB)

```
artifact_logical_name     e.g. "evidence_bundle", "trajectory", "stderr_tail"
producer                  "orchestrator" | "adapter:<name>" | "framework:<name>"
origin                    "execution" | "framework" | "user_input"
size_bytes
sha256
mime_or_ext
created_during_execution   true
framework_created          true|false
truncated                  false
```

### Persist selected bytes

Only when:

- required for evidence reproducibility,
- debugging an ERROR,
- required by the requirement test as audit evidence (e.g. framework
  log file for Article 12(1) PASS verification),
- explicit operator request.

Bytes are persisted under class B with a hash and DB index. If the byte
file is later evicted (cache policy), the DB record remains and flags
`bytes_available = false`.

### Discard

- virtualenv contents,
- package caches,
- repository build outputs unrelated to evidence,
- duplicate artifacts,
- oversized binaries beyond `max_artifact_bytes_per_attempt`.

Limits (configurable; v1.1 defaults):

```
max_artifact_bytes_per_attempt = 64 MiB
max_stdout_bytes               = 1 MiB
max_stderr_bytes               = 1 MiB
max_artifact_bytes             = 16 MiB
```

Truncation is recorded as `truncated=true` plus a `truncation_reason` field.

---

## 9. Execution as a first-class entity

Conceptual split:

```
RepositorySnapshot
        ↓
ExecutionPlan         (recipe_id, recipe_version, scenario_id, scenario_version)
        ↓
ExecutionAttempt      (one materialized checkout, one isolated run)
        ↓
ObservedEvidence       (normalized, requirement-neutral envelope)
        ↓
CapabilityFacts        (deterministic derivations)
        ↓
RequirementEvaluation  (requirement_id + requirement_version + evaluation_time)
```

In v1.1, an ExecutionAttempt is still keyed by
`(repository_id, repo_sha, scenario_id, scenario_version, adapter_name,
adapter_version, runtime_version)` — the same dedup key as `compliance_runtime_runs`,
because Article 12(1) v1.4.0 is the only requirement. The
`ExecutionRecipe` concept is **designed but not instantiated** — the
adapters still own recipe knowledge. The minimum slice adds an
`execution_recipe_id` column to `evaluation_jobs` and `compliance_runtime_runs`
that defaults to `"legacy-adapter-direct"` so the schema is forward-
compatible without touching adapters.

Future requirement reuse is **not** implemented. The design makes it
possible; the v1.1 code does not consume executions from a different
requirement.

---

## 10. Execution identity

v1.1 execution identity is:

```
repository_id
repo_sha
scenario_id
scenario_version
adapter_name        (or ADAPTER_MISSING_SENTINEL)
adapter_version
runtime_version
execution_recipe_id (new; default "legacy-adapter-direct")
```

This is the dedup key. Requirement identity is OUT of execution identity,
matching the spec. A `RequirementEvaluation` row links one execution to
one requirement.

Critique against current `compliance_runtime_runs`:

- `compliance_runtime_runs` already uses the inputs we need for execution
  identity (minus `execution_recipe_id`, which we add).
- `evaluation_jobs` keeps `requirement_id` + `requirement_version`. That
  is the requirement-evaluation side of the join.
- We add an explicit `requirement_evaluations` table for the future
  cross-requirement reuse; v1.1 inserts one row per job into it for
  forward-compatibility but the requirement evaluation logic still reads
  `evaluation_jobs.compliance_status` for v1.4.0.

What stays: `compliance_runtime_runs` (durable evidence + verdict).
What is added: `requirement_evaluations`, `execution_artifacts` metadata,
`execution_recipe_id` column, `source_cache_entries` (optional sidecar
mirrored into DB).
What is removed: nothing.

---

## 11. Normalized observed evidence

v1.1 keeps the existing `Evidence` envelope. Future requirements may need
richer fields; v1.1 does not add them, but lists the candidate envelope:

```json
{
  "events": [...],
  "framework_artifacts": [...],
  "framework_state": {...},
  "tool_activity": [...],
  "model_activity": [...],
  "errors": [...],
  "persistence_observations": [...],
  "timing_order": [...],
  "human_interaction": [...],
  "network_observations": [...],
  "process_outcome": {...},
  "filesystem_observations": [...]
}
```

No field is mandatory. Article 12(1) Evidence stays compatible.

---

## 12. Capability-fact inventory

A future `capability_facts` table (designed, not created in v1.1):

```
fact_key
value
observation_state    TRUE | FALSE | UNKNOWN | NOT_OBSERVED | NOT_APPLICABLE
source_evidence_refs json list of execution_artifacts.artifact_logical_name
producer             "orchestrator" | "adapter:<name>" | "framework:<name>"
```

Example facts:

```
recording.framework_persistent = TRUE       (Article 12(1) requires)
recording.session_state_recoverable = TRUE
recording.native_event_stream = FALSE
execution.tool_use_observed = TRUE
execution.tool_failure_observed = FALSE
evidence.input_recorded = TRUE
evidence.output_recorded = TRUE
evidence.tool_result_recorded = FALSE
```

No subjective confidence scores. v1.1 does NOT instantiate this table; it
is an architectural placeholder.

---

## 13. Missing-fact model

Distinct surfaces; do not collapse:

| Outcome | Where it lives | Field |
|---------|----------------|-------|
| UNSUPPORTED (no adapter) | `evaluation_jobs.compliance_status` | `error_class = "ADAPTER_ERROR"`, `error_message = "adapter not registered"`, future: `missing_capability = "compatible_execution_recipe"` |
| SKIPPED (scenario not supported by adapter) | `evaluation_jobs.job_status = "skipped_unsupported_scenario"` | `error_class = "SKIPPED_UNSUPPORTED_SCENARIO"` |
| UNKNOWN (probe ran but missing evidence) | `compliance_runtime_runs.result` / future `capability_facts` | future: `missing_facts = ["recording.framework_persistence"]` |
| ERROR (infrastructure failure) | `evaluation_attempts.error_class` | one of `SHA_RESOLUTION_ERROR`, `CLONE_ERROR`, `CHECKOUT_ERROR`, `CONTAINER_START_ERROR`, `INSTALL_ERROR`, `PROBE_ERROR`, `ADAPTER_ERROR`, `EVIDENCE_SCHEMA_ERROR`, `TIMEOUT`, `INTERNAL_SCHEDULER_ERROR` |
| PASS / FAIL | `evaluation_jobs.compliance_status` | `missing_facts` = null |

In v1.1 the existing columns carry this; v1.1 makes one small
**schema-additive** refinement:

- `evaluation_jobs.missing_capability` (TEXT NULL) — set to a stable token
  for short-circuit outcomes (e.g. `"compatible_execution_recipe"` for
  ADAPTER_ERROR, `"tool_failure_scenario"` for SKIPPED_UNSUPPORTED_SCENARIO).
- `evaluation_jobs.missing_facts` (TEXT JSON NULL) — for future UNKNOWN
  outcomes; always NULL in v1.1.

These columns are additive and do not change Article 12(1) v1.4.0
semantics.

---

## 14. Requirement evaluation model

Conceptually:

```
requirement
  → required facts
  → available facts (from existing ExecutionAttempt evidence)
  → PASS | FAIL | UNKNOWN
```

In v1.1 the only requirement is Article 12(1) v1.4.0 and its evaluation
is unchanged. The architecture reserves room for future requirements to
consume existing execution evidence without rerunning; v1.1 does not
implement that consumption.

---

## 15. Execution recipe concept

Designed, not implemented. Future responsibilities:

```
install strategy          (editable pip, system deps, no-install)
entrypoint                (which script to invoke)
fake/stub model setup
env
scenario invocation
artifact roots
observer configuration
```

Adapters still own recipe knowledge in v1.1. The
`execution_recipe_id = "legacy-adapter-direct"` literal is the placeholder.

---

## 16. Observer concept

Designed, not implemented. Candidate observers:

- filesystem delta observer
- JSON/JSONL observer
- SQLite observer
- event-bus observer
- message-history observer
- stdout/stderr observer
- framework-native session observer

Observers produce normalized observations. Observers do NOT decide
compliance. v1.1 keeps the existing adapter model.

---

## 17. Adapter evolution

Path forward (incremental, not in v1.1):

```
RepoAdapter (current)
  ≈ invocation knowledge + observation + normalization + classification

Future:
RepositoryIntegration
  ├─ ExecutionRecipe         (install, entrypoint, env, observer config)
  ├─ ObserverSet             (filesystem / jsonl / sqlite / bus / stdout)
  └─ Normalizer              (adapter-specific event/artifact mapping)
```

Existing adapters continue working unchanged. v1.1 only adds the
`execution_recipe_id` column.

---

## 18. Durable schema diagnosis

Review of existing tables:

| Table | Status in v1.1 | Why |
|-------|----------------|-----|
| `agent_repositories` | unchanged | identity already correct |
| `compliance_runtime_runs` | extended | add `execution_recipe_id`, `execution_recipe_version` columns |
| `corpus_runs` | unchanged | orchestration metadata |
| `corpus_run_repositories` | unchanged | frozen SHA manifest already correct |
| `evaluation_jobs` | extended | add `missing_capability`, `missing_facts`, `execution_recipe_id` |
| `evaluation_attempts` | unchanged | attempt record is sufficient |

New tables (designed, NOT all created in v1.1):

| Table | v1.1 status | Purpose | Key | Cardinality | Retention | Relationship |
|-------|-------------|---------|-----|-------------|-----------|--------------|
| `requirement_evaluations` | **created** | Link execution to requirement evaluation; supports future cross-requirement reuse | `(evaluation_job_id, requirement_id, requirement_version)` | 1 per (job, requirement) | Indefinite | child of `evaluation_jobs`; for v1.1 the row is redundant with `evaluation_jobs.compliance_status` but the table is forward-compatible |
| `execution_artifacts` | **created** | Metadata for selected persisted bytes; supports retention / truncation policy | `(evaluation_job_id, artifact_logical_name)` | 0..N per job | Until parent job expires (currently indefinite) | child of `evaluation_jobs` |
| `source_cache_entries` | **deferred** | Mirror of `cache_meta.json` for operator queries | `(cache_key)` | 1 per cached repo | Until evicted | independent |
| `observed_evidence` | **deferred** | Requirement-neutral evidence envelope | `(evaluation_job_id)` | 1 per job | Indefinite | child of `evaluation_jobs`; in v1.1 the same data lives in `compliance_runtime_runs.evidence_json` |
| `capability_facts` | **deferred** | Deterministic facts for future requirement evaluation | `(evaluation_job_id, fact_key)` | 0..N per job | Indefinite | child of `evaluation_jobs` |

Additive evolution. No table is dropped. The frozen Article 12(1)
contract is not modified.

---

## 19. Database questions we must be able to answer

| Question | Answered by |
|----------|-------------|
| Which repos are UNKNOWN for Article 12(1), and what facts were missing? | `evaluation_jobs` where `compliance_status = 'UNKNOWN'` + `missing_facts` (future field) |
| Which repos are UNSUPPORTED because no execution recipe exists? | `evaluation_jobs` where `compliance_status = 'UNSUPPORTED'` + `missing_capability = 'compatible_execution_recipe'` |
| Which repos failed installation? | `evaluation_attempts.error_class = 'INSTALL_ERROR'` joined to `evaluation_jobs` |
| Which repos have persistent framework logging? | current `evidence_json.framework_persistence` field in `compliance_runtime_runs` (Article 12(1) semantics) |
| Which repos expose tool activity? | current `evidence_json.tool_calls` field in `compliance_runtime_runs` |
| Which requirements can be evaluated using an existing execution? | `requirement_evaluations` table — when more than one row per `evaluation_job_id` exists, that execution was reusable |
| Which cache entries consume the most disk? | `source_cache_entries.size_bytes` (deferred) or filesystem `du` |
| Which repositories need rerun because scenario/runtime version changed? | `compliance_runtime_runs` dedup key includes scenario_id, scenario_version, runtime_version; new versions produce new rows |

---

## 20. Cache invalidation

Source cache:
- `repo SHA changes` → old objects may remain; new snapshot uses new SHA.
- `clone_url changes` → different cache_key; old cache stays until evicted.

Dependency cache (designed): invalidates on any of
`runtime_version, python_version, platform, package_manager, dependency_lock_hash,
build_config_hash`.

Observed evidence:
- never mutates historical execution evidence.
- new runtime / scenario / recipe version → new `ExecutionAttempt`, new row.

---

## 21. Cache eviction

Bounded policy (v1.1 minimum slice implements source-cache LRU only):

```
max_source_cache_bytes       = 8 GiB       (default)
max_source_cache_age_days    = 30         (default)
max_dependency_cache_bytes   = 8 GiB       (future)
max_dependency_cache_age_days= 30         (future)
```

LRU keyed on `last_used_at`. Eviction is performed by an offline command:

```
reguard-corpus cache gc
```

Eviction is safe when no active job references the entry; the runner
increments a refcount on each open workspace, and the GC skips entries
with `refcount > 0`.

Cache eviction MUST NEVER delete durable evidence / result records.

---

## 22. Cleanup policy

After a terminal job:

| Job outcome | Default action | Configurable? |
|-------------|----------------|---------------|
| PASS / FAIL / UNKNOWN / UNSUPPORTED | destroy workspace immediately | no (always) |
| ERROR | destroy immediately (`retain_error_workspace_minutes = 0`) | yes |

A janitor command sweeps abandoned workspaces:

```
reguard-corpus workspace gc --stale-after-minutes 60
```

The janitor does NOT touch durable state.

---

## 23. Failure-recovery invariant

If Reguard crashes halfway through a job:

| Resource | Survives? | Recovery semantics |
|----------|-----------|--------------------|
| CorpusRun | yes | resume via `run_corpus_run(id)` |
| EvaluationJob | yes | row state machine is recoverable |
| EvaluationAttempt | yes | started_at set; completed_at NULL → mark interrupted |
| Frozen SHA | yes | persisted at run creation |
| Source cache | yes | durable class B |
| Partial workspace | detectable | janitor cleans; verifier refuses partial bytes |
| Resume must not confuse partial outputs with valid evidence | yes | orchestrator re-runs attempt; partial artifacts never promoted to durable state |

Stale-attempt recovery: an attempt row with `started_at != NULL AND
completed_at IS NULL` after a host restart is marked
`error_class = "INTERNAL_SCHEDULER_ERROR", error_message = "interrupted
by host crash"`. The retry classifier does NOT retry this class — the
caller decides whether to resume. Partial artifacts are NEVER evaluated
as if they were complete.

---

## 24. First implementation slice

Implemented in v1.1 (this PR):

1. ✅ Source cache: bare-git, keyed by `sha256(clone_url)[:32]`.
2. ✅ Materialized checkout per attempt; rejected paths.
3. ✅ Automatic cleanup on terminal completion.
4. ✅ Cache metadata sidecar.
5. ✅ Schema-additive missing/error reason fields (`missing_capability`,
   `missing_facts`, `execution_recipe_id`).
6. ✅ Schema-additive execution/evaluation separation
   (`requirement_evaluations`, `execution_artifacts` metadata tables).
7. ✅ Tests for §25-§27.
8. ✅ Replay of frozen CR-2 manifest with identical compliance behaviour.

NOT implemented in v1.1:

- ❌ Framework-family detection.
- ❌ Full observer rewrite.
- ❌ Multi-requirement execution reuse.
- ❌ Sophisticated dependency build cache.
- ❌ External workers (Redis / Celery / K8s).
- ❌ Article 12(2).

---

## 25. Source-cache tests

Implemented in `tests/cache/test_source_cache.py`:

| Test | Asserts |
|------|---------|
| `test_cache_miss_fetches_and_materializes` | absent cache → fetch → exact SHA materialized |
| `test_cache_hit_avoids_reclone` | same repo/SHA → `git fetch` not invoked → same checkout contents |
| `test_different_sha_fetches_missing_objects` | same repository, new SHA → fetch missing → different snapshot |
| `test_workspace_isolation` | workspace A mod ≠ workspace B ≠ source cache |
| `test_terminal_attempt_destroys_workspace` | attempt completes → workspace deleted; cache retained |
| `test_cache_loss_refetches` | delete cache → same job → same SHA materializes again |

## 26. Security tests

Implemented in `tests/security/test_ephemeral_execution.py`:

| Test | Asserts |
|------|---------|
| `test_cache_objects_not_writable_from_workspace` | workspace cannot write back to `bare.git` |
| `test_no_host_credentials_in_workspace` | env at probe time contains only allow-listed keys |
| `test_no_container_socket_exposed` | container invocation does not bind-mount /var/run/docker.sock |
| `test_probe_network_none` | container exec carries `--network none` |
| `test_input_readonly` | bind mount is `readonly` |
| `test_artifacts_writable` | artifacts bind mount is writable |
| `test_workspace_path_escape_blocked` | workspace path traversal blocked |
| `test_malicious_symlink_cannot_escape_artifacts` | symlinks in repo do not let artifact collection cross workspace boundary |

## 27. Evidence retention tests

Implemented in `tests/evidence/test_retention.py`:

| Test | Asserts |
|------|---------|
| `test_selected_artifact_hash_recorded` | `execution_artifacts.sha256` matches persisted bytes |
| `test_oversized_stdout_truncated_with_marker` | truncation marker + bytes match limit |
| `test_discarded_workspace_does_not_break_evidence_retrieval` | workspace gone; evidence JSON readable from DB |
| `test_missing_raw_artifact_storage_state` | `bytes_available = false` is a clean state, not corruption |
| `test_evidence_immutable_after_completion` | re-running an attempt does not mutate previous evidence row |

---

## 28. 20-repo replay gate

After implementation, run the SAME frozen CR-2 manifest. Selection, SHAs,
requirement_version, scenario, adapter_versions, and frozen categories
must remain identical. Cache behavior may differ; compliance behaviour
must not.

Expected distribution:

```
PASS        2
FAIL        3
UNKNOWN     0
ERROR       0
UNSUPPORTED 15
SKIPPED     0
```

## 29. Cache metrics for replay

```
source_cache_hits
source_cache_misses
bytes_downloaded      (if measurable)
workspaces_created
workspaces_destroyed
orphaned_workspaces
source_cache_size
```

## 30. Next scale decision

After the replay, decide whether the system is ready for the 50-repo
infrastructure gate. Do NOT run 50 automatically. The decision criteria
are listed in §30 of the task spec; the v1.1 report writes item 17 as
READY, PARTIALLY READY, or NOT READY.

---

End of architecture document.
