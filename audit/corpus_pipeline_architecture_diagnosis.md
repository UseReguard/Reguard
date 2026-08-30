# Reguard corpus-scale pipeline — architecture diagnosis

Date: 2026-08-29
Scope: inventory of the current Article 12(1) v1.4.0 pipeline
surface and a diagnosis of what is missing for corpus-scale
execution. **No implementation** is proposed or carried out
in this document. The frozen Article 12(1) v1.4.0 contract is
**not** modified.

---

## 1. Current end-to-end execution architecture

This is the actual call chain followed today for one normal
Article 12(1) invocation (clone mode or path mode). Each
step cites a concrete file and the function / line where the
work is performed.

```text
CLI (human / GHA)
   scripts/compliance-check.py::main       --repo owner/name --sha SHA
        │
        ▼
   _unsupported_record / _synth_record
   (KeyError -> UNSUPPORTED exit=3; RuntimeError -> ERROR exit=4)
        │
   driver.py::run_one                       (clone mode)
        │
        ├── db lookup                      _lookup_repo(db, full_name)
        ├── adapter registry lookup        compliance.adapters.registry.get_adapter(full_name)
        ├── idempotency pre-check          persistence.load_run_by_dedup_key(...)
        │      └── if hit -> return existing RunRecord
        ├── _clone_to_tempdir              git clone --no-checkout; git checkout SHA; rm -rf .git
        │
        ▼
   driver.py::_run_pipeline
        ├── orchestrator.run_probe         subprocess OR container_runner.run_in_container
        │      ├── fresh venv per run       orchestrator: venv.EnvBuilder
        │      ├── pip install -e .        orchestrator: subprocess.run(...)
        │      ├── write probe.py          orchestrator: _PROBE_BY_ADAPTER[adapter.name]
        │      ├── exec probe              orchestrator: subprocess.run([py, probe.py, task])
        │      └── container path:
        │             ├── podman or docker discovered
        │             ├── --cap-drop ALL / --security-opt no-new-privileges
        │             ├── --pids-limit 256 --memory 4g --cpus 2
        │             ├── --user 10001:10001 (non-root)
        │             ├── /input RO bind, /artifacts RW bind
        │             ├── 2-phase network policy: TODO (single-phase today)
        │             └── exec() subcommand -> /opt/repo-runtime/runtime/entrypoint.py
        │
        ▼
   orchestrator.collect_evidence
        ├── returncode != 0  -> probe_status = "probe_failed"     (ERROR)
        ├── no trajectory    -> probe_status = "no_trajectory"    (ERROR)
        ├── parse raises     -> probe_status = "adapter_raised"    (ERROR)
        └── else             -> probe_status = "ok" + adapter.parse_trajectory(...)
        │
        ▼
   adapter.parse_trajectory                 framework-native -> Evidence
        └── stamps:
              recording_category, framework_persists_durably,
              framework_artifact_paths, harness_artifact_paths,
              observation_quality, origin (per event), producer, collector
        │
        ▼
   RequirementTest.evaluate                  base.py::evaluate
        ├── schema mismatch             -> ERROR
        ├── probe_status != "ok"        -> ERROR
        ├── empty events & not observed_absence -> UNKNOWN
        └── else assert_evidence        -> PASS / FAIL reduction
        │
        ▼
   Result + Evidence + RunRecord
        ├── persistence.insert_run       compliance_runtime_runs (UNIQUE dedup key)
        │     └── IntegrityError handled by load_run_by_dedup_key (idempotent return)
        │
        ▼
   compliance-check.py
        ├── writes compliance-result.json if --output
        ├── one-line JSON to stdout
        └── returns EXIT_CODE[status]    0/1/2/3/4
```

### Concrete file / line references

| Layer | File | Function / line |
|---|---|---|
| CLI entrypoint | `scripts/compliance-check.py` | `main()` line 193 |
| Exit-code map | `scripts/compliance-check.py` | `EXIT_CODE` line 50 |
| Synth UNSUPPORTED | `scripts/compliance-check.py` | `_unsupported_record` line 103 |
| Driver | `src/compliance/pipeline/driver.py` | `run_one` line 271, `_run_pipeline` line 161 |
| Clone-to-tempdir | `src/compliance/pipeline/driver.py` | `_clone_to_tempdir` line 98 |
| SHA verifier | `src/compliance/pipeline/driver.py` | `_verify_checkout_sha` line 118 |
| Adapter registry | `src/compliance/adapters/registry.py` | `ADAPTER_REGISTRY` line 16 |
| Orchestrator | `src/compliance/pipeline/orchestrator.py` | `run_probe` line 526 |
| Container runner | `src/compliance/pipeline/container_runner.py` | `run_in_container` line 160 |
| Probe registry | `src/compliance/pipeline/orchestrator.py` | `_PROBE_BY_ADAPTER` line 511 |
| Evidence collection | `src/compliance/pipeline/orchestrator.py` | `collect_evidence` line 741 |
| Adapter base | `src/compliance/adapters/base.py` | `RepoAdapter` line 34 |
| Capability metadata | `src/compliance/adapters/base.py` | `AdapterCapabilities` line 19 |
| Requirement engine | `src/compliance/requirements/base.py` | `RequirementTest.evaluate` line 48 |
| Article 12(1) | `src/compliance/requirements/ai_act/article_12_1.py` | `Article121AutomaticLoggingTest` line 111 |
| RunRecord | `src/compliance/pipeline/types.py` | `RunRecord` line 146 |
| Persistence | `src/compliance/pipeline/persistence.py` | `insert_run` line 27 |
| Dedup key | `migrations/005_compliance_runtime_runs.sql` | `idx_crr_dedup` line 39 |
| CLI exit codes | `scripts/compliance-check.py` | `EXIT_CODE` line 50 |
| Status enum | `src/compliance/pipeline/types.py` | `RunStatus` line 54 |

---

## 2. What is repository-specific today

Adapter / probe responsibilities for the five integrated
repos. Five columns × fifteen rows.

