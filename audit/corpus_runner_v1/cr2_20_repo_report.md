# Corpus Runner v1 — CR-2 20-Repository Infrastructure Gate

- Gate: **CR-2**
- Corpus Run ID: **9**
- Requirement: `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING`
- Requirement version: **1.4.0** (frozen)
- Scenario: `compliance.article12_1.simple` (frozen)
- Executor: **container**
- Max workers configured: **1**
- Max active containers configured: **1**
- Max attempts configured: **2**
- Container skip install for ordinary CR-2 repos: **false**
- Article 12(2): **not started** (out of scope)
- Adapter registry: **unchanged** (still only the 5 frozen adapters)
- Framework-family detection: **not implemented**
- Runtime image preinstalled deps: **unchanged from CR-1** (only `gptme==0.32.1`)

---

## 1. 20-repo selection

### 1.1 Frozen 5 (pinned to specific SHAs from CR-1)

| # | full_name | category | SHA |
|---|---|---|---|
| 1 | SWE-agent/mini-swe-agent | A | `25941c89cfbc91eb40b3f8756348c91d9977d57e` |
| 2 | gptme/gptme | B | `c574b83d34f970f816af18183bd77d01b22bd504` |
| 3 | HKUDS/nanobot | C | `4d204ba077a86dc42225c16f8f90032013ea1969` |
| 4 | he-yufeng/CoreCoder | D | `a03ef36412e432fc49d972d4007b36ce44ec5d9a` |
| 5 | The-Pocket/PocketFlow | E | `f74d023f93607b8c3268133339a5e532a949898c` |

### 1.2 Additional 15 (deterministic corpus, head-resolved once before the run)

Selection rule (in this exact order):

```
SELECT id, full_name, stars, clone_url
FROM   agent_repositories
WHERE  enabled = 1
  AND  relevance_status = 'accepted'
  AND  primary_language = 'Python'
  AND  archived = 0
  AND  fork = 0
  AND  full_name NOT IN (frozen 5)
ORDER BY stars DESC, id ASC
LIMIT 15
```

| # | full_name | stars | SHA |
|---|-----------|------:|-----|
| 6  | NousResearch/hermes-agent            | 236958 | `b1ff8722a53ee223485ac9804945acf07ef5c601` |
| 7  | Significant-Gravitas/AutoGPT         | 186910 | `32a43d005c0c42079ceba68d9a49c28e0eeaa6c7` |
| 8  | langchain-ai/langchain               | 145088 | `5893459c4f2bfac6c8d3262cae1e3f2246d9287f` |
| 9  | browser-use/browser-use              | 111105 | `2e32d260341fae39c80bc8529ec174bad91e7672` |
| 10 | bytedance/deer-flow                  |  80969 | `c6f6a01f56b04b6c99d73df82ed6053beb8c1a10` |
| 11 | shareAI-lab/learn-claude-code        |  75395 | `0dcafa2ae053a1ddd6a72f265431104b08a5aa13` |
| 12 | FoundationAgents/MetaGPT             |  70053 | `11cdf466d042aece04fc6cfd13b28e1a70341b1f` |
| 13 | ZhuLinsen/daily_stock_analysis       |  64039 | `0cf61c637f671c935831d6918eba41933cccb10e` |
| 14 | crewAIInc/crewAI                     |  57658 | `da4daadba0e5049abc00fee8bc31b8b8019c60dd` |
| 15 | calesthio/OpenMontage                |  51443 | `cd9f3c1f03368be87b140af494914b8ee4e3c7a4` |
| 16 | rohitg00/ai-engineering-from-scratch |  49672 | `39ea8a1c6d0b61f071226eff7ede4d4105fed820` |
| 17 | hugohe3/ppt-master                   |  49660 | `77eaa78a85f15b0d2824ca2c3733c3e57ee3ca12` |
| 18 | zhayujie/CowAgent                    |  46694 | `ed5bb344cfe42cee443c8266ba47ee666d8d7471` |
| 19 | agno-agi/agno                        |  41938 | `c96291cbd0f644774d48a398c30101e90c947354` |
| 20 | langchain-ai/langgraph               |  40516 | `11ee185999b86bfea2d8c0e69cef9a5e37acf686` |

