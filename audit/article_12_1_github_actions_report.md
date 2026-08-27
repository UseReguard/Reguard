# Article 12(1) GitHub Actions Integration Report

Date: 2026-08-27
Requirement: `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING` v1.1.0
Runtime: compliance.pipeline 1.0.0

## Scope

Add GitHub Actions support to the existing Article 12(1) engine
WITHOUT changing:

- Article 12(1) legal logic
- adapter semantics
- provenance rules (SYSTEM_NATIVE / SYSTEM_STATE_EXPORTED_BY_HARNESS / HARNESS_GENERATED)
- result schema (evidence v2 / result v2)
- requirement test version (1.1.0)

The GitHub Actions path uses the **exact same core engine** as
local execution.

## Files changed / added

```
modified  src/compliance/pipeline/driver.py
modified  scripts/compliance-check.py
added     .github/workflows/compliance-article-12-1.yml
added     tests/pipeline/test_path_mode.py
added     audit/article_12_1_github_actions_report.md
```

## Driver refactor

`driver.py` now exposes two entry points that share one helper:

| Function | Mode | Clones? | Persists to DB? |
|---|---|---|---|
| `run_one(full_name, sha)` | clone mode (legacy local corpus) | yes | yes |
| `run_path_mode(repository_path, repository_full_name, repo_sha)` | path mode (GHA) | **NO** | optional |

Both call `_run_pipeline(target, requirement_id, repo_checkout, ...)`,
which runs the probe, collects evidence, evaluates the requirement,
and (optionally) persists.

Path mode **does NOT clone**. It verifies that the checkout HEAD
equals the requested SHA via `git rev-parse HEAD`, and refuses
to run otherwise. This preserves the reproducibility contract.

## CLI changes

`scripts/compliance-check.py` now supports:

```
python scripts/compliance-check.py \
  --repo OWNER/NAME \
  --sha SHA \
  [--repo-path DIR]              # path mode
  [--requirement ID]             # default: AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
  [--output FILE]                # write compliance-result.json
  [--persist]                    # also insert into compliance_runtime_runs
```

When `--output` is given, the CLI also creates an `evidence/`
sibling directory and writes one `evidence_<owner>_<name>.json`
per run. Both files are always written regardless of pass/fail.

If `--repo-path` is given but no adapter is registered for the
repo, the CLI emits `status=UNSUPPORTED` and exits with code 3
(graceful, no traceback). If the SHA mismatches the checkout, it
emits `status=ERROR` and exits with code 4.

## Exit-code contract

| RunStatus | Exit code |
|---|---|
| PASS | 0 |
| FAIL | 1 |
| UNKNOWN | 2 |
| UNSUPPORTED | 3 |
| ERROR | 4 |

`UNKNOWN` and `UNSUPPORTED` are **never** collapsed into `FAIL`.
This is enforced by `EXIT_CODE` in the CLI and by an explicit
test (`test_cli_exit_code_table_does_not_collapse_unknown_into_fail`).

## GitHub workflow

`.github/workflows/compliance-article-12-1.yml`:

- Trigger: `workflow_dispatch` only (no PR / push auto-trigger yet)
- Inputs: `repository`, `sha` — both required
- Permissions: `contents: read` (no write permissions)
- Steps:
  1. `actions/checkout@v4` for the compliance-tool repo at `compliance-tool/`
  2. `actions/checkout@v4` for the target repo at the exact SHA into `target/`
  3. `actions/setup-python@v5` with Python 3.12
  4. Set `PYTHONPATH` to include `compliance-tool/src`
  5. Run `compliance-check.py --repo-path $GITHUB_WORKSPACE/target --output compliance-result.json`
  6. Always (`if: always()`) upload:
     - `compliance-result.json` as artifact
     - `evidence/` directory as artifact
  7. Always (`if: always()`) write a job summary table to `$GITHUB_STEP_SUMMARY` with:
     Repository, SHA, Requirement, Status, Adapter, Adapter version,
     Requirement version, Runtime version, Event count,
     Evidence origins, Duration.

The workflow does not embed any target-repo-specific logic; the
target comes from the workflow_dispatch inputs.

The workflow does NOT pass `GITHUB_TOKEN` to the probe environment.

## Tests added

`tests/pipeline/test_path_mode.py` — 13 cases:

| Test | Asserts |
|---|---|
| `test_path_mode_uses_checkout_does_not_clone` | path mode raises KeyError when adapter is missing (without cloning) |
| `test_path_mode_refuses_wrong_sha` | SHA mismatch -> RuntimeError before probe runs |
| `test_path_mode_records_exact_sha` | RepositoryTarget.sha is propagated exactly |
| `test_cli_exit_code_pass` | RunStatus.PASS -> 0 |
| `test_cli_exit_code_fail` | RunStatus.FAIL -> 1 |
| `test_cli_exit_code_unknown` | RunStatus.UNKNOWN -> 2 |
| `test_cli_exit_code_unsupported` | RunStatus.UNSUPPORTED -> 3 |
| `test_cli_exit_code_error` | RunStatus.ERROR -> 4 |
| `test_cli_exit_code_table_does_not_collapse_unknown_into_fail` | defensive: UNKNOWN/UNSUPPORTED distinct from FAIL |
| `test_cli_subprocess_unknown_adapter_yields_unsupported_exit_3` | full subprocess flow: unknown adapter -> exit 3 + result file |
| `test_cli_writes_result_file` | --output produces a JSON file even on UNSUPPORTED |
| `test_repro_equivalence_synthetic_evidence` | same evidence -> same result (local == path mode) |
| `test_repro_equivalence_origins_preserved_through_pipeline` | per-event origin survives the pipeline untouched |

## Total test result

```
============================== 28 passed in 0.21s ==============================
```

- 15 existing Article 12(1) tests still pass.
- 13 new path-mode / exit-code / repro tests pass.

## Local path-mode integration check (mini-swe-agent)

To verify the path-mode flow that GitHub Actions will use, we ran
the CLI locally against a checked-out `SWE-agent/mini-swe-agent` at
SHA `25941c89cfbc91eb40b3f8756348c91d9977d57e`:

```
$ python3 scripts/compliance-check.py \
    --repo SWE-agent/mini-swe-agent \
    --sha 25941c89cfbc91eb40b3f8756348c91d9977d57e \
    --repo-path /tmp/.../target \
    --output /tmp/.../compliance-result.json

{"adapter_name": "minisweagent", "adapter_version": "1.1.0",
 "duration_seconds": 21.909, "event_count": 5,
 "evidence_origins": ["SYSTEM_NATIVE"],
 "status": "PASS", "reason": "all checks passed",
 ...}
exit_code=0

$ ls /tmp/.../evidence/
evidence_SWE-agent_mini-swe-agent.json
```

Result: PASS, exit 0, evidence file written, full schema v1 result
file written. The five Article 12(1) checks all pass with SYSTEM_NATIVE
provenance.

## GitHub Actions execution

**Not executed in this environment.** This sandbox has no access
to `gh` or to a remote runner. The workflow file is structurally
valid and the path-mode entry point it invokes has been verified
locally. The exact same `compliance-check.py` invocation that GHA
will use produced PASS / exit 0 against the same SHA that GHA
will check out.

The remaining step — actually triggering `workflow_dispatch` in
the remote repository and downloading the artifacts — requires a
human in front of the GitHub UI or a `gh` CLI. The expected
result for each of the three initial targets:

| Target | SHA | Expected status | Expected exit |
|---|---|---|---|
| SWE-agent/mini-swe-agent | `25941c89cfbc91eb40b3f8756348c91d9977d57e` | PASS | 0 |
| he-yufeng/CoreCoder | `a03ef36412e432fc49d972d4007b36ce44ec5d9a` | PASS | 0 |
| HKUDS/nanobot | `4d204ba077a86dc42225c16f8f90032013ea1969` | PASS | 0 |

If GHA produces a different result, treat that as a
reproducibility defect and investigate before expanding scope.

## Environment-specific differences discovered

- The local sandbox uses Python 3.14; GHA will use Python 3.12
  per the workflow's `setup-python` step. Both code paths use the
  standard library only at the top of the orchestration code; the
  only third-party packages the runtime needs are pulled in by
  `pip install -e .` of the target repo, not by the engine itself.
- The sandbox has GnuTLS-flavoured git; GHA uses the same. No
  protocol differences expected.

## What was NOT built

- GitHub App
- PR Check Runs
- annotations (e.g. `::error file=...`)
- marketplace Action
- reusable workflow
- matrix across all 26 repos
- scheduled corpus scans
- more legal requirements

## Verdict

The Article 12(1) engine is ready for GitHub Actions:

- 28/28 synthetic tests pass.
- The CLI exposes both clone-mode and path-mode entry points.
- Path mode verifies the checkout SHA matches the request.
- Exit codes are deterministic and documented.
- The workflow is structurally valid and does not embed
  target-repo logic.
- Local path-mode integration against mini-swe-agent produced
  PASS / exit 0.

Stop after Article 12(1) works reproducibly in GitHub Actions.