| Responsibility | mini-swe-agent (A) | CoreCoder (D) | nanobot (C) | PocketFlow (E) | gptme (B) |
|---|---|---|---|---|---|
| Install command | adapter `capabilities.install_command = "pip install -e ."` | identical | identical | identical | empty (`""` → orchestrator falls back to `pip install -e .`) |
| Build-strategy detection | runtime/detect.py → PEP 621 pyproject → `pip` editable | identical | PEP 621 / pyproject + may pull extra deps | PEP 621 / pyproject | Poetry 2.1.3 (gptme ships `poetry.lock` + `[tool.poetry]`) |
| Invocation logic | probe: `DefaultAgent.run` with `DeterministicModel` | probe: `Agent(llm=FakeLLM()).chat` | probe: `RuntimeEventPublisher.publish(...)` events | probe: Flow + Node stub; workspace snapshot | probe: `LogManager.append(Message(...))` |
| Scenario construction | `render_synthetic_task` returns `scenario.user_prompt` | identical | identical | identical | identical |
| Fake / stub model | `DeterministicModel` registered in mini-swe-agent's `test_models.py` | `FakeLLM.chat` defined in probe | no model — runs pure bus events; deterministic | no model — pure in-memory graph | no model — LogManager just appends |
| Env vars | `COMPLIANCE_TRAJECTORY_PATH=/artifacts/trajectory.json` | identical | identical | identical + `REPO_RUNTIME_WORKSPACE=/workspace/repo` | identical + framework reads `GPTME_LOGS_HOME` (probe sets it) |
| Filesystem observation | none — agent writes its own trajectory | probe writes `agent.messages` to trajectory JSON; framework does not persist | probe writes collector record to trajectory | probe snapshots workspace before/after and writes `framework_artifacts_observed` | probe copies `conversation.jsonl` to `/artifacts/framework_conversation.jsonl` |
| Event observation | `messages` list in trajectory → `step/tool/exit` | `messages` list → `step/tool` (no `exit`) | bus events `SessionTurnStarted/UserInputAccepted/TurnCompleted/SessionTurnPersisted/TurnRuntimeAdmitted/TurnRunStatusChanged` | none emitted by framework | LogManager turns → `step/tool/model` |
| Framework artifact discovery | `trajectory_path` | none (none exists) | none | cross-check workspace scan excludes `_HARNESS_WRITTEN_BASENAMES` and `venv/.venv/site-packages/.git/node_modules` | `_resolve_artifact_path` maps `/artifacts/...` to host mount |
| Persistence detection | `framework_persists_durably = path.exists() and bool(messages)` | always `False` (harness writes) | always `False` (subscriber writes) | always `False` (no recorder) | `framework_persists = (resolved_log.exists() & size>0) or log_size_bytes>0` |
| Event normalization | `_ROLE_KIND_MAP` (user/assistant→step; tool→tool; exit→exit) | `_ROLE_KIND_MAP` (user/assistant→step; tool→tool; no exit) | `_NANOBOT_KIND_MAP` (SessionTurnStarted/UserInputAccepted/TurnRunStatusChanged→step; TurnRuntimeAdmitted→model; TurnCompleted→completed) | n/a (no events) | `_KIND_BY_ROLE` (user/system→step; assistant→model; tool→tool) |
| Provenance assignment | `SYSTEM_NATIVE` | `SYSTEM_STATE_EXPORTED_BY_HARNESS` | `SYSTEM_NATIVE` | n/a | `SYSTEM_STATE_EXPORTED_BY_HARNESS` |
| A–E classification | hard-coded `"recording_category": "A"` in `extra` | hard-coded `"D"` | hard-coded `"C"` | hard-coded `"E"` | hard-coded `"B"` |
| Evidence construction | adapter writes 5 fields + `trajectory_format`, `model_stats`, `exit_status`, `scenario_id`, `origin`, `producer`, `collector` | adapter writes 5 fields + `model`, `final_response`, `scenario_id`, `origin`, `producer`, `collector` | adapter writes 5 fields + `result_status`, `scenario_id`, `origin`, `producer`, `collector` | adapter writes 5 fields + workspace scan results, `scenario_id`, `framework_version`, `observation_quality`, `origin`, `producer`, `collector` | adapter writes 5 fields + `log_file_path`, `host_log_file_path`, `session_id`, `log_size_bytes`, `scenario_id`, `origin`, `producer`, `collector` |
| Error handling | missing trajectory or parse error → empty events bundle, `framework_persists_durably=False`, category unchanged | identical | identical | identical | identical |

### Cost to add repo #6 (today)

Things that have to be written / modified for a sixth repo:

1. **New adapter class** (~150 LOC) with a hard-coded
   `recording_category`, `_ROLE_KIND_MAP` or equivalent,
   `parse_trajectory`, `capabilities`, `render_synthetic_task`,
   `resolve_agent`.
2. **New probe source string** registered in
   `orchestrator._PROBE_BY_ADAPTER` (~80–150 LOC) — the
   probe imports the framework, drives a deterministic
   scenario, writes the trajectory.
3. **Entry in `ADAPTER_REGISTRY`** mapping
   `full_name -> RepoAdapter`.
4. **Pinned SHA** chosen (corpus already stores metadata,
   but no SHA column; needs `git ls-remote` per repo).
5. **Build-strategy detection** will likely work
   automatically because `runtime/detect.py` handles pip /
   poetry / setuptools / uv, but unsupported strategies
   (pipenv / none) currently fail at install — see §6.
6. **CI**: hard-coded list in `.github/workflows/compliance.yml`
   or input box in
   `.github/workflows/compliance-article-12-1.yml`. No
   auto-discovery exists.

**Estimate: ~250 lines of new Python + at least one new
human-authored entry in `_PROBE_BY_ADAPTER` and one in
`ADAPTER_REGISTRY`.** That is per repo, not amortised.

### Cost to add repo #500 (today, unchanged architecture)

Stacking the per-repo cost: roughly **500 × 250 = ~125,000
lines of new Python** plus 500 entries in each of two
hard-coded dicts. Plus 500 Pinned-SHA / source-inspection
bottlenecks. **The current architecture trends toward
`O(repos)` integration work with a high constant**, plus
the engineering bottleneck of source inspection per repo.

---

## 3. Adapter registration / discovery

How a repo becomes supported today (and only today):

- Adapter selection is keyed by **exact `owner/name` string**
  in `ADAPTER_REGISTRY` (`src/compliance/adapters/registry.py:16`).
- There is **no family detection**, **no capability detection**,
  **no package-name detection**. Five hard-coded mappings:
  `SWE-agent/mini-swe-agent`,
  `he-yufeng/CoreCoder`,
  `HKUDS/nanobot`,
  `The-Pocket/PocketFlow`,
  `gptme/gptme`.
- **Multiple repos cannot share one adapter.** The registry
  maps one `full_name` to one adapter instance; there is no
  pattern-based dispatch.
- One repo cannot have multiple recipes.
- Adapter version is hard-coded in `class Meta.version`
  (e.g. `MiniSweAgentAdapter.version = "1.1.0"`). Persisted
  into `compliance_runtime_runs.adapter_version`. Not bumped
  automatically.
- When no adapter exists for `full_name`, the registry raises
  `KeyError`; the CLI converts it to a synthetic
  `RunRecord(status=UNSUPPORTED)` and returns `EXIT_CODE[UNSUPPORTED]=3`.

**Classification**: **repo-specific** registry (not
framework-specific, not family-specific, not capability-based).

---

## 4. Probe architecture

- **Storage**: probes are inline Python source strings inside
  `orchestrator.py` (`_PROBE_BY_ADAPTER` line 511). They are
  **not** separate files.
- **Selection**: by `adapter.name` only. The probe has no
  awareness of requirement_id, scenario_id, or
  requirement_version.
- **Parameterisation**: probes accept `sys.argv[1]` (the
  scenario's `user_prompt`), but most probes ignore it (only
  `nanobot`/`gptme` persist `scenario_id` into their
  trajectory). The probe is otherwise a fixed single-purpose
  script.
- **One probe per adapter**, not one per (repo × requirement).
  This is good news for requirement scaling — adding a new
  requirement does **not** force new probes.
- **One probe per adapter** is also bad news for corpus
  scaling — every new repo with a new framework demands a
  new probe.

### Combinatorics

Today:

- probes = O(repos)
- requirements = O(1) probe change per requirement (probes do
  not know about requirement_id)