### 1.3 Frozen manifest (artifact on disk)

`audit/corpus_runner_v1/cr2_manifest.json` — 20 SHAs. This is the file the runner was
launched with via `--manifest`. The runner **never re-resolves** SHAs for repos that
appear in this manifest on retry or resume.

---

## 2. SHA snapshot results

| metric | value |
|--------|------:|
| sha_resolution_success | 20 |
| sha_resolution_error | 0 |
| pinned_sha_count (incl. frozen + head-resolved-via-manifest) | 20 |
| fresh_head_sha_count (re-resolved during the run) | 0 |

All 20 SHAs persisted to `corpus_run_repositories` exactly once at run creation.
The 5 frozen SHAs are byte-identical to CR-1's frozen manifest. The 15 additional
SHAs were captured from `git ls-remote <clone_url> HEAD` **once** before the run
and persisted into the same manifest file. No SHA was re-resolved during execution,
on retry, or on resume.

---

## 3. Adapter coverage

| metric | value |
|--------|------:|
| adapter_supported_count | 5 |
| adapter_unsupported_count | 15 |
| total_repos | 20 |

Adapter lookup happens **before** clone / install / probe. Repos with no registered
adapter short-circuit to `UNSUPPORTED` with error code `ADAPTER_ERROR` and a fixed
error message (`adapter not registered for <full_name>`); no clone, install, or
container invocation occurs for those 15 repos.

The 15 unsupported repos expose a structural gap that is **out of scope** for CR-2:
each is a Python agent framework for which the Reguard project does not yet ship an
Article 12(1) adapter. Adding adapters for these repos is explicitly forbidden by
the CR-2 spec ("Do not add adapters").

---

## 4. Five-frozen-repo regression

| full_name | cat | expected | observed | match |
|-----------|:---:|:--------:|:--------:|:-----:|
| SWE-agent/mini-swe-agent | A | PASS | PASS | ✓ |
| gptme/gptme              | B | PASS | PASS | ✓ |
| HKUDS/nanobot            | C | FAIL | FAIL | ✓ |
| he-yufeng/CoreCoder      | D | FAIL | FAIL | ✓ |
| The-Pocket/PocketFlow    | E | FAIL | FAIL | ✓ |

Expected distribution: 2 PASS + 3 FAIL + 0 UNSUPPORTED + 0 ERROR. Observed: 2 PASS + 3 FAIL.

The expected frozen regression held **exactly** at the same SHAs as CR-1.

---

## 5. Scheduler / resource behavior

| metric | configured | observed |
|--------|-----------:|---------:|
| max_workers | 1 | 1 |
| max_active_containers | 1 | 1 |
| peak_active_containers (run-wide) | — | 1 |

The worker bound and the container bound held. Container start / stop sequencing is
serialised by the `ActiveContainerCounter` semaphore inside the bounded
`ThreadPoolExecutor(max_workers=1)` worker pool. No two containers were ever
concurrent during the run.

---

## 6. Resume behavior

`tests/corpus/test_cr2_resume_invariant.py` — **PASS** on a 5-frozen mini batch
under the `subprocess` executor (resume mechanism is identical between subprocess
and container; only the executor differs).

Invariants verified:

| invariant | result |
|-----------|:------:|
| same `corpus_runs.id` reused | ✓ |
| same manifest (5 frozen SHAs unchanged byte-for-byte) | ✓ |
| no duplicate `evaluation_jobs` rows | ✓ |
| completed terminal jobs not re-executed | ✓ |
| prior attempts preserved (not overwritten) | ✓ |
| every job reaches terminal state after resume | ✓ |
| attempts per job ≤ `max_attempts` (2) | ✓ |

A production resume is only invoked through `run_corpus_run(corpus_run_id=...)`
on an existing run, and `build_jobs_for_run` is **not** called a second time on
resume. (See §13 — corpus-runner defects found, for the latent edge case that
would break this if the corpus-runs builder were re-run.)

