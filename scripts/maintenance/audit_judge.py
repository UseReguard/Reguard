#!/usr/bin/env python3
"""Independent audits of a fetched-README sample.

Sends every repo (description + topics + README excerpt) to an LLM with
the strict accept definition:

    "Repository contains a substantive Python implementation of an AI
    agent, agent runtime, or framework capable of orchestrating
    actions/tools."

Acceptance threshold: target 90% strict precision.

For each row we record:
  - verdict:        ACCEPT | REJECT | BORDERLINE
  - reason:         one-sentence justification
  - is_false_pos:   True iff currently accepted but should be rejected

Borderline is counted as a soft-accept — it does NOT count as a
false positive, but is also not a hard accept. Compute both:
  - strict_precision = ACCEPT / n
  - inclusive_precision = (ACCEPT + BORDERLINE) / n
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


JUDGE_PROMPT = """\
You are auditing a Python AI-agent corpus. A row has been labeled
``accepted`` by an automated heuristic. You must judge each one against
this STRICT definition:

    "Repository contains a substantive Python implementation of an AI
    agent, agent runtime, or framework capable of orchestrating
    actions/tools."

Anything that fails the test (skill packs, plugins, MCP-server-only,
paper artifacts, RL simulators, workshops, awesome-lists, datasets,
model repos, etc.) should be REJECT.

Output a single JSON object per repo, exactly in this shape:
{{
  "verdict": "ACCEPT" | "REJECT" | "BORDERLINE",
  "reason": "<one sentence, max 200 chars>",
  "is_false_positive": true | false,
  "category_match": "<same category the heuristic assigned, OR your
                      better-corrected category; if not an agent, put 'not_agent'>"
}}

Use BORDERLINE only when the repo has partial agent signals but the
README does not let you confirm a real agent runtime exists. Borderline
should be rare. Default to ACCEPT or REJECT.

Repo: {full_name}
Heuristic verdict: accepted ({agent_category}, conf={relevance_confidence:.2f})
Stars: {stars}
Topics: {topics}
Description: {description}
README excerpt (first {readme_chars} chars):
---
{readme_excerpt}
---

Reply with ONLY the JSON object (no markdown fences, no commentary).
"""


def build_messages(rows: list[dict]) -> list[tuple[str, str]]:
    """Return list of (full_name, prompt_text)."""
    return [
        (
            r["full_name"],
            JUDGE_PROMPT.format(
                full_name=r["full_name"],
                agent_category=r["agent_category"] or "unknown",
                relevance_confidence=float(r["relevance_confidence"] or 0.0),
                stars=r["stars"],
                topics=", ".join(r["topics"]) or "(none)",
                description=r["description"][:600] or "(none)",
                readme_chars=len(r["readme_excerpt"]),
                readme_excerpt=r["readme_excerpt"] or "(README unavailable)",
            ),
        )
        for r in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readmes", required=True, help="Output of audit_fetch_readmes.py")
    parser.add_argument("--verdicts", required=True, help="Where to write the verdicts JSON.")
    args = parser.parse_args()

    data = json.loads(Path(args.readmes).read_text())
    rows = [r for r in data["results"] if not r.get("error")]
    if not rows:
        print("no rows to audit", file=sys.stderr)
        return 1
    print(f"auditing {len(rows)} rows")
    # For now this stub writes a placeholder; the agent runs are kicked
    # off in a parallel pass via the Agent tool, then results are
    # stitched in.
    Path(args.verdicts).write_text(json.dumps({"stage": "stub", "rows": []}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