So the current probe architecture is **O(repos)**, not
`O(repos × requirements)`. Adding requirements is free in
the probe layer; adding repos is not.

If corpus-scale work later demands per-(repo × scenario)
probes (e.g. to drive multi-step tool scenarios), the
dimension would multiply. Today, scenario parametrisation
lives entirely in `scenario.user_prompt`, which the probes
ignore.

---

## 5. Repository preparation

### Clone mechanism

`driver._clone_to_tempdir` does:

```bash
git clone --no-checkout https://github.com/owner/name.git tmp/
git -C tmp checkout SHA
rm -rf tmp/.git
```

### Behaviour

| Behaviour | Current state |
|---|---|
| Cache | none — every run clones fresh |
| Exact-SHA checkout | yes; `_verify_checkout_sha` in `driver.py:118` refuses mismatched heads |
| Repo identity | resolved via DB lookup `_lookup_repo(db, full_name)` (clone mode); path mode skips DB |
| Temp workspace layout | `tempfile.mkdtemp(prefix="cp_probe_...")` per clone; per-run `work_root = work_root_parent / "probe"` |
| Cleanup | `shutil.rmtree(repo_checkout, ignore_errors=True)` and `shutil.rmtree(work_root, ignore_errors=True)` in `finally` blocks; failure of either does not crash the pipeline |
| Retry behaviour | none — single shot; on failure the driver returns the synthesised `Evidence(probe_status="probe_failed")` or raises |
| Shallow / full clone | `git clone --no-checkout` (no `--depth`); effectively full-history |
| Submodules | not initialised (`--no-checkout` then explicit `git checkout SHA`); submodules will be empty |
| Git LFS | not pulled; LFS-pointer files will be checked in raw form |
| Private repos | unsupported — auth material would have to be added (currently none) |
| Repo size limits | none enforced; only `git clone` timeout (`timeout=120`) |
| Checkout timeout | `git checkout` = 60s |
| Clone timeout | `git clone` = 120s |

### Where the corpus lives

The current corpus is stored in:

| Table | Rows (this DB) | Notes |
|---|---:|---|
| `agent_repositories` | 1502 | GitHub metadata only; no SHA column |
| `agent_repository_audits` | 26 | per-repo audit notes |
| `article_runtime_assessments` | 878 | static (non-runtime) AI-Act article classifications |
| `compliance_runtime_runs` | 7 | existing runtime runs (most under v1.2 / v1.3 / v1.4) |

The corpus is currently filtered as:

```text
agent_repositories
  WHERE primary_language = 'Python'         -- all 1502 are Python today
    AND relevance_status = 'accepted'      -- 984 of 1502
    AND enabled = 1                        -- same 984
    AND archived = 0                       -- all 1502 satisfy
    AND fork = 0                           -- all 1502 satisfy
```

So the **canonical corpus already-in-DB is 984 Python
repos**. **`agent_repositories` has no `head_sha` column.**
Per-run SHAs must be resolved via `git ls-remote
origin HEAD` (or equivalent) at run time, then pinned.

**The corpus table already exists and is the most natural
source of jobs for a future corpus-runner.** No new table
is required for sourcing; the missing primitives are
runner-side, not source-side.

---

## 6. Build / package detection

Mature. Detection precedence in `runtime/detect.py`:

1. `uv.lock` → uv (`uv pip install`, `uv sync --frozen`)
2. `poetry.lock` → poetry (`poetry install --no-interaction --only main`,
   virtualenv disabled)
3. `pyproject.toml` → PEP 621 → pip editable, or
   `[tool.poetry]` → poetry-core
4. `Pipfile` → pipenv (**unsupported**, command empty)
5. `requirements*.txt` → pip
6. `setup.py` / `setup.cfg` → setuptools
7. none → unsupported

The `UNSUPPORTED_STRATEGIES = {"pipenv", "none"}` set returns
a `BuildStrategy(strategy=..., command=[])` whose runtime
status is `unsupported` (which surfaces as a synthetic
`status="unsupported"` from the runtime entrypoint's detect
step, NOT directly as `UNSUPPORTED` in the compliance
status). The orchestrator currently treats `status != "ok"`
from the container runtime as `probe_failed` → `ERROR`. The
unsupported build strategy path therefore yields `ERROR`
today, not the compliance-status `UNSUPPORTED`. **This is
a behavioural gap to resolve before corpus scale.**

Backends detected (via PEP 517 `build-system.build-backend`):
setuptools, hatchling, flit, pdm, scikit-build-core, maturin,
mesonpy, plus a generic fallback.

Python version constraints are detected from
`pyproject.requires-python` / `setup.cfg options.python_requires`
/ `setup.py python_requires` but the runtime currently hard-codes
`python 3.12-slim-bookworm` in the Dockerfile; the constraint
is *detected* but the runtime cannot honour out-of-range
constraints (e.g. `requires-python = ">=3.11,<3.13"` runs
fine; `>=3.13` will fail at install).

| Build shape | Current support | Detection | Failure state |
|---|---|---|---|
| pip / pyproject / requirements / setup.py | yes | high precedence | ERROR (non-zero pip install) |
| uv.lock | yes | first | ERROR |
| Poetry (lock or `[tool.poetry]`) | yes (Dockerfile installs Poetry 2.1.3) | pyproject parsing | ERROR |
| pipenv | reported as unsupported | detected | ERROR (orchestrator path) |
| none / no pyproject | reported as unsupported | detected | ERROR (orchestrator path) |
| Hatch / Hatchling / Flit / PDM / maturin / mesonpy | backend detectable; install via pip | backend lookup | ERROR |
| Native extensions / cgo / Rust | installable via pip; not validated at detect | implicit | ERROR (build failure) |
| System packages / `apt` deps | not supported | none | ERROR |

---

## 7. Container execution at scale

### Current lifecycle

- **Image**: `python-agent-runtime:dev` is built from
  `runtime/Dockerfile`. Today it is built once per
  container runner invocation, not per repo.
- **Container creation**: `container_runner.run_in_container`
  is called per repo. The `subprocess.run` then issues a
  single `podman run --rm` / `docker run --rm`. There is
  currently **no image reuse across runs**; the same
  `docker build` runs at job start in GHA.
- **Per repo / per scenario / per requirement**:
  - per-repo: yes (every `run_one` clone-mode call builds a
    fresh venv inside the container),
  - per-scenario: not today (the probe is fixed-shape),
  - per-requirement: not today (only one requirement
    registered today).
- **Dependency caching across runs**: none. Every probe
  re-installs via `pip install -e .` inside the container
  from scratch.
- **Repo checkout caching**: none. Container is
  one-shot (`--rm`); repo lives in `/input` bind-mount during
  the run only.
- **`/artifacts` persistence**: yes, host bind-mounted;
  collected by `container_runner`; copied to evidence dir
  for `compliance-check.py --output`.
- **Logs**: surface in `containers/00_setup|01_install|02_exec.{stdout,stderr}.log`;
  tail stitching in `container_runner._surface_logs`.
- **Timeouts**: enforced by the container runner
  (`--timeout-seconds`), plus host-side
  `subprocess.run(timeout=...)` as outer guard.
- **Orphan cleanup**: `--rm` on container run removes the
  container. No explicit "kill stale containers" job exists.
  Host-side `tempfile.mkdtemp` artefacts live in `/tmp` and
  are not cleaned up by the orchestrator today.