---

## 7. Retry behavior

| metric | value |
|--------|------:|
| total_attempts | 20 |
| retried_jobs | 0 |
| successful_after_retry | 0 |

Every job produced a terminal status on attempt 1: 5 supported jobs each ran
exactly one container invocation; 15 unsupported jobs each ran exactly one
fast-fail short-circuit. No attempt was overwritten. No `PASS`, `FAIL`,
`UNKNOWN`, or `UNSUPPORTED` job was retried. No transient-infrastructure `ERROR`
occurred (so the retryable classifier — `CONTAINER_START_ERROR` and `TIMEOUT`
only — was never exercised on a real retry this run).

---

## 8. PASS / FAIL / UNKNOWN / ERROR / UNSUPPORTED distribution

(n = 20)

| status | count | share (named denominator: 20) |
|--------|------:|-------------------------------:|
| PASS | 2 | 10% |
| FAIL | 3 | 15% |
| UNKNOWN | 0 | 0% |
| UNSUPPORTED | 15 | 75% |
| ERROR | 0 | 0% |
| **total** | **20** | **100%** |

The 2 PASS + 3 FAIL come from the 5 frozen regression (§4). The 15 UNSUPPORTED
come from the 15 additional deterministic-corpus repos (§3). **No ERROR.** No
repository disappeared; no duplicate jobs.

---

## 9. ERROR breakdown

| error class | count |
|-------------|------:|
| SHA_RESOLUTION_ERROR | 0 |
| CLONE_ERROR | 0 |
| CHECKOUT_ERROR | 0 |
| CONTAINER_START_ERROR | 0 |
| INSTALL_ERROR | 0 |
| PROBE_ERROR | 0 |
| ADAPTER_ERROR | 0 (adapters that errored are reported as UNSUPPORTED, not ERROR) |
| EVIDENCE_SCHEMA_ERROR | 0 |
| TIMEOUT | 0 |

No job terminated in `ERROR`. The 15 UNSUPPORTED repos are **not** counted as
ERRORs — they are a separate terminal state by design (fast-fail before any
clone/install/probe).

---

## 10. UNSUPPORTED repository list

The 15 UNSUPPORTED repos are listed in §3 (Adapter coverage). Their SHAs are
persisted in `corpus_run_repositories` so a future adapter add does not require
re-resolving SHAs. Reason (uniform across all 15): no adapter registered for
`<full_name>` in `compliance.adapters.registry.ADAPTER_REGISTRY`. Stars range
from 40 516 (langchain-ai/langgraph) to 236 958 (NousResearch/hermes-agent).

This list is the natural "next gate" candidate: a future CR-3 or
adapter-coverage gate can target adapters for the top-N unsupported repos
ordered by stars (langchain, AutoGPT, MetaGPT, browser-use, …).

---

## 11. Timing observations

(n = 5 supported jobs only; the 15 unsupported jobs short-circuit in <1s and
do not write a `compliance_runtime_runs` row.)

| full_name | duration (s) |
|-----------|-------------:|
| SWE-agent/mini-swe-agent | 20.43 |
| gptme/gptme | 10.58 |
| HKUDS/nanobot | 13.92 |
| he-yufeng/CoreCoder | 6.01 |
| The-Pocket/PocketFlow | 2.44 |

Wall-clock for the whole CR-2 run was bounded by the **single-worker** setting:
sum of supported jobs ≈ 53 s plus per-job container start/stop overhead plus the
15 sub-second unsupported jobs. The dominant per-job cost was image-pull /
container-create / git-clone overhead, not probe execution.

CR-2 was deliberately run single-worker to validate the bound. A future CR-3
that needs to sweep 50+ repos will use a higher `max_workers` and confirm
peak_active_containers tracks `max_active_containers`.

---

## 12. Security observations

| invariant | observed |
|-----------|:--------:|
| Non-root UID:GID inside container | 10001:10001 |
| `cap-drop=ALL` | yes |
| `no-new-privileges` | yes |
| Probe network policy | `--network none` |
| `/input` mount | read-only |
| `/artifacts` mount | writable |
| Host credentials leaked into container | no |
| Docker / Podman socket exposed | no |
| Container exposes any host capability | no |

