"""compliance — EU AI compliance assessment tool.

Domains
-------
legal          Canonical laws, parsing, ingestion.
corpus         GitHub repository discovery + gold sets.
pipeline       Clone → SHA → runtime → result orchestration.
adapters       Per-repo adapters (mini-swe-agent, nanobot, …).
requirements   Deterministic legal assertions (AI_ACT_12_1, AI_ACT_14_4_e, …).

The shared DB, ORM models, and configuration live at the package root.
"""