# CR-2 addendum — paste into `Reguard/Study/Corpus Runner v1 Implemented.md`

> **NOTE — MANUAL PASTE REQUIRED.** The Obsidian vault this session can
> write to via MCP does not contain the `Reguard/Study/` subtree. Paste the
> section below into `Reguard/Study/Corpus Runner v1 Implemented.md` in the
> Obsidian vault that holds your study notes. Do not modify the frozen
> Article 12(1) note.

---

## CR-2 — 20-repository infrastructure gate (2026-08-29)

Gate status: **PASS**.

Selection: 5 frozen (PocketFlow, mini-swe-agent, gptme, nanobot, CoreCoder) +
15 deterministic-corpus repos ordered by `stars DESC` excluding the 5 frozen.
SHAs frozen once before the run; the runner never re-resolves on retry/resume.

Container executor, `max_workers=1`, `max_active_containers=1`,
`max_attempts=2`, no `container_skip_install` for ordinary CR-2 repos.

Distribution (n=20): PASS=2, FAIL=3, UNSUPPORTED=15, ERROR=0.

Five-frozen regression: A→PASS, B→PASS, C→FAIL, D→FAIL, E→FAIL — matches CR-1
exactly.

Resume invariants verified by `tests/corpus/test_cr2_resume_invariant.py` —
same manifest, no duplicate `evaluation_jobs`, completed jobs not re-executed,
prior attempts preserved.

No corpus-runner defects triggered by the run. One latent defect surfaced in
review: `build_jobs_for_run` is not idempotent (does not skip already-existing
jobs). The CR-2 production flow does not re-invoke it on resume, so the defect
is dormant; it should be fixed before CR-3. The fix is small and isolated
(does not touch Article 12(1) v1.4.0, the adapter registry, or the runtime
image).

What CR-2 says to build next (do not implement from this note):

1. **Adapter coverage for the top-N unsupported Python agent repos.** 15 of
   the 20 CR-2 repos short-circuited to UNSUPPORTED because no adapter is
   registered for them in `compliance.adapters.registry.ADAPTER_REGISTRY`.
   Suggested priority by observed stars: `langchain-ai/langchain`,
   `Significant-Gravitas/AutoGPT`, `FoundationAgents/MetaGPT`,
   `browser-use/browser-use`, `crewAIInc/crewAI`, `agno-agi/agno`,
   `langchain-ai/langgraph`. Each new adapter implies a new framework-family
   detector — both are explicitly out of scope for CR-2.
2. **Make `build_jobs_for_run` idempotent** (or skip it in `cmd_resume`).
3. **Allow-list exactly one PyPI endpoint for the install step** (closes the
   pre-existing SECURITY_LIMITATION_INSTALL_NETWORK).
4. Do not start Article 12(2). Do not optimise for PASS rate.

Artifacts:

- `audit/corpus_runner_v1/cr2_manifest.json` — frozen 20-SHA manifest
- `audit/corpus_runner_v1/cr2_20_repo_report.md` — full report
- `audit/corpus_runner_v1/cr2_20_repo_summary.json` — machine-readable summary
- `tests/corpus/test_cr2_resume_invariant.py` — resume invariant test (PASS)

CR-2 is the **final** infrastructure gate for Corpus Runner v1. No further
scaling or expansion is part of this milestone.
