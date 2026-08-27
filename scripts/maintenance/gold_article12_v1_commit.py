#!/usr/bin/env python3
"""Confirm a curated subset of LLM-judge-proposed ACCEPTs as
HUMAN-REVIEWED GOLD.

Source:  audit/2026-08-28-gold-bootstrap-proposals.json
Target:  agent_repository_audits rows with
            verdict       = 'gold'
            auditor_type  = 'human'
            auditor       = 'user:marcelo'
            audit_batch   = 'gold_article12_v1'

The script is idempotent: re-running it for the same audit_batch will
report existing gold rows for those repositories and exit cleanly
without creating duplicate audits.

Curated selection (26 repos, 9 categories, architectural diversity):

    coding_agent      (6)  mini-swe-agent, gptme, CoreCoder,
                            broccoli, CodeJury, AgentLoom
    agent_framework   (3)  PocketFlow, SuperAGI, nerve
    multi_agent       (4)  MetaGPT, nanobot, agent-framework, MassGen
    general_agent     (3)  AutoGPT, aiwaves-cn/agents, whenx
    browser_agent     (2)  browser-use, auto-browser
    computer_use_agent(2)  TuriX-CUA, home-generative-agent
    workflow_agent    (2)  FAROS, sparrow
    tool_using_agent  (3)  haystack, Vibe-Trading, open-agent-tools-coder
    other_agent       (1)  opensquilla

Selection criteria:
    * Architecturally distinct patterns (single-loop, multi-role,
      DAG, graph-of-nodes, parallel-voting, event-driven, microkernel).
    * Mix of mature (high stars) and minimal/reference implementations.
    * Different memory strategies (none, persistent, vector, structured).
    * Different tool-integration models (bash, MCP, Playwright, desktop,
      REST, custom protocol).
    * Spread across specialisations relevant to Article 12: coding,
      research, trading, browser, computer-use, IoT, document.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from compliance.db import session_scope
from compliance.models import AgentRepository, AgentRepositoryAudit


# Curated selection. Each tuple is (full_name, selection_rationale).
GOLD_ARTICLE12_V1: list[tuple[str, str]] = [
    # ── coding_agent (6) ────────────────────────────────────────────────
    ("SWE-agent/mini-swe-agent",
     "minimal reference: ~100-line coding agent, SWE-bench >74%, "
     "single ReAct loop over bash tool"),
    ("gptme/gptme",
     "mature terminal coding agent: tools, skills, MCP/ACP, "
     "sub-agents, autonomous loop, large user base"),
    ("he-yufeng/CoreCoder",
     "minimal didactic coding agent: ~1000 lines, file/shell tools, "
     "compacting, 103 tests — well-tested reference impl"),
    ("besimple-oss/broccoli",
     "production SDLC pipeline: Linear tickets → Claude/Codex → PRs "
     "via Cloud Run orchestration"),
    ("krishagarwal314/CodeJury",
     "two-judge code-review pattern: Planner/Dev/Jury with adversarial "
     "review before merge"),
    ("linora-u/AgentLoom",
     "YAML-app multi-agent runtime: typed Workers, evidence-aware TUI "
     "Studio, Skills system"),

    # ── agent_framework (3) ─────────────────────────────────────────────
    ("The-Pocket/PocketFlow",
     "graph-of-nodes abstraction spanning agents, multi-agent, RAG, "
     "workflow — minimal orchestrator kernel"),
    ("TransformerOptimus/SuperAGI",
     "mature multi-feature framework: tool/toolkit orchestration, "
     "agent management UI, cloud deployment"),
    ("ClickHouse/nerve",
     "self-hosted runtime with persistent memory, scheduled execution, "
     "Skills system, multi-channel delivery (web UI/Telegram)"),

    # ── multi_agent (4) ─────────────────────────────────────────────────
    ("FoundationAgents/MetaGPT",
     "canonical SOP-based software-company multi-agent: roles, message "
     "bus, established pattern with high adoption"),
    ("HKUDS/nanobot",
     "self-hosted personal agent: tool use, long-term memory, MCP, "
     "multi-agent delegation, workspace isolation"),
    ("microsoft/agent-framework",
     "Microsoft production framework: graph workflows, middleware, "
     "orchestration patterns, multi-language"),
    ("massgen/MassGen",
     "parallel-voting-consensus pattern: multiple frontier models "
     "refining in parallel, distinct deliberation model"),

    # ── general_agent (3) ───────────────────────────────────────────────
    ("Significant-Gravitas/AutoGPT",
     "foundational autonomous-agent platform: tool orchestration, "
     "deployment infrastructure, high adoption"),
    ("aiwaves-cn/agents",
     "self-evolving agents with symbolic back-propagation and prompt "
     "pipelines — distinct self-improvement architecture"),
    ("edmar/whenx",
     "event-driven Captain/Scout/Sentinel/Soldier architecture with "
     "observation-based monitoring — novel trigger pattern"),

    # ── browser_agent (2) ───────────────────────────────────────────────
    ("browser-use/browser-use",
     "canonical Python browser-agent framework: LLM-driven loop over "
     "Playwright, action registry, dominant adoption"),
    ("LvcidPsyche/auto-browser",
     "perception/action tools, approvals, audit trail, skill "
     "induction — production-safety-oriented control plane"),

    # ── computer_use_agent (2) ──────────────────────────────────────────
    ("TurixAI/TuriX-CUA",
     "real desktop actions with OSWorld benchmark results, "
     "open-source stack for computer-use agents"),
    ("goruck/home-generative-agent",
     "LangGraph agent inside Home Assistant: tool calls control real "
     "entities, write automations — embodied control loop"),

    # ── workflow_agent (2) ──────────────────────────────────────────────
    ("OpenNSWM-Lab/FAROS",
     "Blueprint-driven AutoResearch pipeline: idea/experiment/paper/"
     "review multi-stage workflow"),
    ("katanaml/sparrow",
     "multi-agent document intelligence with pluggable ML/LLM/VLM "
     "pipelines, REST orchestration"),

    # ── tool_using_agent (3) ─────────────────────────────────────────────
    ("deepset-ai/haystack",
     "production-grade Python orchestration framework: agents, "
     "pipelines, RAG, tool-using workflows — high maturity"),
    ("HKUDS/Vibe-Trading",
     "multi-agent trading framework: MCP adapter, kill-switch loop, "
     "broker integration, autonomous execution"),
    ("district-solutions/open-agent-tools-coder",
     "compressed-prompt-index source reuse: distinct memory pattern "
     "for tool-calling workflows"),

    # ── other_agent (1) ─────────────────────────────────────────────────
    ("opensquilla/opensquilla",
     "microkernel Python agent runtime: single turn loop with tool "
     "dispatch, model routing, persistent memory, sandbox — "
     "architecturally novel"),
]


def main() -> int:
    if len(GOLD_ARTICLE12_V1) < 25 or len(GOLD_ARTICLE12_V1) > 30:
        raise RuntimeError(
            f"selection has {len(GOLD_ARTICLE12_V1)} repos; "
            "spec requires 25-30"
        )

    with session_scope() as session:
        # Resolve full_name → repository_id.
        rows = session.execute(
            select(AgentRepository)
            .where(AgentRepository.full_name.in_(
                [name for name, _ in GOLD_ARTICLE12_V1]))
        ).scalars().all()
        repo_by_name = {r.full_name: r for r in rows}

        missing = [name for name, _ in GOLD_ARTICLE12_V1
                   if name not in repo_by_name]
        if missing:
            raise RuntimeError(
                f"missing in agent_repositories: {missing}"
            )

        # Check existing audits for this batch.
        existing = session.execute(
            select(AgentRepositoryAudit)
            .where(AgentRepositoryAudit.audit_batch == "gold_article12_v1")
        ).scalars().all()
        already_gold_names = {a.repository.full_name for a in existing}

        inserted = 0
        skipped = 0
        for name, rationale in GOLD_ARTICLE12_V1:
            repo = repo_by_name[name]
            if name in already_gold_names:
                print(f"  skip (already gold): {name}")
                skipped += 1
                continue
            audit = AgentRepositoryAudit(
                repository_id=repo.id,
                verdict="gold",
                auditor_type="human",
                auditor="user:marcelo",
                reason=rationale,
                audit_batch="gold_article12_v1",
            )
            session.add(audit)
            inserted += 1

        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            print(f"IntegrityError during flush: {exc}", file=sys.stderr)
            return 1

        # Print post-state.
        total_gold_v1 = session.execute(
            select(AgentRepositoryAudit)
            .where(AgentRepositoryAudit.audit_batch == "gold_article12_v1")
        ).scalars().all()

    print()
    print(f"audit_batch = gold_article12_v1")
    print(f"  target:    {len(GOLD_ARTICLE12_V1)} repos")
    print(f"  inserted:  {inserted}")
    print(f"  skipped:   {skipped} (already in this batch)")
    print(f"  total in batch: {len(total_gold_v1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
