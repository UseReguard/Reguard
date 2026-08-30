# Reguard v1.1.1 — Test Accounting Closure

**Scope:** Explain every one of the 233 collected tests. Verify all
required container-closure tests actually executed. Identify the
229 → 233 delta. Identify why the prior closure reported "184
passed".

**Date:** 2026-08-29
**Runtime version:** v1.1.1

**Constraints honoured (verbatim):**
- ✅ Did NOT change implementation unless the audit revealed
  accidental test exclusion. None found.
- ✅ Did NOT run 50-repository gate.
- ✅ Did NOT add adapters.
- ✅ Did NOT add framework-family detection.
- ✅ Did NOT start Article 12(2).
- ✅ Did NOT change Article 12(1) v1.4.0.

---

## 1. Test inventory

```bash
$ python3 -m pytest tests/ --collect-only -q
...
233 tests collected in 0.16s
```

**`total_collected = 233`.**

---

## 2. Run with full reporting

```bash
$ python3 -m pytest tests/ -ra
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/mrcel/projects/business/compliance-tool
configfile: pytest.ini (WARNING: ignoring pytest config in pyproject.toml!)
plugins: anyio-4.14.2, typeguard-4.4.4
collected 233 items

... (file-by-file summary) ...

============================= 233 passed in 18.26s =============================
```

**Final tally:**

| Outcome     | Count |
|-------------|------:|
| passed      | 233   |
| failed      | 0     |
| errors      | 0     |
| skipped     | 0     |
| deselected  | 0     |
| xfailed     | 0     |
| xpassed     | 0     |

---

## 3. Accounting equation

```text
collected    = 233
passed       = 233
skipped      =   0
xfailed      =   0
xpassed      =   0
failed       =   0
errors       =   0
deselected   =   0
```

```text
collected (233)
  = passed    (233)
  + skipped   (  0)
  + xfailed   (  0)
  + xpassed   (  0)
  + failed    (  0)
  + errors    (  0)
  + deselected(  0)
  = 233   ✅ exact match
```

**Equation balances. Zero unexplained remainder.**

---

## 4. Classification of non-passing collected tests

**There are none.** All 233 collected tests passed on this runner.

The two tests that **could** have been skipped are gated by an OCI
runtime check, but the gate resolved to **true** (podman is on
PATH), so they executed:

| File                                                    | Marker                                           | Reason (when skipped)                                | Status here |
|---------------------------------------------------------|--------------------------------------------------|------------------------------------------------------|-------------|
| `tests/pipeline/test_oci_artifact_contract.py`          | `pytest.mark.skipif(not _have_oci_runtime(), ...)` | "no OCI runtime on PATH (docker or podman)"          | **PASSED** |
| `tests/pipeline/test_gptme_container_frozen_sha.py`     | `pytest.mark.skipif(not _have_oci_runtime(), ...)` | "no OCI runtime on PATH (docker or podman) — container executor integration test cannot run" | **PASSED** |
| `tests/pipeline/test_path_mode.py`                      | `pytest.mark.skipif(not _HAVE_GIT, reason="git not available")` | git unavailable                                     | **PASSED** (git available) |

Since none of these gates fired, the set of "non-passing collected
tests" is empty. If any were skipped, their classifications would
have been:

| Class                                 | File                                              |
|---------------------------------------|---------------------------------------------------|
| `OCI_RUNTIME_UNAVAILABLE`             | `test_oci_artifact_contract.py`, `test_gptme_container_frozen_sha.py` |
| `EXTERNAL_DEPENDENCY_UNAVAILABLE`     | `test_path_mode.py`                              |

---

## 5. Required final-closure container tests — execution proof

Every required v1.1.1 container-closure test was located, executed,
and **passed**:

| Required test                                                                      | File                                                    | COLLECTED | EXECUTED | PASSED |
|------------------------------------------------------------------------------------|---------------------------------------------------------|:---------:|:--------:|:------:|
| OCI artifact write contract                                                         | `tests/pipeline/test_oci_artifact_contract.py::test_oci_artifact_write_contract` | 1 | 1 | 1 |
| gptme frozen-SHA container executor integration                                    | `tests/pipeline/test_gptme_container_frozen_sha.py::test_gptme_container_frozen_sha_reproduces_pass` | 1 | 1 | 1 |
| Cold-cache materialization replay (5 repos, 5 misses, 5 fetches, 0 hits)          | `tests/cache/test_cold_warm_cache_replay.py::test_cold_then_warm_5_repos` | 1 | 1 | 1 |
| Cache-hit avoids re-clone metrics                                                   | `tests/cache/test_cold_warm_cache_replay.py::test_cache_hit_avoids_reclone_metrics` | 1 | 1 | 1 |
| Cache loss / refetch (compliance semantics preserved)                              | `tests/cache/test_v1_1_1.py::test_cache_loss_refetches_with_same_semantics` | 1 | 1 | 1 |
| Workspace cleanup on every terminal state (3 tests)                                 | `tests/cache/test_workspace_cleanup_all_states.py` | 3 | 3 | 3 |
| Workspace per-run metric accounting (4 tests)                                       | `tests/cache/test_per_run_metric_regression.py` | 4 | 4 | 4 |
| RepositoryMaterializer hot path = `run_with_prepared_checkout`                      | `tests/cache/test_v1_1_1.py::test_materialization_metrics_recorded` | 1 | 1 | 1 |
| Cache isolation / malicious cache mutation (workspace cannot reach cache)          | `tests/cache/test_v1_1_1.py::test_malicious_cache_mutation_blocked` | 1 | 1 | 1 |
| Security: cache objects not writable from workspace                                 | `tests/security/test_ephemeral_execution.py::test_cache_objects_not_writable_from_workspace` | 1 | 1 | 1 |
| Security: workspace path cannot escape root                                         | `tests/security/test_ephemeral_execution.py::test_workspace_path_cannot_escape_root` | 1 | 1 | 1 |
| Security: malicious symlink cannot escape artifacts                                 | `tests/security/test_ephemeral_execution.py::test_malicious_symlink_cannot_escape_artifacts` | 1 | 1 | 1 |
| Concurrent materialization (same repo, same SHA)                                   | `tests/cache/test_v1_1_1.py::test_concurrent_materialization_same_repo_same_sha` | 1 | 1 | 1 |
| Concurrent materialization (same repo, different SHA)                              | `tests/cache/test_v1_1_1.py::test_concurrent_materialization_same_repo_different_sha` | 1 | 1 | 1 |
| GC lock race (locked entry skipped by GC)                                           | `tests/cache/test_v1_1_1.py::test_gc_does_not_evict_active_materializer_entry` | 1 | 1 | 1 |
| Stale attempt workspace cleaned by janitor                                          | `tests/cache/test_crash_recovery.py::test_stale_attempt_workspace_cleaned_by_janitor` | 1 | 1 | 1 |
| Active attempt workspace protected from janitor                                     | `tests/cache/test_crash_recovery.py::test_active_attempt_workspace_protected_from_janitor` | 1 | 1 | 1 |
| Post-crash idempotence                                                              | `tests/cache/test_crash_recovery.py::test_post_crash_idempotent` | 1 | 1 | 1 |
| `build_jobs_for_run` idempotence at persistence boundary                            | `tests/cache/test_build_jobs_idempotence.py::test_build_jobs_for_run_is_idempotent` | 1 | 1 | 1 |
| Actual 20-repo resume (CR-2 manifest replay)                                        | `tests/cache/test_actual_20_run_resume.py::test_actual_20_run_resume` | 1 | 1 | 1 |
| Article 12(1) v1.4.0 unsupported-repo short-circuit (no driver call)               | `tests/corpus/test_corpus_runner_v1.py::test_unsupported_repo_short_circuits_without_driver_call` | 1 | 1 | 1 |

**Zero required container-closure tests were skipped.** All
executed and passed. The OCI runtime (`podman 5.7.0`) is available
on this host, so the OCI skipif gate in the two container integration
tests did not fire.

---

## 6. Explanation of "184 passed" in the prior closure

The prior v1.1.1 container closure ran:

```bash
python3 -m pytest tests/ --ignore=tests/runtime --ignore=tests/docker -q
```

which explicitly excluded:

- **`tests/runtime/`** — 49 collected tests
  (14 detect + 11 inspect + 11 result_schema + 8 test_mode + 5 timeout = 49)

The `tests/docker/` directory does not exist (was never created), so
its `--ignore` had no effect.

**The 184 figure = 233 collected − 49 runtime tests excluded.**

This was not a test failure, skip, or accidental collection loss.
It was an **explicit directory-level filter** passed on the pytest
command line. The 49 runtime tests are real and pass when the
filter is dropped (as confirmed in this closure).

