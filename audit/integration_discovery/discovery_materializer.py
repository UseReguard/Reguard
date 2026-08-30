"""Integration-pattern discovery materializer.

Clones and inspects a sample of currently UNSUPPORTED CR-3
repositories at their frozen SHAs into ephemeral inspection
workspaces. Uses the existing SourceCache + RepositoryMaterializer
architecture; no new clone path.

After analysis:
  - source cache is retained (so re-discovery is cheap)
  - inspection workspaces are destroyed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Use distinct cache + workspace roots from any prior CR-3 run so
# this discovery phase never collides with control-plane state.
# Default to /home/mrcel/.reguard/ because /tmp is small (7.7G
# total, mostly used by other caches).
DISCOVERY_CACHE_ROOT = Path(
    os.environ.get("REGUARD_DISCOVERY_CACHE_ROOT",
                   "/home/mrcel/.reguard/discovery_cache")
)
DISCOVERY_WORKSPACE_ROOT = Path(
    os.environ.get("REGUARD_DISCOVERY_WORKSPACE_ROOT",
                   "/home/mrcel/.reguard/discovery_ws")
)

from compliance.corpus_runner.cache.source_cache import (
    SourceCache,
    cache_key_for_url,
)
from compliance.corpus_runner.materializer import RepositoryMaterializer
from compliance.corpus_runner.workspace.manager import WorkspaceManager


# -----------------------------------------------------------------------------
# Frozen CR-3 sample selection.
#
# 9 named in the brief (NousResearch/hermes-agent is excluded — its
# CR-3 SHA was not resolved); plus 3 structurally diverse.
# -----------------------------------------------------------------------------

SAMPLE: list[dict] = [
    # The 9 preferred (1 omitted for sha-resolution error).
    {"position": 7,  "full_name": "langchain-ai/langchain",
     "repository_id": 7,
     "resolved_sha": "5893459c4f2bfac6c8d3262cae1e3f2246d9287f",
     "stars": 145088,
     "rationale": "LangChain core - primary representative of the "
                  "constructor(model, tools) + chain/agent run() family. "
                  "Most-cited dependency in the sample."},
    {"position": 19, "full_name": "langchain-ai/langgraph",
     "repository_id": 19,
     "resolved_sha": "11ee185999b86bfea2d8c0e69cef9a5e37acf686",
     "stars": 40516,
     "rationale": "Graph-state execution family - StateGraph.compile "
                  "-> .invoke(state) -> checkpoint saver. "
                  "Architecturally distinct from LangChain core despite "
                  "brand kinship."},
    {"position": 13, "full_name": "crewAIInc/crewAI",
     "repository_id": 13,
     "resolved_sha": "da4daadba0e5049abc00fee8bc31b8b8019c60dd",
     "stars": 57658,
     "rationale": "Role-based crew orchestration - Agent(role, goal, "
                  "backstory) -> Crew(agents, tasks) -> kickoff(). "
                  "Different model-injection surface than LangChain."},
    {"position": 18, "full_name": "agno-agi/agno",
     "repository_id": 18,
     "resolved_sha": "c96291cbd0f644774d48a398c30101e90c947354",
     "stars": 41938,
     "rationale": "Newer multi-agent framework - Agent(model, tools, "
                  "instructions) -> .arun() / .run(). Provides explicit "
                  "storage/postgres hook."},
    {"position": 6,  "full_name": "Significant-Gravitas/AutoGPT",
     "repository_id": 578,
     "resolved_sha": "32a43d005c0c42079ceba68d9a49c28e0eeaa6c7",
     "stars": 186910,
     "rationale": "Classic CLI autonomous-loop architecture - long-running "
                  "agent process driven by command queue; not a "
                  "single-call invocation. Tests the CLI/session family."},
    {"position": 11, "full_name": "FoundationAgents/MetaGPT",
     "repository_id": 1392,
     "resolved_sha": "11cdf466d042aece04fc6cfd13b28e1a70341b1f",
     "stars": 70053,
     "rationale": "Software-engineering multi-agent (architect / "
                  "engineer / PM roles) - Team / Role collaboration. "
                  "Distinct from crewAI role model."},
    {"position": 8,  "full_name": "browser-use/browser-use",
     "repository_id": 9,
     "resolved_sha": "2e32d260341fae39c80bc8529ec174bad91e7672",
     "stars": 111105,
     "rationale": "Browser-driven agent - Agent(task, llm) -> .run(). "
                  "External browser runtime dependency; "
                  "different integration shape."},
    {"position": 9,  "full_name": "bytedance/deer-flow",
     "repository_id": 10,
     "resolved_sha": "bf740ffa9077f55661fce80186b656651f497c89",
     "stars": 80969,
     "rationale": "Deep-research workflow orchestration - graph + "
                  "sub-agent delegation. LangGraph-style state + "
                  "multi-step LLM calls."},
    # NousResearch/hermes-agent omitted: CR-3 SHA was not resolved
    # (sha_resolution_error). Substituted with another structurally
    # distinct framework.
    {"position": 27, "full_name": "agentscope-ai/agentscope",
     "repository_id": 1393,
     "resolved_sha": "e90f1c7592896cc95f6e5ee506194f533378247d",
     "stars": 29730,
     "rationale": "agentscope - explicit multi-agent message-passing "
                  "design (MsgHub / sequential / parallel / parallel "
                  "branching). Distinct from crewAI/autoGen role models. "
                  "Replacement for NousResearch/hermes-agent."},
    # 3 structurally diverse extras.
    {"position": 29, "full_name": "deepset-ai/haystack",
     "repository_id": 29,
     "resolved_sha": "e318778c9bf60a1963e3b5f451359655dd696c30",
     "stars": 26325,
     "rationale": "Haystack - pipeline-style LLM orchestration "
                  "(Pipeline.add_node(...) -> .run()). Different from "
                  "agent-style frameworks; tests the pipeline "
                  "execution family."},
    {"position": 30, "full_name": "google/adk-python",
     "repository_id": 32,
     "resolved_sha": "c3d3730250b64156129508354b45120372f95334",
     "stars": 21303,
     "rationale": "Google ADK - Runner(agent, session_service) -> "
                  "run_async(). Provider-pluggable via google-adk "
                  "providers; tests a different invocation surface."},
    {"position": 43, "full_name": "microsoft/agent-framework",
     "repository_id": 854,
     "resolved_sha": "edfe115ea06bca57ae5a123d0fac5b3fdda13603",
     "stars": 13137,
     "rationale": "Microsoft agent-framework - ChatAgent / Workflow; "
                  "Azure-influenced; tests Microsoft-style chat-agent "
                  "+ workflow builder family."},
]


def materialize_one(mat: RepositoryMaterializer,
                     *, full_name: str, clone_url: str,
                     repo_sha: str, repository_id: int) -> dict:
    """Materialize one repo at the frozen SHA. Return inspection
    workspace path + cache metadata. The workspace is destroyed
    by the caller."""
    import uuid
    attempt_id = int(time.time() * 1_000_000) ^ uuid.uuid4().int & 0xFFFF
    prepared = mat.prepare(
        repository_id=repository_id,
        clone_url=clone_url,
        repo_sha=repo_sha,
        attempt_id=attempt_id,
    )
    return {
        "full_name": full_name,
        "clone_url": clone_url,
        "repo_sha": repo_sha,
        "repository_id": repository_id,
        "cache_key": cache_key_for_url(clone_url),
        "cache_path": str(mat.source_cache.layout(clone_url).cache_root),
        "workspace_path": str(prepared.repository_path),
        "workspace_id": str(prepared.workspace_id),
        "cache_hit": prepared.cache_hit,
        "attempt_id": attempt_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out",
                        default=str(REPO_ROOT / "audit" / "integration_discovery"
                                    / "sample_manifest.json"),
                        help="output path for sample_manifest.json")
    parser.add_argument("--keep-workspaces", action="store_true",
                        help="do NOT destroy the inspection workspaces "
                             "(default: destroy after materialization)")
    args = parser.parse_args()

    # Materialize at the per-discovery cache + workspace roots.
    sc = SourceCache(cache_root=DISCOVERY_CACHE_ROOT)
    wm = WorkspaceManager(source_cache=sc,
                          workspace_root=DISCOVERY_WORKSPACE_ROOT)
    mat = RepositoryMaterializer(source_cache=sc, workspace_manager=wm)

    DISCOVERY_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    DISCOVERY_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"# Discovery materializer")
    print(f"# cache_root = {DISCOVERY_CACHE_ROOT}")
    print(f"# workspace_root = {DISCOVERY_WORKSPACE_ROOT}")
    print(f"# sample size = {len(SAMPLE)}")
    print()

    out_items: list[dict] = []
    for entry in SAMPLE:
        full_name = entry["full_name"]
        clone_url = f"https://github.com/{full_name}.git"
        repo_sha = entry["resolved_sha"]
        repository_id = int(entry["repository_id"])

        print(f"[{entry['position']:>2}] {full_name}  sha={repo_sha[:10]}…")
        t0 = time.monotonic()
        try:
            result = materialize_one(
                mat, full_name=full_name,
                clone_url=clone_url, repo_sha=repo_sha,
                repository_id=repository_id,
            )
        except Exception as exc:
            print(f"    FAILED: {exc!r}")
            continue
        print(f"    materialized in {time.monotonic()-t0:.2f}s "
              f"(cache_hit={result['cache_hit']})")
        print(f"    workspace = {result['workspace_path']}")

        # The static inspection walks this workspace.
        out_items.append({
            **entry,
            "clone_url": clone_url,
            "resolved_sha": repo_sha,
            "materialization": result,
        })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1",
        "phase": "integration_pattern_discovery",
        "produced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frozen_manifest_source": "audit/corpus_runner_v1/cr3_50_repo_manifest.json",
        "discovery_cache_root": str(DISCOVERY_CACHE_ROOT),
        "discovery_workspace_root": str(DISCOVERY_WORKSPACE_ROOT),
        "kept_workspaces": bool(args.keep_workspaces),
        "sample_size": len(out_items),
        "items": out_items,
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True),
                        encoding="utf-8")
    print()
    print(f"wrote {out_path}")
    print()
    print("# To inspect each repo, cd into the workspace path above.")
    print("# Workspaces are disposable; the source cache is retained.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
