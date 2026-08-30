"""Corpus Runner v1 — minimal orchestration layer.

This package adds bounded in-process batch evaluation against the
existing compliance pipeline. It does not change the frozen Article
12(1) v1.4.0 requirement semantics; it persists orchestration
metadata (`corpus_runs`, `corpus_run_repositories`, `evaluation_jobs`,
`evaluation_attempts`) alongside the existing
`compliance_runtime_runs` deterministic-result table.

Scope for Corpus Runner v1:

  * database-driven repository selection,
  * frozen SHA snapshot before execution,
  * bounded in-process worker pool,
  * explicit retry classifier,
  * capability-declared scenario eligibility,
  * resumability without re-resolving SHAs,
  * machine-readable error classes for infrastructure diagnostics.

Out of scope:

  * framework-family detection,
  * evidence sharing across requirements,
  * install / repo caches,
  * external queues,
  * multi-host scheduling,
  * additional adapters,
  * Article 12(2).

v1.1 additions (architecture: audit/corpus_runner_v1/ephemeral_execution_architecture.md):

  * immutable bare-git source cache (class B),
  * ephemeral per-attempt workspace (class C),
  * automatic workspace cleanup on terminal completion,
  * schema-additive missing/error reason fields
    (`missing_capability`, `missing_facts`),
  * schema-additive execution/evaluation separation
    (`requirement_evaluations`, `execution_artifacts`).

Still out of scope in v1.1:

  * framework-family detection,
  * full observer rewrite,
  * multi-requirement execution reuse (table is created; consumption is not),
  * sophisticated dependency build cache,
  * external workers,
  * Article 12(2).
"""