### Per-run repeated work

For each `(repo, requirement, scenario)` the orchestration
repeats:

1. container pull / build (GHA builds per job; local
   reuses the local image if the tag matches);
2. fresh venv creation inside the container;
3. `pip install -e .` from the on-disk checkout;
4. framework import + probe exec;
5. evidence write.

For the same SHA, `pip install -e .` is **the dominant
repeated work** — typically 10–60s per repo for the five
pinned ones; will be much larger for repos that depend on
torch / tensorflow / datasets / litellm.

### Cost-shape estimate

| Workload | Repeated-work quantity |
|---|---|
| 100 repos × 1 requirement × 1 scenario | 100 container boots + 100 fresh `pip install -e .` |
| 1000 repos × 10 requirements × N scenarios | (if probes share executions) ≈ 1000 pip installs × N. If executions do **not** share, this is ≈ 1000 × 10 × N installs. |

Without an install cache and a probe-vs-evidence separation,
the 1000-repo × 10-requirement workload grows linearly in
the number of `(requirement, scenario, repo)` triples.

---

## 8. Network isolation

### Repository / dependency preparation

- `runtime/Dockerfile` installs curl / ca-certificates,
  enabling `pip` to fetch packages during install.
- `runtime/container_runner` does **not** pass `--network`
  to the container today. The default OCI behaviour (bridge
  networking) is in effect.
- `audit/container_gate1/report.md` records two-phase
  network policy (install=enabled, probe=disabled) as a
  TODO; **not implemented today**.

### Probe execution

- Same: no `--network=none`. The container can reach the
  network during exec unless the host sets it.
- This is a hardening gap. It does not currently affect
  the determinism of the 5 integrated adapters because the
  probes are deliberately network-free.

### Other security knobs in `container_runner.run_in_container`

| Knob | Current state | Risk |
|---|---|---|
| `--cap-drop ALL` | yes | safe |
| `--security-opt no-new-privileges` | yes | safe |
| `--pids-limit 256` | yes | safe |
| `--memory 4g` | yes | safe |
| `--cpus 2` | yes | safe |
| `--user 10001:10001` (non-root) | yes | safe |
| `/input` read-only bind | yes | safe |
| `/artifacts` writable bind | yes | safe |
| `/workspace` writable overlay (no host mount) | yes | safe |
| `/tmp` overlay (no tmpfs; mmap fix per P2 commit) | yes | safe |
| `--network` flag | **not set** | **hardening TODO** |
| Docker socket bind | not present | safe |
| `--privileged` | not set | safe |
| Host home directory mounts | none | safe |
| Allow-listed env (`DEFAULT_ENV`) | yes (5 keys) | safe; env not forwarded wholesale |
| `probe_extra_env` (e.g. `COMPLIANCE_TRAJECTORY_PATH`) | passed through `--env` | safe; restricted to the caller's explicit list |

### Security gap classification for corpus-scale

| Gap | Status |
|---|---|
| `--network` not enforced during probe exec | **hardening TODO** (not blocking for the 5 determinstic probes today; blocking for "trust untrusted 1000 repos" — unknown packages could phone home during install even if we trust exec) |
| Subprocess / pip-with-build-hooks execute inside container | safe (in-container) |
| Host secrets in `DEFAULT_ENV` / env-allow-list | safe; no leakage seen |
| Docker socket absent | safe |
| `--privileged` flag | safe |
| `apt` install of system packages from inside framework builds | not enabled today; would be a hardening TODO if added |

---

## 9. Persistence model

Relevant tables:

- `agent_repositories` (corpus metadata only)
- `compliance_runtime_runs` (every runtime attempt)

`compliance_runtime_runs` schema columns (from `migrations/005_compliance_runtime_runs.sql`):

- `repository_id`, `repo_full_name`, `repo_sha`, `repo_branch`
- `requirement_id`, `requirement_version`, `runtime_version`
- `adapter_name`, `adapter_version`
- `status`, `reason`, `result_json`, `evidence_json`
- `scenario_id`
- `started_at`, `completed_at`, `duration_seconds`, `created_at`
- `schema_version`
- Dedup UNIQUE index:
  `(repository_id, requirement_id, requirement_version, repo_sha, scenario_id, adapter_name, adapter_version)`

Can this represent a 1000-repo × many-requirements × multiple-scenarios corpus?

- **Yes** for the result rows themselves (no cardinality issue;
  the table is unbounded).
- **Idempotency**: the dedup key is correct for one execution
  per `(repo, requirement_version, sha, scenario, adapter)`.
- But: **the dedup key makes retries impossible without
  modifying the key**. If two attempts at the same triple
  differ (different probe_artifact, different evidence), the
  second attempt will collide with the first. There is no
  `attempt_id`, no `created_at_retry_batch`, no
  `batch_id`, no `worker_id`.

### Missing concepts in the current schema

For a future corpus runner, these are absent:

- `batch_id` / `corpus_run_id` — group job sets,
- `attempt_id` / `attempt_n` — enable deterministic
  retries,
- `worker_id` — concurrency auditing,
- `execution_backend` — record `subprocess` vs `container`
  vs a future k8s-worker,
- `parent_corpus_run_id` — restart hierarchy,
- `retry_reason` — distinguish transient infra failure from
  permanent failure,
- `queue_state` — `pending / running / completed / failed / cancelled`,
- `cancellation_reason` / `cancel_requested_by`,
- `scheduling_priority`,
- `assigned_at` / `started_by_worker_at`.

The current schema can be extended without breaking the
frozen `schema_version=1`. No schema change is required in
this diagnosis (P6 freeze article §22.3 keeps schema changes
under v1.4.x).

---

## 10. Corpus / repository database inventory

| Table | Rows | Notes |
|---|---:|---|
| `agent_repositories` | 1502 | All Python (primary_language check); 984 enabled + accepted; 518 rejected; 23 `agent_framework`; 139 `coding_agent`; 160 `workflow_agent`. |
| `agent_repository_audits` | 26 | per-repo audit notes |
| `article_runtime_assessments` | 878 | static (non-runtime) AI-Act article classifications |
| `compliance_runtime_runs` | 7 | existing runtime runs |

Filtered to enabled + accepted + Python: **984 candidate repos.**

Observations:

- All 1502 are `primary_language='Python'`.
- Zero `archived` rows; zero `fork` rows.
- `clone_url` and `html_url` are non-NULL on every row.
- **No `head_sha` column** — the corpus does not pin SHAs.
- **No language-binary verification** — `primary_language`
  is whatever GitHub said at scrape time.
- **No license filter** in the corpus. License data is
  present (`license_spdx`) but not used to gate eligibility.
- **No LFS / submodule metadata**.
- The corpus has been hand-curated via `gold_article12_v1_repos.json`
  and `relevance_status` field. This is manual triage.

Other corpus sources in the tree:

- `audit/gold_article12_v1_repos.json` — five pinned repos
  (the same five integrated adapters). Each entry has
  `full_name` and `sha` but is **not** in the DB by SHA.
- The v1.4.0 corpus that is canonical in-DB is
  `agent_repositories`. The five pinned SHAs live outside
  the table (in `audit/` plus Obsidian).

