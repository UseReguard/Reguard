# Corpus Quality Audit — 2026-08-27

**Sample:** 169 repos, deterministic seed `20260827`
**Personally audited:** 116 (rejected bucket 25 + candidate bucket 25 + accepted top-50 via detailed reading + a stratified subset of category buckets)
**Defaulted (not deeply read):** 53 — counted only as "matches DB status" for the uninspected category-only repos; **excluded from precision metrics below**

---

## TL;DR

The current classifier is **not** ready to scale to 5,000. Audit shows:

| Metric | Result | Target |
|---|---|---|
| Accepted strict precision | **54.5%** | 90–95% |
| Accepted inclusive precision (incl. borderline) | 78.8% | — |
| False-negative rate (rejected → should-be-accepted) | **40.0%** | <10% |
| Candidate → should-be-accepted | **52.0%** | <20% |

The headline problem: the **reject list is way too aggressive on implementation-detail topics** (`ollama`, `llama-cpp`, `prompt-engineering`, `webui`, `tui`, `booking`, `llama-3`), and the **accept side has no filter for paper artifacts, RL frameworks, skill packs, and MCP-server collections** — exactly the categories the user's spec excluded.

**Recommendation: do not run the remaining 9 queries yet.** Tune the classifier first (proposed changes below), re-run the audit, then expand.

---

## 1. Accepted precision (the headline number)

Of 66 audited `accepted` rows:

| Verdict | Count | % |
|---|---|---|
| Real agent (clean) | 36 | **54.5%** |
| Borderline (skill pack, plugin, memory layer, paper demo, narrow agent) | 16 | 24.2% |
| Not an agent (false positive) | 14 | **21.2%** |

### Precision by star band (accepted only)

| Stars | Strict precision | n |
|---|---|---|
| 5000+ | **100.0%** | 3 |
| 1000–4999 | 87.5% | 8 |
| 100–999 | **34.5%** | 29 |
| 20–99 | 75.0% | 8 |
| 0–19 | **55.6%** | 18 |

→ The 100–999 band is the danger zone. Most skill packs, plugin repos, and paper artifacts land here.

### Precision by category (accepted only)

| DB category | Strict precision | n |
|---|---|---|
| agent_framework | 100% | 2 |
| browser_agent | 100% | 1 |
| computer_use_agent | 100% | 1 |
| workflow_agent | 100% | 2 |
| coding_agent | 76.9% | 13 |
| general_agent | **55.6%** | 9 |
| multi_agent | **50.0%** | 20 |
| tool_using_agent | **27.8%** | 18 |

→ `tool_using_agent` and `multi_agent` are the worst — they catch MCP servers and RL/research simulators respectively.

### False positive root causes (14 total)

| Cause | Count | Examples |
|---|---|---|
| Paper / research artifact | 3 | `nv-tlabs/Gamma-World`, `thu-nics/C2C`, `pzqpzq/LSF_MDia` |
| RL / Isaac Gym framework | 3 | `inspirai/TimeChamber`, `MultiAgentTORCS`, `ai-in-pm/Titans` |
| Skill pack / plugin (Claude-Code skill) | 4 | `Alexander-Tyagunov/magician`, `WinterDDo/...-autopilot`, `genpark-*` × 4 |
| MCP server (not an agent) | 2 | `mnemox-ai/idea-reality-mcp`, `sirkirby/unifi-mcp` |
| Workshop / tutorial | 1 | `iusztinpaul/...-workshop` |
| Spiking / neuroscience | 1 | `Saran-nns/sorn` |
| Research simulator API | 1 | `xavierpuigf/virtualhome` |

---

## 2. Rejected recall (false negatives)

Of 25 audited `rejected` rows, **10 are real agents** the classifier wrongly threw out (40.0% FN rate).

| Repo | Stars | Real category | Rejected because of |
|---|---|---|---|
| `HKUDS/nanobot` | **47,436** | agent_framework | topic `webui` |
| `LetsFG/LetsFG` | 1,914 | tool_using_agent | topic `booking` |
| `sbhooley/ainativelang` | 690 | agent_framework | topic `prompt-engineering` |
| `nathansutton/chad` | 7 | coding_agent | topic `tui` |
| `Alex8791-cyber/cognithor` | 153 | general_agent | topic `ollama` |
| `EmbraceAGI/LocalAGI` | 81 | general_agent | topic `llamacpp` |
| `dovvnloading/Cortex` | 38 | general_agent | topic `llama-cpp` |
| `PxA-Labs/AutoMaintainer` | 23 | general_agent | topic `llama-3` |
| `Ashutosh0428/pi-agent` | 4 | coding_agent | topic `ollama` |
| `kabartay/deepseek-local` | 3 | coding_agent | topic `ollama` |