---

## 7. Explanation of 229 → 233 delta

The previous readiness audit reported **229 collected / 229 passing**.
The current closure reports **233 collected / 233 passing**.

**Delta: +4 tests.**

These are the four tests added in
`tests/cache/test_per_run_metric_regression.py` during the final
container-backed cache closure:

| # | File                                               | Test name                                       |
|---|----------------------------------------------------|-------------------------------------------------|
| 1 | `tests/cache/test_per_run_metric_regression.py`    | `test_prepare_then_cleanup_yields_one_one_zero` |
| 2 | `tests/cache/test_per_run_metric_regression.py`    | `test_unsupported_short_circuit_no_workspace`   |
| 3 | `tests/cache/test_per_run_metric_regression.py`    | `test_per_run_metric_isolation`                 |
| 4 | `tests/cache/test_per_run_metric_regression.py`    | `test_orphan_after_failed_materialization`      |

All four are regression tests for §16 metric correctness in the
v1.1.1 container closure:

- (1) pins `workspaces_created == 1, workspaces_destroyed == 1,
  orphaned_workspaces == 0` for one prepare→cleanup.
- (2) pins the UNSUPPORTED pre-execution short-circuit produces no
  workspace at all.
- (3) pins per-run metric isolation (fresh materializer per run).
- (4) pins that a failed materialization still destroys the
  workspace, leaving zero orphans.

`229 + 4 = 233` ✅.

---

## 8. Per-file counts

Full collection breakdown by file:

| Test file                                                  | Collected | Passed | Skipped | XFail | Failed |
|------------------------------------------------------------|----------:|-------:|--------:|------:|-------:|
| tests/cache/test_actual_20_run_resume.py                   | 1         | 1      | 0       | 0     | 0      |
| tests/cache/test_build_jobs_idempotence.py                 | 1         | 1      | 0       | 0     | 0      |
| tests/cache/test_cold_warm_cache_replay.py                 | 2         | 2      | 0       | 0     | 0      |
| tests/cache/test_crash_recovery.py                        | 3         | 3      | 0       | 0     | 0      |
| tests/cache/test_per_run_metric_regression.py             | 4         | 4      | 0       | 0     | 0      |
| tests/cache/test_source_cache.py                          | 9         | 9      | 0       | 0     | 0      |
| tests/cache/test_v1_1_1.py                                 | 6         | 6      | 0       | 0     | 0      |
| tests/cache/test_workspace_cleanup_all_states.py           | 3         | 3      | 0       | 0     | 0      |
| tests/corpus/test_corpus_cli_includes.py                   | 11        | 11     | 0       | 0     | 0      |
| tests/corpus/test_corpus_runner_v1.py                      | 25        | 25     | 0       | 0     | 0      |
| tests/corpus/test_cr2_resume_invariant.py                 | 1         | 1      | 0       | 0     | 0      |
| tests/evidence/test_retention.py                           | 5         | 5      | 0       | 0     | 0      |
| tests/pipeline/test_artifact_write_contract.py             | 2         | 2      | 0       | 0     | 0      |
| tests/pipeline/test_compliance_pipeline.py                 | 22        | 22     | 0       | 0     | 0      |
| tests/pipeline/test_gptme_container_frozen_sha.py          | 1         | 1      | 0       | 0     | 0      |
| tests/pipeline/test_observation_quality.py                 | 17        | 17     | 0       | 0     | 0      |
| tests/pipeline/test_oci_artifact_contract.py               | 1         | 1      | 0       | 0     | 0      |
| tests/pipeline/test_p4_result_states.py                    | 18        | 18     | 0       | 0     | 0      |
| tests/pipeline/test_p5_scenario_variants.py                | 29        | 29     | 0       | 0     | 0      |
| tests/pipeline/test_path_mode.py                           | 13        | 13     | 0       | 0     | 0      |
| tests/requirements/test_legal_text_parser.py               | 7         | 7      | 0       | 0     | 0      |
| tests/runtime/test_detect.py                               | 14        | 14     | 0       | 0     | 0      |
| tests/runtime/test_inspect.py                              | 11        | 11     | 0       | 0     | 0      |
| tests/runtime/test_result_schema.py                        | 11        | 11     | 0       | 0     | 0      |
| tests/runtime/test_test_mode.py                            | 8         | 8      | 0       | 0     | 0      |
| tests/runtime/test_timeout.py                              | 5         | 5      | 0       | 0     | 0      |
| tests/security/test_ephemeral_execution.py                 | 3         | 3      | 0       | 0     | 0      |
| **TOTAL**                                                  | **233**   | **233**| **0**   | **0** | **0**  |