### Multiple corpus sources

There are two corpus sources today:

1. **`agent_repositories` (DB, canonical)** — 1502
   metadata-only Python repos. Used as the source of job
   intake for a future corpus runner.
2. **`audit/gold_article12_v1_repos.json` (file,
   authoritative)** — five pinned repos with SHAs. Used by
   the current run-path. Not derivable from
   `agent_repositories` (no SHA column).

A corpus runner would either:

- (a) add an `agent_repository_pin` table keyed by id →
  sha, or
- (b) resolve SHAs at run time via `git ls-remote`.

(a) is preferred because determinism is the v1 contract.

---

## 11. Batch / concurrency capabilities

Searched for: `multiprocessing`, `concurrent.futures`,
`asyncio.gather`, `ThreadPool`, `ProcessPool`, `Worker`,
`JobQueue`, `TaskQueue`, `Celery`, `RQ`, `arq`, `Dramatiq`.

**Result: none.** The pipeline runs one row at a time
synchronously. The only reference found was GitHub-API
rate-limit sleep in `corpus/github_client.py` (a search
throttle, not a runner primitive).

There is no:

- worker pool,
- job queue,
- async runner,
- database-driven job creation,
- scheduled runner,
- retries,
- concurrency controls.

### CI

`.github/workflows/compliance.yml` runs three sequential
shell steps (one per repo). No matrix. No parallelism.
`.github/workflows/compliance-article-12-1.yml` is a
single-repo `workflow_dispatch`.

### Can Reguard currently accept 500 repository records and process them automatically?

**No.** A human has to (a) decide the SHA per repo,
(b) pick or write an adapter, (c) add a probe, (d) add
an entry to `ADAPTER_REGISTRY`, (e) add a step to
`compliance.yml` or invoke `compliance-check.py` 500
times by hand. No code path today takes a list of
`full_name`s and runs them.

---

## 12. Concurrency / resource control

Container-level limits exist (`--memory 4g`, `--cpus 2`,
`--pids-limit 256`, `--cap-drop ALL`,
`--security-opt no-new-privileges`). Each container has
its own envelope.

**There is no scheduler-level control.** Nothing today
prevents 100 containers × 4 GB = 400 GB of memory if a
human launches them concurrently. There is no max-parallel
container knob; no CPU-budget / memory-budget / disk-budget
gate at host level.

| Knob | Today | Gap |
|---|---|---|
| Max parallel containers | none | required before 100+ |
| Max concurrent installs | none | required before 100+ |
| CPU budget | per-container | no aggregator |
| Memory budget | per-container | no aggregator |
| Disk budget | none | dep install caches can fill `/tmp` |
| Total job timeout | none | per-job only via `run_timeout_seconds` |
| Per-step timeout | yes (install + exec) | ok |
| Backpressure | none | required for any queue |
| Rate limiting | none | required before hitting upstream network |
| Cancellation | none | required for graceful shutdown |

---

## 13. Retry semantics

Searched `Retry`, `retry`, `MAX_RETRIES`, `attempt_id`,
`ExponentialBackoff` in `src/`, `runtime/`,
`migrations/`.

**Result: no retry manager, no attempt tracking.** A
single execution maps to a single `compliance_runtime_runs`
row. Failures (any of `probe_failed`, `no_trajectory`,
`adapter_raised`, `ERROR`, `UNSUPPORTED`) all return
without retry. `pipeline/persistence.insert_run` catches
`sqlite3.IntegrityError` (a race on the dedup key) and
loads the existing row instead — that is idempotency,
not retry.

The `compliance.synthetic.hello` baseline duplicates
across CI runs are caught by the dedup key alone, not by a
retry layer.

The P4 (`unknown / error / unsupported` semantics) and the
v1.4 contract distinguish ERROR (infra) from FAIL (negative
observation). There is no automatic retry currently keyed
on `status == "ERROR"`. Adding one is a v1.4.x engineering
decision, not a contract change.

---

## 14. Result / evidence storage cost

- `compliance-result.json` on disk (CLI path-mode + GHA
  artifact upload).
- `evidence/.../*.json` sibling files (per-run; written via
  `--output`).
- `compliance_runtime_runs.result_json` and
  `compliance_runtime_runs.evidence_json` in SQLite.

Unbounded growth risks today:

- Each run writes **two SQLite blobs** containing the full
  Evidence and Result JSON. For 1000 repos × 10
  requirements × 5 scenarios, this is ~50,000 rows of
  growth on the order of (Evidence + Result) per row. The
  Evidence is bounded per adapter (a few KB). Result is a
  handful of KB.
- Trajectory files on disk under `evidence/`. Bounded by
  adapter (typically <100 KB for our five). With 1000
  repos × 10 req × 5 scenarios that is 50,000 files.
  Total disk ≈ a few GB. Manageable.
- Container stdout/stderr — `container_runner` already
  truncates stderr to 16 KB inside `collect_evidence`
  (`orchestrator.py:768`) and stitches tail logs for
  per-step surfacing.
- GitHub Actions artifacts: `compliance-results/*.json` +
  `eu-ai-compliance-db` — uploaded each job, retained 14
  or 30 days.

There is **no eviction policy** in SQLite or on disk; rows
accumulate forever. For 1000× scale this is workable but
will eventually need a retention policy. **A storage
abstraction is not strictly required before corpus scale;
a retention job is.** Documented as hardening.

---

## 15. Requirement execution reuse

This is one of the most architecture-defining questions.

### Today

Each `compliance-check.py` invocation runs **one
requirement** (default: `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING`)
against one repo + one scenario. The orchestrator is
single-requirement-shaped: there is one
`_PROBE_BY_ADAPTER` lookup and the probe drives a single
scenario shape. Evidence is then handed to one
`RequirementTest` via `get_requirement(requirement_id)`.

### Sharing?

The same probe result could in principle be handed to
multiple `RequirementTest`s. The pipeline does **not**
do this today. Each requirement is launched as an
independent `run_one` / `run_path_mode` call.

`Evidence` itself is **requirement-neutral** at the field
level — the `Evidence` dataclass has no
`requirement_id` field. It's the **probe + adapter** that
is shaped for one requirement.

**Consequence**: cost scales linearly with requirements:
`repos × requirements × executions`.

If a future Article 12(2) is added, **a new
`run_one`-style execution is required per (repo,
scenario)** today — there is no evidence-sharing layer.

The single Article-12(1)-only adapter family does not
currently impose this cost, but at the corpus scale the
difference between `repos × reqs × execs` and
`repos × reqs` becomes decisive.

---

## 16. Scenario architecture

- `Scenario` is a `@dataclass(frozen=True)` with
  `scenario_id`, `user_prompt`, `expected_tool_calls`,
  `max_steps`. First-class.
- It is constructed **once** as `DEFAULT_SCENARIO_12_1`
  in `driver.py:64`. There is no scenario registry; no
  versioning of scenarios; no "supported by this adapter"
  map.
- Every adapter's `render_synthetic_task` returns
  `scenario.user_prompt` verbatim — **the orchestrator
  parameter is not consumed by any probe**. The
  parameterisation surface exists but is unused today.