**Pattern:** the classifier is rejecting real agents because their GitHub topics describe their **runtime stack** (ollama, llama.cpp, a TUI, a Web UI) rather than their **nature** (agent vs not). Topics like `ollama` and `llama-cpp` are **implementation choices**, not signals that the project isn't an agent.

The 47k-star `nanobot` false negative alone is a smoking gun: the classifier is throwing away the entire "self-hosted agent framework" tier.

---

## 3. Candidate quality

Of 25 audited `candidate` rows:

| Verdict | Count | % |
|---|---|---|
| Should be accepted (real agent) | 13 | **52.0%** |
| Should be rejected (not agent at all) | 8 | 32.0% |
| Borderline (stays candidate) | 4 | 16.0% |

Clear agents stuck in `candidate`:
- `hugohe3/ppt-master` (49,660★, workflow_agent) — AI PPT generator
- `julep-ai/julep` (6,591★, agent_framework) — durable AI agents framework
- `BAAI-Agents/Cradle` (2,573★, computer_use_agent) — general computer control
- `strands-labs/ai-functions` (307★, agent_framework) — agent-powered Python functions
- `agi-hub/AGIAgent` (265★, general_agent) — Claude-Cowork-like platform
- `duartecaldascardoso/article-explainer` (191★, general_agent) — agentic doc explainer
- `OpenDemon/Pilipili-AutoVideo` (202★, workflow_agent) — automated AI video agent
- `Optim-Agent/optim-agent` (933★, tool_using_agent) — LLM hyperparameter tuner
- `notque/vexjoy-agent` (416★, general_agent) — explicit agent
- `Li-Evan/Bloom` (243★, general_agent) — AI tutor
- `addsumtech/slides_maker` (481★, workflow_agent) — PPT generator
- `AMAP-ML/SkillClaw` (2,516★, agent_framework) — agent skill evolver

→ The classifier's "fall through to candidate when no specific category matches" rule catches too many real agents because the category regex list doesn't cover common agent domains (PPT generation, video gen, tutors, finetuning, etc.).

---

## 4. Why each pattern slipped through (root-cause for the classifier)

### False negatives (10)
**Cause:** `_REJECT_TOPIC_PATTERNS` in `classifier.py` contains implementation-detail topics.

```python
# CURRENT (too aggressive):
"ollama", "llama-cpp", "llamacpp", "prompt-engineering",
"webui", "tui", "booking", "llama-3"
```

These describe *how* the agent runs locally, not *whether* it's an agent.

### False positives — paper artifacts (3)
**Cause:** no topic/name regex for research-paper artifacts.

Examples slipped through: `Gamma-World`, `Cache-to-Cache (C2C)`, `LSF_MDia`.

### False positives — RL / Isaac Gym / OpenAI Gym (3)
**Cause:** no filter for non-LLM "agents" (RL research).

Topics like `reinforcement-learning`, `self-play`, `isaac-gym`, `openai-gym`, `spiking-neural-networks` slipped through because the description contains "agent" or "multi-agent".

### False positives — skill packs (4)
**Cause:** `ai-agent` / `agent-skill` topic alone passes the heuristic; nothing checks whether the repo is itself a runnable agent or a *plugin* for an existing agent.

Heuristic signals of "plugin, not agent":
- Description starts with "Skill", "Plugin", "Extension", "Add-on"
- Repo description mentions running on Claude Code / Codex / Cursor / OpenCode
- Topics include `agent-skill`, `claude-skill`, `claude-plugin`, `codex-plugin`

### False positives — MCP server collections (2)
**Cause:** the user's spec explicitly excludes "MCP server collections that are not themselves agents", but the classifier doesn't check.

Heuristic signals of "MCP server only":
- Description starts with "MCP server for X"
- Topics include `mcp-server`
- HTML URL or description says "MCP server" and there's no agent loop / runtime described

### False positives — workshops / tutorials (1)
**Cause:** the awesome-list regex covers `awesome` but not `workshop`, `tutorial`, `course`, `lecture`.

---

## 5. Proposed classifier changes (high-confidence)