Sum check: 1+1+2+3+4+9+6+3+11+25+1+5+2+22+1+17+1+18+29+13+7+14+11+11+8+5+3 = **233** ✅

By area:

| Area                       | Collected |
|----------------------------|----------:|
| Corpus runner              | 37        |
| Cache                      | 29        |
| Pipeline                   | 102       |
| Evidence                   | 5         |
| Runtime                    | 49        |
| Security                   | 3         |
| Requirements               | 7         |
| **Total**                  | **233**   |

---

## 9. Test / config exclusion audit

### pytest configuration files

```text
pytest.ini:
  [pytest]
  testpaths = tests
  pythonpath = . src
  addopts = -ra
  norecursedirs = tests/runtime/fixtures

pyproject.toml [tool.pytest.ini_options]:
  testpaths = ["tests"]
  pythonpath = [".", "src"]
  addopts = "-ra"
  norecursedirs = ["tests/runtime/fixtures"]
```

(`pytest.ini` is the live config; the duplicated block in
`pyproject.toml` is ignored with a warning.)

### Filtering analysis

| Filter mechanism                          | Effect                                                | Hidden tests? |
|-------------------------------------------|-------------------------------------------------------|---------------|
| `testpaths = tests`                       | Only `tests/` is scanned                              | No — desired  |
| `addopts = -ra`                           | Adds summary of all non-pass outcomes (no filtering)  | No — desired  |
| `norecursedirs = tests/runtime/fixtures` | Excludes fixtures dir (NOT a test dir)                | No — fixtures, not tests |
| `--ignore=tests/runtime` (prior closure)  | Excluded 49 runtime tests on the command line         | Yes — by explicit filter, NOT a config change |
| `--ignore=tests/docker` (prior closure)   | No effect — `tests/docker/` does not exist            | No             |

**There has been no broad marker/filter/config change that silently
removed previously collected tests.** The prior `184` figure was a
command-line filter, not a configuration regression.

### Markers in test code

Three skipif markers exist in the test suite, none of which fired
on this runner:

| File                                                  | Marker                                                    | Resolved  |
|-------------------------------------------------------|-----------------------------------------------------------|-----------|
| `tests/pipeline/test_oci_artifact_contract.py`        | `skipif(not _have_oci_runtime(), ...)`                    | **ran** (podman present) |
| `tests/pipeline/test_gptme_container_frozen_sha.py`   | `skipif(not _have_oci_runtime(), ...)`                    | **ran** (podman present) |
| `tests/pipeline/test_path_mode.py`                    | `skipif(not _HAVE_GIT, ...)`                              | **ran** (git present)    |

### Environment-variable gates

The runtime tests use `REPO_RUNTIME_WORKSPACE` (set in
`tests/runtime/conftest.py` to a per-session tempdir). No test
selection or skipping is driven by environment variables beyond the
OCI/git presence checks already documented above.

**No accidental test/config exclusion exists.**

---

## 10. Remaining test-accounting issues

**None.** Every collected test is accounted for. Every required
container-closure test executed and passed. The 184 figure was a
command-line filter. The 229 → 233 delta is the four new metric
regression tests in `test_per_run_metric_regression.py`.

---

## 11. Readiness for the 50-repository gate

Per the readiness rule:

1. ✅ All 233 tests are accounted for (233 = 233 passed + 0 skipped +
   0 xfailed + 0 xpassed + 0 failed + 0 errors + 0 deselected).
2. ✅ Zero failures.
3. ✅ Zero unexplained collection gaps. The 184 figure is explained
   as a `--ignore=tests/runtime` filter; the 229 figure is explained
   as the test count before the four metric-regression tests were
   added.
4. ✅ Every required final container-closure test actually executed
   and passed (including the two OCI-runtime-gated ones — both
   resolved to "ran" because podman is on PATH).
5. ✅ No skipped tests. Any skipif gates in the codebase did not fire.
6. ✅ No accidental test/config exclusion.
7. ✅ The +4 from 229 → 233 is identified as
   `tests/cache/test_per_run_metric_regression.py`'s four tests.

**Status: READY.**

The 50-repository gate is unblocked. Per the explicit closure
instruction, it is **not run here**.

— end of report —