- Two scenarios with the same `scenario_id` and
  `user_prompt` are deduped via the
  `compliance_runtime_runs` UNIQUE index. Two scenarios
  with the same `(repo, requirement, sha, adapter)` tuple
  but different `scenario_id` are kept as separate rows.
- The P5 study added stable IDs
  (`compliance.article12_1.simple`, etc.) but they are
  **not yet persisted by the runtime path** — the runtime
  still uses `compliance.synthetic.hello` (semantic S1).

**Gaps**:

- Scenarios are not pinned-versioned.
- Scenarios are not declared supported / unsupported per
  adapter.
- Scenarios cannot be shared across requirements because
  every adapter probe is fixed-shape.

---

## 17. Capability model

`AdapterCapabilities` exists with:

- `python_version` (default `"3.12"`),
- `needs_network` (default `False`),
- `install_timeout_seconds` (default `600`),
- `run_timeout_seconds` (default `120`),
- `install_command` (default `""` → orchestrator uses
  `pip install -e .`).

It is read in `orchestrator.run_probe`:

- `install_command` for the install command,
- `install_timeout_seconds` for the pip subprocess,
- `run_timeout_seconds` for the probe subprocess,
- implicitly `python_version` is used to pick a Python
  interpreter (but the runtime image is hard-coded to
  3.12).

There is **no** scenario-support capability, **no** tool-support
capability, **no** async-support capability, **no**
fake-model capability, **no** persistence-side capability,
**no** skill-support / event-bus / session-store capability
declared in code. A scenario-vs-adapter scheduling decision
cannot be made by the orchestrator because the capability
data does not exist.

---

## 18. Framework-family reuse

Common patterns across the five adapters that are
duplicated, not shared:

| Pattern | Used by |
|---|---|
| Read a JSON trajectory written by the probe; map role→kind | all 5 |
| Path-existence / size > 0 == persistence check | gptme, mini-swe-agent |
| Five-field `extra` block (`recording_category`, `framework_persists_durably`, `framework_artifact_paths`, `harness_artifact_paths`, `scenario_id`) | all 5 (duplicated literally) |
| Hard-coded `recording_category` literal | each adapter |
| Producer / collector string | each adapter |
| Probe writes `trajectory.json` shape | all 5 |
| Workspace scan to filter harness-written files | PocketFlow; others ad-hoc |
| `SYSTEM_NATIVE` / `SYSTEM_STATE_EXPORTED_BY_HARNESS` stamping | all 5 |
| `Message(role="user", content=...)` plus `Message(role="assistant", content=...)` fake-model construction | gptme; conceptually similar shape in CoreCoder's FakeLLM and mini-swe-agent's DeterministicModel |
| Bus-event subscription | nanobot |

**Classification**: the current adapters are encoding
**entire repositories**, not reusable observation patterns.
The five adapter classes share a parse_trajectory skeleton
(role→kind map + 5-field extra dict), but that skeleton is
copy-pasted, not extracted into a base helper.

A common base helper that receives (probe-shaped
trajectory, role_kind_map, category, producer, collector)
would reduce per-adapter code by ~50%. **No refactor is
proposed in this diagnosis.** Identifying the duplicate is
the point.

---

## 19. Orchestrator coupling

The orchestrator's repo-specific coupling is in:

- `_PROBE_BY_ADAPTER` — keyed by `adapter.name`; adding a
  new adapter requires editing this dict. **Required
  edit.** Repo #6 → orchestrator.py edit.
- `if executor == "container"` branch in `run_probe` —
  generic; no repo-specific branch.
- `_PROBE_BY_ADAPTER` lookup is the only repo-name branch
  in the orchestrator.

Repo-name conditionals: **0**.
Adapter-name conditionals: **2** (probe lookup × 2 paths:
subprocess + container). Not a smell because both paths
must agree.
Requirement-specific branches: **0** — the orchestrator
is requirement-agnostic. Confirmed by
`_PROBE_BY_ADAPTER` lookup + `requirement_id` parameter
flowing into `RequirementTest.evaluate`.
Scenario-specific branches: **0**.
Container-specific behaviour: 1 branch (`if executor ==
"container"`); this is executor-specific, not
repo-specific — fine.
Evidence-specific behaviour: 0; universal in
`collect_evidence`.

**Result**: the orchestrator is **scarcely coupled** to
repo specifics. The adapter registry plus the probe
dictionary are the only two extension points. Both are
explicit and small. This is good for
requirement-scaling, neutral for repo-scaling (the
extension points remain repo-by-repo).

**Smell**: adding repo #6 requires editing two
hard-coded dictionaries (`ADAPTER_REGISTRY` and
`_PROBE_BY_ADAPTER`) plus writing a new adapter class and
a new probe. The dictionaries are the extension surface;
they are explicit, not implicit. The only refactor
candidate is to move `_PROBE_BY_ADAPTER` to a sibling
file (`probes.py`) so the orchestrator module is
exclusively control flow. Not blocking.

---

## 20. CI architecture

Current GitHub Actions workflows in `.github/workflows/`:

| File | Trigger | Jobs | Purpose |
|---|---|---|---|
| `compliance.yml` | push / pull_request / manual | 1 (`compliance`) | Hard-coded three-rep run, sequential |
| `compliance-article-12-1.yml` | manual dispatch | 1 (`article-12-1`) | Single repo input box |
| `runtime-smoke.yml` | (per its own logic) | (smoke) | runtime / detect unit checks |

None of these is a real corpus runner:

- No matrix strategy.
- No concurrency (`jobs.compliance` is single).
- Hard-coded repos / SHAs.
- Hard-coded requirement ID.
- Timeout 30 minutes (sufficient for 3 repos, insufficient
  for 100).

**Assessment**: GitHub Actions today is **validation CI for
Reguard itself**. It is not a production corpus-scheduling
backend. Using GHA matrix for 1000 repos would mean 1000
matrix entries × full image build per entry, which
**violates GHA's free-tier matrix limits** and would be
operationally prohibitive.

A future corpus runner is therefore almost certainly a
local orchestrator (Python) plus an in-house queue or a
dedicated worker pool. **GHA is not the corpus
production backend.**

---

## 21. Current-state architecture map

```text
Repository corpus (DB, 984 candidate repos)
  agent_repositories table (no SHA column)
        ↓
Manual triage / SHA pinning           (audit/gold_article12_v1_repos.json)
        ↓
Hand-authored adapter                  src/compliance/adapters/<framework>.py
        ├── parse_trajectory
        ├── capabilities
        ├── render_synthetic_task
        └── resolve_agent
        ↓
Hand-authored probe source             src/compliance/pipeline/orchestrator.py
        (_PROBE_BY_ADAPTER)
        ↓
Hard-coded ADAPTER_REGISTRY            src/compliance/adapters/registry.py
        ↓
CLI entrypoint                         scripts/compliance-check.py
        │
        ▼
driver.run_one
  ├── db lookup (if persist)
  ├── adapter dispatch (KeyError -> UNSUPPORTED)
  ├── clone-to-tempdir (no cache)
  ├── _run_pipeline
  │     ├── orchestrator.run_probe
  │     │     ├── fresh venv (no cache)
  │     │     ├── pip install -e . (no cache)
  │     │     └── probe (subprocess or container_runner)
  │     ├── collect_evidence
  │     ├── adapter.parse_trajectory
  │     ├── RequirementTest.evaluate
  │     └── insert_run (UNIQUE dedup key)
  │
  ▼
RunRecord -> compliance-result.json (--output)
RunRecord -> compliance_runtime_runs (DB)
RunRecord -> EXIT_CODE[status]
```

