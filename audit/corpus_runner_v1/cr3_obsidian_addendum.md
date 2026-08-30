# CR-3 addendum — paste into `Reguard/Study/Corpus Runner v1 Implemented.md`

This is a self-contained section to paste **below** the existing
CR-2 / v1.1.1 closure sections in
`Reguard/Study/Corpus Runner v1 Implemented.md`. **Do not modify
the frozen Article 12(1) note** above it.

---

## 50-repository control-plane scale gate (CR-3)

**Date:** 2026-08-29
**CorpusRun ID:** 11
**Source artifacts:**

- `audit/corpus_runner_v1/cr3_50_repo_manifest.json`
- `audit/corpus_runner_v1/cr3_50_repo_summary.json`
- `audit/corpus_runner_v1/cr3_50_repo_report.md`

### What it did

Selected 50 repos deterministically (frozen five first, 45 by
`stars DESC, id ASC` against `agent_repositories`), pinned the
frozen five to their historical SHAs, resolved the other 45 via
`git ls-remote HEAD` with 40-hex validation, and ran the resulting
fresh `corpus_run` end-to-end with `executor=container`,
`max_workers=1`, `max_attempts=2`. SIGTERM-ed the runner cleanly
after 13 terminal jobs, then resumed on the same `corpus_run_id`
to drive the remaining 37.

### Key results

- **Selection:** 50 rows; 5 pinned, 44 resolved on first attempt,
  1 transient timeout (`NousResearch/hermes-agent`) → classified as
  `SHA_RESOLUTION_ERROR` (a real, surfaced outcome, not silently
  dropped).
- **Frozen-five regression:** all five held their expected
  `compliance_status` (`mini-swe-agent` PASS, `gptme` PASS,
  `nanobot` FAIL, `CoreCoder` FAIL, `PocketFlow` FAIL) and their
  pinned SHAs.
- **Job construction idempotence:** `build_jobs_for_run` called
  three times in a row returned 50 logical jobs each; no duplicate
  rows.
- **Interrupt/resume:** SIGTERM at 13 terminals left the
  manifest, frozen SHAs, and 13 completed jobs unchanged. The same
  `corpus_run_id` resumed only the 37 pending jobs to completion.
- **Terminal coverage:** 50 selected, 50 terminal, sum=50.
  Distribution: `PASS=2 FAIL=3 UNSUPPORTED=44 ERROR=1 SKIPPED=0`.
  Only the ERROR (1) is the `SHA_RESOLUTION_ERROR` mentioned above.
- **Source-cache:** 5 entries on disk (only the frozen five actually
  fetched), 478,849,255 bytes total, 0 orphans.
- **Workspace:** 5 created, 5 destroyed, 0 orphans, 0
  cleanup failures.
- **Cache-GC dry-run:** 5 entries considered, 0 protected, 0
  reclaimable (within configured 8 GiB bound, no eviction needed).
- **Workspace-janitor dry-run:** 0 stale workspaces.
- **Tests:** 233 collected, 233 passed (no test delta from the
  gate).

### Constraints honoured

Did NOT run the 50-repository gate as compliance validation; it
measured control-plane behaviour only. Did NOT add adapters,
framework-family detection, Article 12(2), dependency caching,
concurrency increase, or PASS-rate optimisation. Did NOT inspect
unsupported source.

### Known real-world transient

`git ls-remote HEAD` for `NousResearch/hermes-agent` timed out at
30 s on the run-creation call (it resolves successfully on retry,
with a different HEAD). The runner surfaced this as
`SHA_RESOLUTION_ERROR` rather than silently discarding it. This is
the desired behaviour per the v1.1.1 readiness audit.

### Readiness for the next scale step

- **READY** for the next control-plane scale step (e.g. manifest
  rows to 100).
- **NOT** ready to claim `100-repo compliance validation` —
  execution coverage is still bounded by the adapter set (5 repos
  have adapters).

— end of CR-3 addendum —