These are the smallest coherent set of changes that should fix the audit findings:

### A. Drop these from the reject topic list (eliminates 10 false negatives)

```python
# REMOVE from _REJECT_TOPIC_PATTERNS:
"ollama",
"llama-cpp", "llamacpp",
"prompt-engineering",
"webui", "tui",
"booking",
"llama-3",
```

### B. Add new hard-reject topic / name patterns (eliminates ~10 false positives)

```python
# REJECT if name matches:
r"\bworkshop\b",        # hands-on workshop
r"\btutorial(s)?\b",    # tutorial
r"\bcourse(s|ware)?\b",
r"\bawesome[-_ ]",      # keep — confirmed catching real awesome lists

# REJECT if topics include (substring match):
"mcp-server", "mcp_collection",
"isaac-gym", "openai-gym", "self-play",
"reinforcement-learning",   # only when not combined with explicit LLM agent topics
"neuroscience", "spiking-neural-network",
"agent-skill", "agent-skills", "claude-skill", "claude-skills",
"claude-plugin", "codex-plugin",
"openclaw-skill", "openclaw-plugin",
```

### C. Add new "is this a real agent" topic hints

```python
# Topics that are STRONG accept signals (broaden category detection):
"ppt", "pptx", "powerpoint", "presentation",
"video-generation", "ai-video",
"tutor", "education",
"fintech", "stock", "trading",
"data-analysis", "deep-research",
```

### D. Tighten "is it really an agent" gate

Add a final check that flags a row as `candidate` rather than `accepted` when:

- Topic set contains a strong implementation-only signal (`mcp-server`, `agent-skill`, `plugin`)
- Description mentions running on Claude Code / Codex / Cursor / OpenCode as the primary executor
- Repository has no Python source dirs (`src/`, `agent/`, `runtime/`) mentioned in the README excerpt (lighter check)

### E. Loosen the awesome-list regex

Currently any "awesome" in name → reject. Change to: only reject if the repo description or topics confirm "this is purely a list". Examples that should *not* be auto-rejected:

- Real frameworks that happen to use "Awesome" in their branding
- "Awesome list of skills" with `agent-framework` topic

Heuristic:
```python
# Only reject if description contains "curated list", "reading list", "resources"
# AND no "framework" / "runtime" / "agent" / "tool" in topics.
```

### F. (Optional) Add paper/repo-impl soft filter

Flag as `not_agent` if description contains both a conference tag ("ICLR", "ICML", "NeurIPS", "arXiv") AND the topic set lacks strong agent-runtime signals. Soft reject — manual review can override.

---

## 6. Estimated impact (rough)

Applying A–D should:

- Cut false-negative rate from **40% → ~5%** (the 10 wrongly-rejected agents all hit the topic-list issue in A)
- Cut accepted false-positive rate from **21% → ~10%** (skill packs, MCP servers, paper artifacts, RL frameworks all caught)
- Move ~50% of `candidate` → `accepted` (the broader topic hints in C push agents into categories)
- Keep strict precision in the **80–90%** range on the audit sample

After tuning, re-run the audit. **If strict precision ≥ 90%** on a fresh sample, scale to 5,000. If not, iterate.

---

## 7. Open questions for the user

1. **Borderline repos (16 in the audit, mostly skill packs).** Do we keep them in `accepted` so the scanner sees Claude-Code skills as well, or filter them out? My recommendation: filter them out — they're plugins, not agents — but it's a product call.

2. **Candidate threshold.** Currently `unknown` and `candidate` mean "human review needed". With ~30% of candidates being real agents, do we want to (a) bulk-promote candidates whose topics include `ai-agent` + 100+ stars to `accepted`, or (b) keep them in `candidate` and surface them via the CLI for manual triage?

3. **Re-discover vs re-classify.** After the classifier changes, the cleanest path is to re-classify the existing 1,502 rows (cheap — no API calls, just heuristic re-runs) rather than re-discover. Then a small discovery pass to fill gaps. Want me to add a `reclassify` command?

---

## Files in this audit

- `audit/2026-08-27-sample.json` — the deterministic sample (169 repos)
- `audit/2026-08-27-readmes.json` — fetched README excerpts for each repo
- `audit/2026-08-27-verdicts.json` — my judgement per repo, with FP/FN flags
- `audit/2026-08-27-metrics.json` — summary metrics
- `audit/2026-08-27-bucket-*.json` — per-bucket dumps for re-review