Manual / repo-specific boundaries are at every `↓`
marked "Hand-authored" above (and at the registry /
`_PROBE_BY_ADAPTER`).

---

## 22. Scalability bottleneck table

| Area | Current mechanism | Works for 5 repos? | Works for 1000? | Why / why not |
|---|---|---:|---:|---|
| Repository inventory | `agent_repositories` table, 984 enabled+accepted Python repos; no SHA column | yes | yes | Sufficient — column-add suffices for SHA |
| SHA management | hand-pinned `audit/gold_article12_v1_repos.json`; not in DB | yes | **no** | Manual per-repo work; no DB-backed pinning |
| Adapter selection | hard-coded `ADAPTER_REGISTRY` keyed by `full_name` | yes | **no** | O(repos) entries required |
| Repo setup | fresh clone per run, no cache | yes | **no** | repeated network I/O cost |
| Dependency installation | `pip install -e .` per probe, no cache | yes | **no** | repeated CPU/network cost |
| Probe selection | hard-coded `_PROBE_BY_ADAPTER` dict keyed by `adapter.name` | yes | **no** | O(repos) entries required |
| Scenario selection | single `DEFAULT_SCENARIO_12_1`; P5 IDs exist but unused by runtime | yes | partial | Capabilities not declared; scheduling not feasible |
| Container scheduling | one container per run, FIFO via sub-process | yes | **no** | No concurrency control / no scheduler |
| Concurrency | none | yes | **no** | No parallelism / max-parallel knob |
| Caching | none | yes | **no** | pip/clone repeated every run |
| Retries | none | yes | partial | Status = ERROR not auto-retried; for one repo ERR is rare, for 1000 it is the norm during bring-up |
| Evidence storage | SQLite blobs + on-disk JSON + GHA artifact upload | yes | yes | Bounded; retention policy missing |
| Deduplication | UNIQUE index covers `(repo, requirement_version, sha, scenario, adapter)` | yes | yes | Correct as-is; would not survive retries (no `attempt_id`) |
| Requirement reuse | one requirement per execution; no evidence sharing across requirements | yes | partial | OK at 1 requirement; would scale linearly at 2+ |
| Observability | one-line JSON to stdout; no progress aggregation | yes | partial | Insufficient for 1000 concurrent jobs |
| CI | manual workflow with one-or-three hard-coded repos | yes | **no** | GHA matrix limits; per-job image rebuild |
| Result reporting | hand-written Markdown aggregator | yes | partial | Not corpus-driven |

---

## 23. Missing architectural primitives

For each, classified by when it becomes required.

| Primitive | Why needed | Current code substitute | Required before 20? | Required before 100? | Required before 1000? | Required before multi-article? |
|---|---|---|:---:|:---:|:---:|:---:|
| `CorpusRun` / `batch_id` | group job sets; restart; cancel one batch | none | **yes** | yes | yes | yes |
| `EvaluationJob` / `attempt_id` | idempotent retries without breaking the dedup UNIQUE index | none (dedup collides on retry) | partial | **yes** | yes | yes |
| Worker pool | run N probes in parallel | one subprocess.run at a time | **yes** | yes | yes | yes |
| Scheduler | dispatch jobs at controlled rate | none | **yes** | yes | yes | yes |
| Repository manifest with SHA | determinism per repo at any run | hand-pinned `audit/gold_article12_v1_repos.json` | **yes** | yes | yes | yes |
| Capability resolver | decide which adapters / scenarios a repo can run | hard-coded `ADAPTER_REGISTRY` | **yes** | yes | yes | yes |
| Execution recipe | parameterised, callable, testable | `install_command` + `install_timeout_seconds` + `run_timeout_seconds` | partial | partial | yes | yes |
| Observer abstraction | share observation logic across frameworks | each adapter duplicates parse_trajectory skeleton | partial | yes | yes | yes |
| Probe registry (was: dict constant) | move `_PROBE_BY_ADAPTER` out of orchestrator module | inline dict in orchestrator | partial | partial | partial | partial |
| Scenario registry | first-class scenario versions + capability matching | single `DEFAULT_SCENARIO_12_1` literal | partial | yes | yes | yes |
| Install cache | avoid re-installing the same repo's deps every run | none | **yes** | yes | yes | yes |
| Repo cache | avoid re-cloning | none | yes | yes | yes | yes |
| Evidence store | uniform location for `result_json` / `evidence_json` | `compliance_runtime_runs` + on-disk files | no | partial | partial | yes |
| Batch progress reporting | summarise 1000-row run | per-run one-line JSON only | partial | yes | yes | yes |
| Retry policy | ERROR -> retry transient infra failures | none | partial | yes | yes | yes |
| Cancellation | stop a batch | none | partial | yes | yes | yes |
| Resource governor | max-parallel container / memory / disk budget | per-container only | **yes** | yes | yes | yes |
| Idempotent SHA pinning (DETERMINISM) | SHA-per-row at run time without breaking dedup | none | **yes** | yes | yes | yes |
| Network policy (2-phase) | install=enabled, probe=disabled | single-phase | no | partial | yes | yes |

---

## 24. Components that should NOT be rebuilt

These are validated under the v1.4.0 freeze and should
remain as-is or evolve incrementally:

- `RequirementTest` and the v1.4.0 check set.
- `RunStatus` (PASS / FAIL / UNKNOWN / ERROR / UNSUPPORTED).
- `Evidence` dataclass and `EvidenceOrigin` enum.
- OCI runtime abstraction (`container_runner.discover_runtime`
  + `run_in_container`).
- Restricted runtime image (`runtime/Dockerfile`; UID 10001,
  capabilities, no-new-privileges, pids/memory/cpu limits,
  read-only `/input`, writable `/artifacts`).
- Adapter `parse_trajectory` shape (5-field `extra` block,
  event origins, framework_persists_durably).
- Persistence (`compliance_runtime_runs` schema v1; UNIQUE
  dedup key).
- `_verify_checkout_sha` and exact-SHA provenance enforcement.
- CLI exit-code map (0/1/2/3/4).

The freeze record (Article 12(1) v1.4.0) is not in this
list because it is a **requirement**, not a component.

---

## 25. Combinatorics answer

| Workload | Today |
|---|---|
| 100 repos × Article 12(1) | O(100): 100 adapter entries in `ADAPTER_REGISTRY`; 100 probe entries in `_PROBE_BY_ADAPTER`; 100 hand-picked SHAs; 100 sequenced runs. No code changes if we hand-write the adapter + probe each time. **Cost dominated by human labour, not CPU.** |
| 100 repos × 10 runtime requirements | O(100) per requirement to add an adapter; **10 × 100 = O(1000)** adapter entries (untenable). |
| 1000 repos × 10 runtime requirements | O(10,000) adapter entries if every repo needs its own adapter. The architecture **trends dangerously close to O(repos × requirements)** if every repo has a unique adapter and every requirement rewires the adapter layer. |