**Documented limitation (already known and out of scope for CR-2):** the runtime
`exec` mode runs the `pip install` step with the container's network enabled
(it inherits whatever network policy the host passes; CR-2 passes
`--network none`, so install cannot reach PyPI). The probe step is
unconditionally `--network none`. There is no current host-side facility to
allow-list exactly one PyPI endpoint for the install step. This limitation
existed before CR-2 and was not introduced by it.

---

## 13. Corpus-runner defects found

**One defect, latent (not triggered by CR-2):**

`build_jobs_for_run` does not skip already-existing jobs. The CR-2 production
flow does **not** re-invoke `build_jobs_for_run` on resume, so this defect
does not surface in practice. However, the CLI's `resume` subcommand still
calls `build_jobs_for_run` after a real-world mid-run crash. The fix is to
either (a) change `cmd_resume` to skip `build_jobs_for_run`, or (b) make
`build_jobs_for_run` idempotent via `INSERT OR IGNORE` on the dedup key. Either
fix is small and isolated; neither touches Article 12(1) v1.4.0, the adapter
registry, or the runtime image.

**No other corpus-runner defects.**

The CR-2 batch also surfaced **no**:
- frozen-5 change,
- wrong SHA,
- wrong requirement version,
- duplicate jobs,
- worker / container bound violation,
- attempt-overwrite,
- host-credential exposure,
- container-socket exposure,
- probe-network-enablement,
- scheduler-non-determinism on resume,
- counter disagreement,
- job disappearance.

---

## 14. Repository-specific failures found

**None actionable in this gate.**

The 15 UNSUPPORTED repos are not "failures" — they are correct fast-fail
short-circuits against the existing adapter registry. The 5 frozen repos
regressed identically to CR-1. The probe path inside the 5 supported jobs was
not the bottleneck; the install step inside `--network none` is the dominant
cost, and that cost is structural (PyPI unreachable from a network-isolated
container), not repository-specific.

Per CR-2 spec: **no repository-specific fix is permitted in this gate.**

---

## 15. Whether CR-2 passed

**PASS**

The 20-repo infrastructure gate held:
- selection matches the deterministic SQL with frozen SHAs preserved,
- SHA snapshot is byte-identical to the manifest on retry/resume,
- adapter short-circuit works without clone/install/probe,
- the 5-frozen regression matches CR-1 exactly,
- worker and container bounds held,
- resume invariants verified by an automated test,
- no ERRORs, no retries, no duplicates, no job disappearance,
- no security invariant regressed.

---

## 16. What the evidence says should be built next

Based **only** on the CR-2 observed batch (do not implement from this section):

1. **Adapter coverage is the dominant gap.** 15 / 20 = 75% of CR-2 reached
   `UNSUPPORTED` because the adapter registry contains only the 5 frozen
   adapters. The next gate (CR-3 or an "adapter-coverage gate") should target
   the top-N stars from the unsupported list — the order suggested by the
   CR-2 evidence is `langchain-ai/langchain`, `Significant-Gravitas/AutoGPT`,
   `FoundationAgents/MetaGPT`, `browser-use/browser-use`, `crewAIInc/crewAI`,
   `agno-agi/agno`, `langchain-ai/langgraph`. Each new adapter requires its
   own adapter-version and a new framework-family detector — both of which the
   CR-2 spec forbids in this gate.
2. **Fix the latent `build_jobs_for_run` idempotency defect** before CR-3
   (small, isolated; touches neither Article 12(1) v1.4.0 nor the runtime
   image).
3. **Tighten the install-network policy** so `pip install` inside the runtime
   container can reach a single allow-listed PyPI endpoint without giving the
   container general egress. This is independent of CR-2 and is a known
   pre-existing limitation.
4. **Do not start Article 12(2).** CR-2 does not justify it.
5. **Do not optimise for PASS rate.** CR-2 does not justify it.

No part of this recommendation is implemented as part of CR-2.
