"""Heuristic relevance + agent_category classifier.

Accept definition (strict):
    "Repository contains a substantive Python implementation of an AI
    agent, agent runtime, or framework capable of orchestrating
    actions/tools."

Everything else — skill packs, plugins, MCP-server-only repos, paper
artifacts, RL/simulation code, workshops, awesome-lists, simple
wrappers, datasets, model repos — must NOT be accepted. Either reject
or leave as candidate.

The classifier uses repository metadata only (name, description, topics,
language, stars, activity). It does NOT clone or read source files.

Outputs:
- ``relevance_status``: accepted | candidate | rejected | unknown
- ``agent_category``:   one of the canonical categories (or unknown / not_agent)
- ``confidence``:       0.0–1.0
- ``reason``:           short human-readable explanation

Design rules (locked in by the 2026-08-27 audit):
- Hard reject only obvious non-agents. Rejected rows still get stored as
  audit trail.
- Anything ambiguous stays ``candidate`` — never silently rejected.
- Stars are only one signal. A repo with 20★ pushed this week is more
  interesting than one with 800★ last touched two years ago.
- The accept gate is strict. Many repos that the previous classifier
  accepted will be downgraded to ``candidate`` or ``rejected`` after
  reclassification.
- Skill packs / plugins are explicitly excluded. They are not agents;
  if we want them later they belong in a separate corpus.

Audit findings this revision addresses:
- Drop implementation-detail topics from reject list (ollama, llama-cpp,
  prompt-engineering, webui, tui, booking, llama-3, llamacpp). They
  caused 10 real agents to be wrongly rejected.
- Add hard-reject for: paper artifacts, RL/Isaac-Gym frameworks,
  MCP-server-only repos, skill packs, workshops, awesome-lists (when
  purely a list).
- Add positive topic hints for common agent domains: PPT generation,
  video generation, tutor, fintech, deep-research.
- Gate ``accepted`` to require substantive Python source signals.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger("repo_corpus.classifier")


# ──────────────────────────────────────────────────────────────────────
# Categories
# ──────────────────────────────────────────────────────────────────────
CATEGORY_CODING_AGENT         = "coding_agent"
CATEGORY_GENERAL_AGENT        = "general_agent"
CATEGORY_AGENT_FRAMEWORK      = "agent_framework"
CATEGORY_MULTI_AGENT          = "multi_agent"
CATEGORY_BROWSER_AGENT        = "browser_agent"
CATEGORY_COMPUTER_USE_AGENT   = "computer_use_agent"
CATEGORY_WORKFLOW_AGENT       = "workflow_agent"
CATEGORY_TOOL_USING_AGENT     = "tool_using_agent"
CATEGORY_OTHER_AGENT          = "other_agent"
CATEGORY_NOT_AGENT            = "not_agent"
CATEGORY_UNKNOWN              = "unknown"

ALL_CATEGORIES: tuple[str, ...] = (
    CATEGORY_CODING_AGENT, CATEGORY_GENERAL_AGENT, CATEGORY_AGENT_FRAMEWORK,
    CATEGORY_MULTI_AGENT, CATEGORY_BROWSER_AGENT, CATEGORY_COMPUTER_USE_AGENT,
    CATEGORY_WORKFLOW_AGENT, CATEGORY_TOOL_USING_AGENT, CATEGORY_OTHER_AGENT,
    CATEGORY_NOT_AGENT, CATEGORY_UNKNOWN,
)

# ──────────────────────────────────────────────────────────────────────
# Relevance status
# ──────────────────────────────────────────────────────────────────────
STATUS_ACCEPTED  = "accepted"
STATUS_CANDIDATE = "candidate"
STATUS_REJECTED  = "rejected"
STATUS_UNKNOWN   = "unknown"

ALL_STATUSES: tuple[str, ...] = (
    STATUS_ACCEPTED, STATUS_CANDIDATE, STATUS_REJECTED, STATUS_UNKNOWN,
)


# ──────────────────────────────────────────────────────────────────────
# Hard-exclude name patterns
# ──────────────────────────────────────────────────────────────────────
# These match against name + full_name + description.
_HARD_EXCLUDE_NAME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Curated lists (pure awesome-lists). NOT rejected if they ALSO carry
    # agent-runtime topics — see classify() for the override.
    (re.compile(r"\bawesome[-_ ]", re.I),                          "awesome-list"),
    (re.compile(r"^awesome\b", re.I),                              "awesome-list"),
    # Workshops, tutorials, courses, interviews, cookbooks
    (re.compile(r"\bworkshop(s)?\b", re.I),                        "workshop"),
    (re.compile(r"\btutorial(s|ing)?\b", re.I),                    "tutorial"),
    (re.compile(r"\bcourse(s|ware)?\b", re.I),                     "course"),
    (re.compile(r"\bcookbook\b", re.I),                            "cookbook"),
    (re.compile(r"\binterview[-_ ]?(prep|questions?)\b", re.I),    "interview-prep"),
    # Books, papers, datasets, benchmarks, models, roadmaps
    (re.compile(r"\bcheat[-_ ]?sheet\b", re.I),                    "cheatsheet"),
    (re.compile(r"\b(book(s)?|handbook)\b", re.I),                 "book"),
    (re.compile(r"\broad[-_ ]?map(s)?\b", re.I),                   "roadmap"),
    (re.compile(r"\b(learning|study)[-_ ]?path\b", re.I),          "learning-path"),
    (re.compile(r"\btext[-_ ]?book\b", re.I),                      "textbook"),
    (re.compile(r"\b(syllabus|curriculum)\b", re.I),               "syllabus"),
    (re.compile(r"\bcheatsheets?\b", re.I),                        "cheatsheet"),
    (re.compile(r"\bdataset(s)?\b", re.I),                         "dataset"),
    (re.compile(r"\bbenchmark(s|ing)?\b", re.I),                   "benchmark"),
    (re.compile(r"\bpaper(s)?[-_ ]?impl", re.I),                   "paper-impl"),
    (re.compile(r"\bmodel(s)?[-_ ]?zoo\b", re.I),                 "model-zoo"),
    (re.compile(r"\bprompt[-_ ]?(library|collection|book|guide)\b", re.I),
                                                                  "prompt-library"),
    # NOTE: `webui` / `web-ui` is NOT in the broad name/desc patterns
    # below — many real agents ship with a WebUI internally. The
    # frontend reject fires on `webui` only when it's the *repo name*
    # (handled in classify() via the name-only check).
    # Plain chatbot / wrapper UIs
    (re.compile(r"^chatgpt[-_ ]?(clone|wrapper|ui)$", re.I),       "chatgpt-clone"),
    (re.compile(r"^llm[-_ ]?ui$", re.I),                           "llm-ui"),
    (re.compile(r"^llm[-_ ]?playground$", re.I),                   "llm-playground"),
)

# Hard-exclude topic patterns — substring match on individual topics.
# Conservative: only flag when the topic is the primary signal.
_HARD_EXCLUDE_TOPIC_PATTERNS: tuple[tuple[str, str], ...] = (
    # Generic list / learning resources
    ("awesome",                  "awesome-list"),
    ("awesome-list",             "awesome-list"),
    ("learning-resource",        "learning-resource"),
    ("roadmap",                  "learning-resource"),
    ("learning-path",            "learning-path"),
    ("cheatsheet",               "cheatsheet"),
    ("interview-prep",           "interview-prep"),
    ("stanford",                 "course"),
    # Non-agent AI artifacts
    ("dataset",                  "dataset"),
    ("benchmark",                "benchmark"),
    ("prompt-library",           "prompt-library"),
    # RL / spiking / OpenAI Gym (not LLM agents). `gym` is intentionally
    # NOT here — many legitimate Python packages use the word "gym"
    # (OpenAI Gym is properly caught by `openai-gym`).
    ("openai-gym",               "rl-framework"),
    ("isaac-gym",                "rl-framework"),
    ("self-play",                "rl-framework"),
    ("world-model",              "world-model"),
    ("worldmodel",               "world-model"),
    ("spiking-neural-network",   "spiking-nn"),
    ("neuroscience",             "spiking-nn"),
    # MCP server-only repos (per spec: not agents). NOTE: bare `mcp`
    # is intentionally NOT here — `mcp` is the Model Context Protocol
    # and legitimate agents routinely list it as a topic. We only
    # reject the specifically server-only markers.
    ("mcp-server",               "mcp-server"),
    ("mcp-servers",              "mcp-server"),
    ("mcp-gateway",              "mcp-server"),
    ("mcp-service",              "mcp-server"),
    ("mcp-services",             "mcp-server"),
    ("mcp-tools",                "mcp-server"),
    ("mcp-collection",           "mcp-server"),
    ("mcp-marketplace",          "mcp-server"),
    ("mcp-registry",             "mcp-server"),
    # Skill packs / plugins (per spec: separate corpus, not agents)
    ("agent-skill",              "skill-pack"),
    ("agent-skills",             "skill-pack"),
    ("claude-skill",             "skill-pack"),
    ("claude-skills",            "skill-pack"),
    ("claude-plugin",            "skill-pack"),
    ("codex-plugin",             "skill-pack"),
    ("openclaw-skill",           "skill-pack"),
    ("openclaw-plugin",          "skill-pack"),
    ("openclaw-skills",          "skill-pack"),
    # Frontend / webui topics — bare `webui` is intentionally NOT here.
    # Many real agents ship with a WebUI; only when the repo is named
    # `-webui` or `-web-ui` should we treat it as a frontend. That
    # check lives in classify() (name-only).
    ("frontend",                 "frontend"),
)

# Description signals for paper artifacts (conference tag + paper language).
_PAPER_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(iclr|icml|neurips|cvpr|aaai|emnlp|acl|naacl|ijcai)\s*['’]?\s*\d{2,4}\b", re.I),
    re.compile(r"\bofficial code implementation\b", re.I),
    re.compile(r"\bofficial implementation\b", re.I),
    re.compile(r"\bimplementation of (the|our)\b.{0,40}\bpaper\b", re.I),
    re.compile(r"\bcode for paper\b", re.I),
    re.compile(r"\barxiv[: ]", re.I),
)

# Skill-pack / recipe / capability-pack patterns.
_SKILL_PACK_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bclaude code skill\b", re.I),
    re.compile(r"\bclaude[-_ ]code plugin\b", re.I),
    re.compile(r"\bplugin for claude code\b", re.I),
    re.compile(r"\bskill for (claude code|codex|cursor|opencode)\b", re.I),
    re.compile(r"\bruns? on (claude code|codex|cursor|opencode)\b", re.I),
    re.compile(r"\bcopy[-_ ]?paste\b.{0,40}\b(hooks?|recipes?|snippets?|config)\b", re.I),
    re.compile(r"^\s*\d{2,4}\b.*\b(structured\s+)?(skills?|capabilities?|services?)\b\s+for\b", re.I),
    re.compile(r"\blibrary of\b.{0,40}\b(skills?|tools?|integrations?)\b", re.I),
    re.compile(r"\bgive\b.{0,30}\b(your )?ai[-_ ]?agents?\b.{0,40}\b(eyes|capabilit|ability|power)", re.I),
    re.compile(r"\b(skill|plugin)[-_ ]?(pack|hub|set)\b", re.I),
)

# MCP-server-only description signals.
_MCP_SERVER_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^mcp server (for|that|which|to)\b", re.I),
    re.compile(r"\bmcp server (for|that|which|to)\b", re.I),
    re.compile(r"\bmcp servers? for the\b", re.I),
    re.compile(r"^\s*give ai (assistants|agents)\s+.{0,40}\bsuperpowers\b", re.I),
    re.compile(r"\bmcp gateway\b|\bmcp registry\b|\bmcp control plane\b", re.I),
)

# Frontend / WebUI / Gradio descriptions (a UI for someone else's agent).
# Apply ONLY when description explicitly frames as a UI layer — many
# real agents use WebUI internally but ship their own runtime.
_FRONTEND_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgradio\b", re.I),
    re.compile(r"\bstreamlit\b", re.I),
    re.compile(r"\bfrontend for\b", re.I),
    re.compile(r"\bbest way to use\b.{0,30}\bfrom the web\b", re.I),
    # A name with "webui" / "web-ui" surrounded by word boundaries —
    # without context this is almost always a frontend for another agent.
    # We rely on the name-check below rather than this generic pattern.
)

# Memory / persistence / storage layer patterns.
_MEMORY_LAYER_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmemory[-_ ]?(layer|subsystem|store|backend|substrate)\b", re.I),
    re.compile(r"\bmemory[-_ ]?plus\b|\bmemov?\b", re.I),
    re.compile(r"\brecall|reflect|retrieval[-_ ]?augmented\b.{0,30}\b(agent memory|memory)\b", re.I),
    re.compile(r"\bagent memory\b", re.I),
    re.compile(r"\b(consolidat|consolidate|consolidating)\b.{0,30}\b(memory|knowledge)\b", re.I),
)

# Tool / plugin / extension patterns. A repo that is a tool/extension
# for an existing agent is not itself a runtime.
_TOOLSET_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btoolset\b", re.I),
    re.compile(r"\bplugin(s)? for\b", re.I),
    re.compile(r"\bextension(s)?\b", re.I),
    re.compile(r"\bdelegates? to\b", re.I),
    re.compile(r"\bskill(s)? (pack|set|suite|collection|catalog)\b", re.I),
    re.compile(r"\bcli and skills\b", re.I),
    re.compile(r"\b(tool|command)[-_ ]?(call|use)[-_ ]?(hub|tool|integration)\b", re.I),
    re.compile(r"\bcli that\b.{0,30}\b(reads? the|parses?)\b", re.I),
    re.compile(r"\bupload\b.{0,20}\b(contract|file|document|pdf)\b.{0,30}\b(get|red[-_ ]flags?|explanations?)\b", re.I),
    re.compile(r"\bsqueeze\b.{0,40}\boutput\b", re.I),
    re.compile(r"\bpruning\b.{0,40}\boutput\b|\boutput.{0,40}prun", re.I),
    re.compile(r"\bbest way to use\b.{0,40}\bagent\b", re.I),
    re.compile(r"\brun\b.{0,30}\bon the same\b.{0,15}\b(account|channel|number)\b", re.I),
    re.compile(r"\brun\b.{0,20}\bcloud\b.{0,20}\bcoding agents?\b", re.I),
    re.compile(r"\b(spec[-_ ]?driven|workflow)\b.{0,30}\b(skills?|artifacts?)\b", re.I),
)

# Observability / tracing / traffic interception patterns.
_OBSERVABILITY_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(intercept(ing)?|trace(ing)?|inspect)\b.{0,30}\b(api traffic|coding agent|llm traffic)\b", re.I),
    re.compile(r"\btrace[-_ ]?viewer\b", re.I),
    re.compile(r"\bcli for\b.{0,40}\b(static analysis|threat modeling|threat model)\b.{0,40}\b(of )?(other )?agents?\b", re.I),
    re.compile(r"\bguardrail(s|enforce|enforcement)?\b.{0,30}\b(llm traffic|llm gateway|llm proxy)\b", re.I),
    re.compile(r"\b(remote terminal|sandbox rest)\b.{0,30}\bfor agents\b", re.I),
    re.compile(r"\bmake your agents (follow|comply)\b", re.I),
    re.compile(r"\b(reliability|safety|compliance|policy)[-_ ]?(harness|enforcement)\b", re.I),
    re.compile(r"\bai (firewall|governance|policy|audit)\b", re.I),
    re.compile(r"\bai[-_ ]?kit ?kit\b|\bai toolkit\b", re.I),
)

# Educational content / documentation patterns.
_EDUCATIONAL_DESC_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bstep[-_ ]?by[-_ ]?step\b.{0,30}\b(guide|tutorial|walkthrough|build)\b", re.I),
                                                                  "step-by-step guide"),
    (re.compile(r"\blearning[-_ ]?path\b", re.I),                "learning path"),
    (re.compile(r"\b(stanford|cs\d{3,4}[a-z]?)\b.{0,30}\bcourse\b", re.I),
                                                                  "stanford course"),
    (re.compile(r"\bopen[-_ ]?source book\b.{0,40}\b(experimental|example|accompanying)\b", re.I),
                                                                  "book with code"),
    (re.compile(r"\bnotes vault\b|\bnotes\b.{0,40}\bcovering\b", re.I),
                                                                  "notes vault"),
    (re.compile(r"\bcurated list\b|\breading list\b|\b\d{2,4}\+?\s+resources\b", re.I),
                                                                  "curated list"),
    (re.compile(r"\bknowledge[-_ ]?base\b.{0,30}\b(adapted|from)\b", re.I),
                                                                  "knowledge base"),
    (re.compile(r"\bresources,? practice and research\b", re.I), "resources/practice/research"),
    (re.compile(r"\b\d{2,4}K LOC\b", re.I),                       "XXXK LOC reference"),
    (re.compile(r"\breverse[-_ ]?engineering\b", re.I),           "reverse engineering"),
)

# Specialised platform / marketplace / SDK / protocol / spec descriptions.
_PLATFORM_DESC_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{2,4}\+?\s+integrations?\b", re.I),         "integrations marketplace"),
    (re.compile(r"\btool[-_ ]?calling platform\b", re.I),         "tool-calling platform"),
    (re.compile(r"\bmarketplace client\b|\bpublishing agents to\b", re.I),
                                                                  "marketplace"),
    (re.compile(r"\bdeployment sdk\b", re.I),                     "deployment SDK"),
    (re.compile(r"\bdeploy your\b.{0,40}\bagents?\b.{0,40}\b(production|cloud|uptime|environment)\b", re.I),
                                                                  "deploy agents"),
    (re.compile(r"\brest/openapi specification\b", re.I),         "protocol spec"),
    (re.compile(r"\b(common interface|tech stack agnostic|protocol)\b", re.I),
                                                                  "protocol spec"),
    (re.compile(r"^\s*examples?\s+repository\b|\bexamples? of\b.{0,60}\bcan be built\b", re.I),
                                                                  "examples only"),
)

# Industrial / safety / autonomous-vehicle topics — these are not LLM agents.
_INDUSTRIAL_TOPICS: tuple[str, ...] = (
    "autonomous-vehicle", "autonomous-vehicles", "autonomous-driving",
    "self-driving", "tesla", "fsd", "robotics", "robot-control",
    "design-by-contract", "verification", "static-analysis",
    "contract-review", "threat-modeling",
    "interview", "interview-prep", "java", "kotlin",
    "notes-vault",
    "spec-driven-development",  # usually workflow spec, not agent runtime
    "china-equity", "china-stocks", "chinese-stocks",
    "parquet", "data-lake", "duckdb",  # data infra, not LLM agent
)

# Reinforcement-learning description (catches `Saran-nns/sorn` whose topic
# `openai-gym` was missing but description referenced OpenAI Gym).
_RL_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bopenai gym\b", re.I),
    re.compile(r"\breinforcement[-_ ]?learning\b.{0,40}\b(simulator|environment|reset|step)\b", re.I),
    re.compile(r"\bself[-_ ]?organizing recurrent\b", re.I),
    re.compile(r"\bneuro[-_ ]?robotics\b", re.I),
)

# RL / non-LLM-agent description signals.
_NON_LLM_AGENT_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\breinforcement[-_ ]?learning\b", re.I),
    re.compile(r"\bspiking[-_ ]?neural\b", re.I),
    re.compile(r"\bself[-_ ]?play\b", re.I),
    re.compile(r"\bmulti[-_ ]?agent\b.{0,40}\b(simulator|simulation|racing|game|environment)\b", re.I),
)


# ──────────────────────────────────────────────────────────────────────
# Agent-runtime signals (for accept gate)
# ──────────────────────────────────────────────────────────────────────
# Strong topics that signal an agent runtime (after hard-exclusion passes).
_AGENT_RUNTIME_TOPICS: tuple[str, ...] = (
    "agent", "agents", "agentic", "agentic-ai", "agentic-workflow",
    "agent-runtime", "agent-framework", "agent-platform",
    "ai-agent", "ai-agents", "ai-agent-framework",
    "autonomous-agent", "autonomous-agents",
    "multi-agent", "multi-agent-system", "multi-agent-systems",
    "llm-agent", "llm-agents", "llm-agent-framework",
    "conversational-ai-agent", "task-automation", "ai-automation",
)

# Sub-keyword → category mapping for both topics and description.
_CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    (r"\bcoding[-_ ]?agent\b|\bswe[-_ ]?agent\b|\bcode[-_ ]?agent\b"
     r"|\bcode[-_ ]?generation\b|\bcode[-_ ]?interpreter\b"
     r"|\bgenerate\b.*\bcode\b"
     r"|\b(build|creates?|generates?)\b.*\b(code|app|software|project|repo)\b",
                                                                  CATEGORY_CODING_AGENT),
    (r"\bbrowser[-_ ]?agent\b|\bbrowser[-_ ]?use\b|\bweb[-_ ]?agent\b"
     r"|\bbrowser[-_ ]?automation\b|\bweb[-_ ]?automation\b",   CATEGORY_BROWSER_AGENT),
    (r"\bcomputer[-_ ]?use\b|\bdesktop[-_ ]?agent\b|\bcomputer[-_ ]?agent\b"
     r"|\bgui[-_ ]?agent\b|\bscreen[-_ ]?automation\b",          CATEGORY_COMPUTER_USE_AGENT),
    (r"\bmulti[-_ ]?agent\b|\bswarm\b|\bcrew\b|\bagentic[-_ ]?team\b",
                                                                  CATEGORY_MULTI_AGENT),
    (r"\bworkflow\b|\borchestrat|\bpipeline\b",                  CATEGORY_WORKFLOW_AGENT),
    (r"\btool[-_ ]?use\b|\btool[-_ ]?calling\b|\bfunction[-_ ]?calling\b"
     r"|\bmcp\b(?![- ]server)|\bplugin\b|\brag\b|\bretrieval[-_ ]?augmented\b",
                                                                  CATEGORY_TOOL_USING_AGENT),
    (r"\bagent[-_ ]?framework\b|\bagent[-_ ]?runtime\b|\bagent[-_ ]?sdk\b"
     r"|\bagent[-_ ]?platform\b|\bllm[-_ ]?framework\b",        CATEGORY_AGENT_FRAMEWORK),
    (r"\bautonomous\b|\bauto[-_ ]?gpt\b|\bfull[y]?[-_ ]?autonomous\b",
                                                                  CATEGORY_GENERAL_AGENT),
)

# Domain → category mapping for topics that imply an agent use case
# even when the topic name doesn't literally contain "agent".
_DOMAIN_TOPIC_TO_CATEGORY: tuple[tuple[str, str], ...] = (
    # coding_agent: anything explicitly about code
    ("code-generation",         CATEGORY_CODING_AGENT),
    ("code-interpreter",        CATEGORY_CODING_AGENT),
    ("code-review",             CATEGORY_CODING_AGENT),
    # workflow_agent: presentation, video, data analysis
    ("ppt",                     CATEGORY_WORKFLOW_AGENT),
    ("pptx",                    CATEGORY_WORKFLOW_AGENT),
    ("powerpoint",              CATEGORY_WORKFLOW_AGENT),
    ("presentation",            CATEGORY_WORKFLOW_AGENT),
    ("video-generation",        CATEGORY_WORKFLOW_AGENT),
    ("ai-video",                CATEGORY_WORKFLOW_AGENT),
    ("deep-research",           CATEGORY_WORKFLOW_AGENT),
    ("data-analysis",           CATEGORY_WORKFLOW_AGENT),
    ("automation",              CATEGORY_WORKFLOW_AGENT),
    # general_agent: tutor / education / personal AI
    ("tutor",                   CATEGORY_GENERAL_AGENT),
    ("ai-tutor",                CATEGORY_GENERAL_AGENT),
    ("education",               CATEGORY_GENERAL_AGENT),
    ("personal-ai",             CATEGORY_GENERAL_AGENT),
    # tool_using_agent: finance / data
    ("fintech",                 CATEGORY_TOOL_USING_AGENT),
    ("investment",              CATEGORY_TOOL_USING_AGENT),
    ("stock-analysis",          CATEGORY_TOOL_USING_AGENT),
    ("trading",                 CATEGORY_TOOL_USING_AGENT),
    # browser_agent: explicit
    ("browser-automation",      CATEGORY_BROWSER_AGENT),
    # computer_use_agent: explicit
    ("computer-vision",         CATEGORY_COMPUTER_USE_AGENT),
)


# ──────────────────────────────────────────────────────────────────────
# Generic AI/agent description patterns
# ──────────────────────────────────────────────────────────────────────
# These patterns increase confidence in the accept gate. Combined with
# an agent-runtime topic (or, absent that, the description alone), they
# justify `accepted`. Python-language filtering happens upstream in the
# pipeline, so we don't re-gate on "this repo mentions Python" here.
_GENERIC_AGENT_DESC_HINTS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bai[-_ ]?agent\b", re.I),
    re.compile(r"\bautonomous[-_ ]?agent\b", re.I),
    re.compile(r"\bcoding[-_ ]?agent\b", re.I),
    re.compile(r"\bbrowser[-_ ]?agent\b", re.I),
    re.compile(r"\bagent[-_ ]?framework\b", re.I),
    re.compile(r"\bagent[-_ ]?runtime\b", re.I),
    re.compile(r"\bagentic\b", re.I),
    re.compile(r"\btool[-_ ]?use\b|\btool[-_ ]?calling\b", re.I),
    re.compile(r"\bfunction[-_ ]?calling\b", re.I),
    re.compile(r"\bautonomous\b", re.I),
    re.compile(r"\bllm[-_ ]?powered\b|\bllm[-_ ]?driven\b", re.I),
    re.compile(r"\bchat[-_ ]?agent\b|\btask[-_ ]?agent\b", re.I),
)


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────
@dataclass
class Classification:
    relevance_status: str
    agent_category: str
    confidence: float
    reason: str


def classify(repo: dict) -> Classification:
    """Decide whether a GitHub repository contains a substantive Python
    AI agent.

    Strict accept definition:
        The repository ships a runnable Python implementation of an AI
        agent, agent runtime, or framework that orchestrates actions
        and tools.

    Anything that fails that test is either rejected (with a clear
    reason) or left as candidate for human review.
    """
    name = (repo.get("name") or "").strip()
    full_name = (repo.get("full_name") or "").strip()
    description = (repo.get("description") or "").strip()
    topics = [t.lower() for t in (repo.get("topics") or [])]
    archived = bool(repo.get("archived"))
    fork = bool(repo.get("fork"))
    pushed_at = repo.get("pushed_at")
    language = (repo.get("language") or "").strip()

    haystack = " ".join([name, full_name, description]).lower()
    topic_blob = " ".join(topics)

    # ─── 1. Trivial hard rejections ─────────────────────────────────────
    if archived:
        return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 1.0,
                              "archived repository")
    if fork:
        return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 1.0,
                              "fork of another repository")
    if not name and not description:
        return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.8,
                              "no name or description")
    if not pushed_at:
        return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.6,
                              "no push date on GitHub")
    if language and language != "Python":
        # Caller should already filter by language, but defend in depth.
        return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 1.0,
                              f"primary language is {language!r}, not Python")

    # ─── 2. Hard exclusions: name/desc patterns ─────────────────────────
    # Only reject "awesome" when no agent-runtime topic is present —
    # some legitimate frameworks use "Awesome" in branding.
    awesome_match = None
    for pat, reason in _HARD_EXCLUDE_NAME_PATTERNS:
        if pat.search(haystack):
            if reason == "awesome-list":
                awesome_match = reason
                continue
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.9,
                                  f"name/description matches reject pattern: {reason}")

    if awesome_match and not _has_agent_runtime_topic(topics):
        return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.85,
                              "awesome-list with no agent-runtime signal")

    # ─── 3. Hard exclusions: topic patterns ─────────────────────────────
    # Match exact topic name OR topic starts with needle+'-'/' '. This
    # avoids e.g. 'prompt-engineering' accidentally matching needle
    # 'prompt-library' just because one contains the prefix of the other.
    for topic in topics:
        for needle, reason in _HARD_EXCLUDE_TOPIC_PATTERNS:
            if topic == needle or topic.startswith(needle + "-") or topic.startswith(needle + "_"):
                return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.8,
                                      f"rejected topic '{topic}' ({reason})")
    # Industrial / non-LLM-agent topics (autonomous vehicles, robotics,
    # contract review, verification — not LLM agents).
    for topic in topics:
        if topic in _INDUSTRIAL_TOPICS:
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.8,
                                  f"non-LLM-agent topic '{topic}'")

    # ─── 4. Hard exclusions: description signals ────────────────────────
    # Paper artifacts
    for pat in _PAPER_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.9,
                                  f"paper artifact: {pat.pattern}")

    # Skill packs / plugins — even if they describe an "agent", they are
    # not standalone agent runtimes.
    for pat in _SKILL_PACK_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.85,
                                  "skill pack / plugin (not a standalone agent runtime)")

    # MCP server-only repos
    for pat in _MCP_SERVER_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.85,
                                  "MCP server (not a standalone agent runtime)")

    # RL / spiking / non-LLM agents
    for pat in _NON_LLM_AGENT_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.85,
                                  "non-LLM agent framework (RL / spiking / simulator)")

    # Frontend / WebUI / Gradio UIs (description explicitly frames a UI
    # layer for someone else's agent). Real agents that ship with a
    # WebUI internally are not caught by this — only repos whose
    # description presents themselves AS the UI do.
    if re.search(r"\bweb[-_ ]?ui\b", (name or "").lower()):
        return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.8,
                              "WebUI in repo name (frontend for another agent)")
    for pat in _FRONTEND_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.8,
                                  "frontend / WebUI for another agent")

    # Memory / persistence layer (substrate for OTHER agents, not itself).
    # Even with agent topics — "Agent Memory That Learns" is the product
    # description of a memory layer, not a sign that the repo ships an
    # agent runtime.
    for pat in _MEMORY_LAYER_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.8,
                                  "memory / persistence layer (substrate, not a runtime)")

    # Observability / tracing / proxy for OTHER agents
    for pat in _OBSERVABILITY_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.85,
                                  "observability / proxy for other agents")

    # Toolset / plugin / extension / single-purpose CLI
    for pat in _TOOLSET_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.8,
                                  "toolset / plugin / extension (not a standalone runtime)")

    # Educational content / documentation / cookbooks
    for pat, label in _EDUCATIONAL_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.8,
                                  f"educational content: {label}")

    # Platform / marketplace / SDK / protocol
    for pat, label in _PLATFORM_DESC_PATTERNS:
        if pat.search(description):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.8,
                                  f"platform/SDK (not a runtime): {label}")

    # RL in description
    for pat in _RL_DESC_PATTERNS:
        if pat.search(description) and not any(
            p.search(description) for p in _GENERIC_AGENT_DESC_HINTS
        ):
            return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.85,
                                  "reinforcement-learning library (not LLM agent)")

    # ─── 5. World-model / paper-artifact backup reject ────────────────
    # Some LLM-agent papers slide through on the `multi-agent` topic.
    # If the description sounds like a research paper / world model,
    # reject unless we have an explicit agent-runtime description.
    worldmodel_desc = re.compile(
        r"\bworld[-_ ]?model(s|ing)?\b|\bgenerative multi[-_ ]?agent\b",
        re.I,
    )
    if worldmodel_desc.search(description) and not any(
        pat.search(description) for pat in _GENERIC_AGENT_DESC_HINTS
    ):
        return Classification(STATUS_REJECTED, CATEGORY_NOT_AGENT, 0.85,
                              "world-model / generative-multi-agent research artifact")

    # ─── 6. Agent-runtime signal (Python language already guaranteed) ──
    has_runtime_topic = _has_agent_runtime_topic(topics)
    matched_categories = _categories_from_haystack(haystack) + _categories_from_topics(topics)

    # Tier-1: clear agent-runtime topic.
    if has_runtime_topic:
        category, confidence = _best_category(matched_categories, topics, stars=int(repo.get("stargazers_count") or 0))
        if category != CATEGORY_UNKNOWN:
            return Classification(STATUS_ACCEPTED, category, confidence,
                                  "agent-runtime topic matched a category")
        # Runtime topic but no specific category matched → other_agent
        return Classification(STATUS_ACCEPTED, CATEGORY_OTHER_AGENT,
                              0.75 if int(repo.get("stargazers_count") or 0) >= 100 else 0.6,
                              "agent-runtime topic, no category-specific match")

    # Tier-2: description hints of agent behaviour.
    has_desc_hint = any(pat.search(description) for pat in _GENERIC_AGENT_DESC_HINTS)
    if has_desc_hint:
        category, confidence = _best_category(matched_categories, topics, stars=int(repo.get("stargazers_count") or 0))
        if category != CATEGORY_UNKNOWN:
            return Classification(STATUS_ACCEPTED, category,
                                  confidence * 0.85,
                                  "agent description + category-specific match")
        return Classification(STATUS_CANDIDATE, CATEGORY_UNKNOWN, 0.45,
                              "agent description but no category-specific match")

    # Tier-3: no clear agent signal. Stay candidate.
    return Classification(STATUS_CANDIDATE, CATEGORY_UNKNOWN, 0.2,
                          "no agent-runtime topic or description hint detected")


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _has_agent_runtime_topic(topics: list[str]) -> bool:
    blob = " ".join(topics)
    return any(t in blob for t in _AGENT_RUNTIME_TOPICS)


def _categories_from_haystack(text: str) -> list[str]:
    """Match category rules against arbitrary text (description or topic blob)."""
    found: list[str] = []
    for pattern, cat in _CATEGORY_RULES:
        if re.search(pattern, text, re.I):
            found.append(cat)
    return found


def _categories_from_topics(topics: list[str]) -> list[str]:
    """Map individual topics to categories using the domain-topic table."""
    found: list[str] = []
    for topic in topics:
        for needle, cat in _DOMAIN_TOPIC_TO_CATEGORY:
            if topic == needle or needle in topic:
                found.append(cat)
                break
    return found


# Category priority: more specific first.
_CATEGORY_PRIORITY: tuple[str, ...] = (
    CATEGORY_CODING_AGENT, CATEGORY_BROWSER_AGENT, CATEGORY_COMPUTER_USE_AGENT,
    CATEGORY_MULTI_AGENT, CATEGORY_TOOL_USING_AGENT, CATEGORY_WORKFLOW_AGENT,
    CATEGORY_AGENT_FRAMEWORK, CATEGORY_GENERAL_AGENT, CATEGORY_OTHER_AGENT,
)


def _best_category(matched: list[str], topics: list[str], stars: int) -> tuple[str, float]:
    """Pick the highest-priority category from the matched set.

    Confidence is boosted by star count.
    """
    if not matched:
        return CATEGORY_UNKNOWN, 0.0
    # De-dup while preserving order.
    seen = set()
    deduped = []
    for c in matched:
        if c not in seen:
            seen.add(c); deduped.append(c)
    for cat in _CATEGORY_PRIORITY:
        if cat in deduped:
            base = 0.85 if stars >= 100 else 0.65
            return cat, base
    return CATEGORY_UNKNOWN, 0.0