The dominant reason is **adapter proliferation**, not
probe proliferation: probes are requirement-agnostic
(keyed by `adapter.name`); adapters are repo-specific
(keyed by `full_name`). If the architecture were rewritten
to key adapters by **framework family** + capability, the
constant would drop dramatically.

**Conclusion**: today the architecture grows as
**O(repos)** (one adapter + one probe per repo). It can
be flattened to **O(framework-families)** with framework
detection (e.g. "any repo importing `nanobot.bus` is C;
any repo using `gptme.logmanager` is B; any repo using a
`LogManager`-shaped class is B"). That is the principled
path. Until then, cost is O(repos).

---

## 26. Three problems, separated

| Problem | Maturity | Evidence |
|---|---|---|
| **A. Corpus orchestration** (jobs, queue, retries, persistence) | **missing** | No worker pool, no queue, no retry manager, no attempt_id, no batch_id |
| **B. Repository integration scalability** (any Python AI-agent repo becomes executable) | **partial** | Build-strategy detection mature (uv / Poetry / pip / hatchling / pdm / maturin / mesonpy); install path mature; adapter layer is O(repos); no framework-family detection; no per-repo capability resolver |
| **C. Requirement scalability** (multiple Articles consume shared evidence) | **usable prototype** | Single requirement shipped (v1.4.0). Evidence is requirement-neutral at the dataclass level; probe is requirement-neutral (`_PROBE_BY_ADAPTER` keyed by adapter.name); no evidence-sharing layer across requirements yet |

---

## 27. Minimum corpus-runner v1 architecture

The minimum delta needed to move from "5 manually
integrated repos" to "database-driven batch evaluation
against Article 12(1)".

### Required now (before any 20-repo batch)

1. **SHA-pin table** — new `agent_repository_pin`
   (repository_id, sha, requirement_id) keyed by
   `repository_id`. Today there is no SHA column. Without
   it, the dedup uniqueness cannot survive batch reruns.
2. **`CorpusRun` bookkeeping** — add
   `corpus_run_id` (UUID) + `attempt_id` (smallint)
   columns to `compliance_runtime_runs`. **Schema
   version bump allowed under v1.4.x freeze** because no
   semantic check relies on the row key shape; the change
   is purely additive for retries.
3. **Capability resolver** — extend `AdapterCapabilities`
   with `scenario_support: list[str]` (codes like
   `S1..S5`). Until capability declarations exist, the
   runner cannot decide which scenarios to drive.
4. **Worker pool** — small bounded pool (4–8 workers);
   in-process; no external queue. Submit jobs via
   `concurrent.futures.ProcessPoolExecutor` or
   `ThreadPoolExecutor`. The orchestrator is
   already-isolated (fresh venv per run), so processes
   are correct.
5. **Resource governor** — `max_parallel_containers`,
   `max_parallel_disk_bytes` (quota on tmpfs), backpressure
   on the queue.
6. **Two-phase network policy** — `--network=...` passed
   per OCI runtime step. install=enabled, probe=disabled
   is the documented hardening TODO.
7. **Batch progress reporter** — single JSONL progress
   stream + tail-able summary table.
8. **Deterministic SHA resolution** — `git ls-remote
   origin HEAD` happens once before the batch starts, and
   the resolved SHAs are persisted into the pin table.

### Required before 100 repos

9. **Install cache** — extract a pip-cache or uv-cache
   key (sha of the build-strategy + content-hash of
   `requirements*.txt` / `pyproject.toml` / `poetry.lock` /
   `uv.lock`); store under a host-controlled cache dir.
10. **Repo cache** — content-addressed clone cache (`git
    clone --reference`) keyed by `(clone_url, sha)`.
11. **Retry policy** — transient infra failure (e.g.
    `container_error`) retries up to N times; non-transient
    (e.g. `unsupported`, `adapter_raised`) does not. The
    `attempt_id` column above makes this recordable.
12. **Cancellation** — request-stop flag the worker pool
    checks between runs.

### Required before 1000 repos / multi-article

13. **Framework-family detection** — observe import paths
    or class shapes to map a repo to a registered
    capability class, instead of one adapter per
    `full_name`.
14. **Evidence-sharing across requirements** — execute
    once, dispatch Evidence to multiple `RequirementTest`s.
15. **Storage abstraction** — replace ad-hoc `result_json`
    / `evidence_json` blobs with a versioned
    `evidence_store` object. **Storage abstraction is not
    strictly required before 1000** but becomes a
    bottleneck when retention/rbac policy arrives.
16. **Retention policy** — periodic GC of
    `compliance_runtime_runs` rows older than N, with
    exception class for "frozen-contract pinned".

### Defer until later (out of scope)

17. **External queue** (Redis / Postgres job queue) — only
    after local ProcessPool becomes the bottleneck.
18. **Multi-worker host scheduler** (k8s / Nomad) — only
    after single-host becomes the bottleneck.
19. **GHA matrix as a corpus runner** — explicitly
    rejected; GHA today is validation CI, not a corpus
    scheduler.

---

## 28. Safe first scale test

### 20-repo batch proposal (NOT executed in this diagnosis)

**Goal**: measure the *infrastructure* behaviour, not
compliance statistics. The 20 rows must come from the DB,
not be hand-picked, to avoid selection bias.

**Suggested selection criterion** (filter only — no source
inspection):

```text
FROM agent_repositories
WHERE primary_language = 'Python'
  AND relevance_status = 'accepted'
  AND enabled = 1
  AND archived = 0
  AND fork = 0
ORDER BY stars DESC
LIMIT 5                       -- accept the 5 current integrated
UNION ALL
ORDER BY stars DESC
LIMIT 15                      -- next 15 by stars, accepted, enabled
```

Manual triage is still required to pin SHAs, but the
*count* and *kind* of repos is corpus-driven.

**Targets to measure**:

- clone success rate,
- install support rate (uv / Poetry / pip / setuptools /
  hatchling / pdm / maturin / mesonpy / unsupported),
- adapter coverage (what fraction of 20 need new
  adapters, vs. what fraction land in
  `UNSUPPORTED` via the no-adapter path),
- probe success (probe exits 0, trajectory non-empty),
- container reliability (container exit 0 + trajectory
  written),
- result distribution (PASS / FAIL / UNKNOWN / ERROR /
  UNSUPPORTED counts),
- ERROR cause distribution
  (probe_failed / no_trajectory / adapter_raised /
  schema_mismatch),
- UNKNOWN cause distribution
  (empty bundle without observed_absence),
- UNSUPPORTED rate (no adapter),
- average pip-install cost per repo (cached vs not),
- average probe duration per repo (cached vs not).

### 50-repo second gate

Same selection criterion (`LIMIT 50` instead of 20).
Adds infrastructure-side confidence: cumulative
distribution, cache hit rate, container reuse rate.

Neither batch is to be executed under this diagnosis task.

---

## 29. Reference outputs

This document is the implementation-facts companion to the
Obsidian study note
`Reguard/Study/Corpus Evaluation Pipeline Architecture.md`.

The frozen Article 12(1) v1.4.0 implementation note
(`EU AI Act/Runtime Analysis/Article 12(1) - Automatic
Event Logging.md`) is **not** modified by this diagnosis.
The v1.4.0 contract and P1–P6 audit history remain
authoritative.
