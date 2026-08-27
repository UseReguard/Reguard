#!/usr/bin/env python3
"""Aggregate per-batch LLM proposal verdicts into a single human-review
document for the gold-bootstrap pass.

Inputs (all in audit/):
    2026-08-28-gold-bootstrap-sample.json          (stratified sample)
    2026-08-28-gold-bootstrap-readmes.json        (fetched READMEs)
    2026-08-28-gold-bootstrap-proposals-batch-00..05.json

Outputs:
    2026-08-28-gold-bootstrap-proposals.md         (human-review document)
    2026-08-28-gold-bootstrap-proposals.json      (aggregated JSON sidecar)

This is the PROPOSAL layer only. NOTHING is written to the database
here. After the user reviews and confirms gold members, a separate
script will emit llm-judge verdicts into agent_repository_audits, and
an additional human-confirmation pass will write subsequent rows with
auditor_type='human'.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _readme_section_for(readme_text: str, max_chars: int = 1200) -> str:
    if not readme_text:
        return "(README not fetched)"
    text = readme_text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars].rstrip() + "\n\n[…truncated…]"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audit-dir", required=True,
        help="Directory holding sample/readmes/proposal files",
    )
    parser.add_argument(
        "--batch-prefix",
        default="2026-08-28-gold-bootstrap",
    )
    parser.add_argument(
        "--out-md", required=True,
        help="Human-review Markdown output path",
    )
    parser.add_argument(
        "--out-json", required=True,
        help="Aggregated JSON sidecar path",
    )
    args = parser.parse_args()

    audit_dir = Path(args.audit_dir)

    sample_path   = audit_dir / f"{args.batch_prefix}-sample.json"
    readmes_path  = audit_dir / f"{args.batch_prefix}-readmes.json"
    out_md_path   = Path(args.out_md)
    out_json_path = Path(args.out_json)

    sample_doc = _load_json(sample_path)
    readme_doc = _load_json(readmes_path)

    # Sample dict keyed by full_name.
    sample_by_name: dict[str, dict] = {r["full_name"]: r for r in sample_doc["sample"]}
    # The fetch-READMEs script writes the excerpt under the key
    # `readme_excerpt`. Treat any of these shapes as the canonical readme.
    def _extract_readme(row: dict) -> str:
        for k in ("readme_excerpt", "readme", "readme_text", "content"):
            v = row.get(k)
            if v:
                return v
        return ""

    readme_by_name: dict[str, str] = {r["full_name"]: _extract_readme(r)
                                       for r in readme_doc["results"]}

    # Walk every batch proposal file.
    proposals: list[dict] = []
    seen_names: set[str] = set()
    for n in range(6):
        batch_path = audit_dir / f"{args.batch_prefix}-proposals-batch-{n:02d}.json"
        rows = _load_json(batch_path)
        for row in rows:
            name = row["full_name"]
            if name in seen_names:
                raise ValueError(f"duplicate proposal for {name}")
            seen_names.add(name)
            sample = sample_by_name.get(name)
            if sample is None:
                raise ValueError(f"proposal {name} not present in sample file")
            proposals.append({
                "full_name":         name,
                "verdict":           row["verdict"],
                "reason":            row.get("reason", ""),
                "is_false_positive": bool(row.get("is_false_positive", False)),
                "category_match":    row.get("category_match", sample["agent_category"]),
                "classifier_category": sample["agent_category"],
                "stars":             sample["stars"],
                "band":              sample["band"],
                "topics":            sample["topics"],
                "description":       sample["description"],
                "readme":            readme_by_name.get(name, ""),
            })

    if set(sample_by_name) != seen_names:
        missing_in_proposals = sorted(set(sample_by_name) - seen_names)
        extra_in_proposals   = sorted(seen_names - set(sample_by_name))
        raise ValueError(
            "proposal set != sample set.\n"
            f"  missing_in_proposals: {missing_in_proposals}\n"
            f"  extra_in_proposals:   {extra_in_proposals}"
        )

    # Verdict × category counts.
    verdict_counts: Counter[str] = Counter(p["verdict"] for p in proposals)
    by_cat: dict[str, Counter[str]] = defaultdict(Counter)
    for p in proposals:
        by_cat[p["classifier_category"]][p["verdict"]] += 1

    # Grouping for human review: ACCEPT first, BORDERLINE second, REJECT last.
    verdict_order = {"ACCEPT": 0, "BORDERLINE": 1, "REJECT": 2}
    proposals.sort(key=lambda p: (verdict_order.get(p["verdict"], 9),
                                 p["classifier_category"], -p["stars"], p["full_name"]))

    # Build Markdown body.
    lines: list[str] = []
    lines.append("# Gold-corpus bootstrap — LLM proposal layer")
    lines.append("")
    lines.append(f"**Audit batch**: `{args.batch_prefix}`  ")
    lines.append(f"**Auditor type**: `llm-judge` (automated read-based review)  ")
    lines.append(f"**Total candidates**: {len(proposals)}  ")
    lines.append(f"**Provenance**: `audit/{args.batch_prefix}-proposals-batch-{{00..05}}.json`  ")
    lines.append("")
    lines.append("> ⚠️ **Nothing here is gold yet.** These are PROPOSALS. A repository")
    lines.append("> only becomes `gold` after a human-confirmed `agent_repository_audits`")
    lines.append("> row with `auditor_type='human'` is written to the database. This")
    lines.append("> document is the input for that confirmation pass.")
    lines.append("")
    lines.append("## Verdict summary")
    lines.append("")
    lines.append("| Verdict      | Count |")
    lines.append("|--------------|-------|")
    for v in ("ACCEPT", "BORDERLINE", "REJECT"):
        lines.append(f"| {v:<12} | {verdict_counts.get(v, 0):>5} |")
    lines.append(f"| **Total**    | {len(proposals):>5} |")
    lines.append("")

    lines.append("## Verdict × classifier-category matrix")
    lines.append("")
    cats = sorted(by_cat)
    verdict_cols = ("ACCEPT", "BORDERLINE", "REJECT")
    lines.append("| classifier_category | " + " | ".join(verdict_cols) + " |")
    lines.append("|---" * (len(verdict_cols) + 1) + "|")
    for cat in cats:
        row = by_cat[cat]
        lines.append(f"| {cat} | " + " | ".join(
            f"{row.get(v, 0)}" for v in verdict_cols) + " |")
    lines.append("")

    lines.append("## Instructions for the human reviewer")
    lines.append("")
    lines.append("For every entry below, you choose one of three final verdicts:")
    lines.append("")
    lines.append("- **GOLD** — keep as engineering baseline (`agent_repository_audits` row with")
    lines.append("  `verdict='gold'`, `auditor_type='human'`)")
    lines.append("- **BORDERLINE** — needs deeper review before deciding (`verdict='borderline'`);")
    lines.append("  please add a note explaining what to investigate")
    lines.append("- **REJECT** — drop from the corpus entirely (`verdict='reject'`)")
    lines.append("")
    lines.append("Entries are grouped **ACCEPT → BORDERLINE → REJECT** (by LLM proposal).")
    lines.append("Within a group, they are sorted by classifier_category, then stars, then name.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Proposals")
    lines.append("")

    for p in proposals:
        lines.append(f"### {p['full_name']}")
        lines.append("")
        lines.append(f"- **classifier_category**: `{p['classifier_category']}`")
        lines.append(f"- **proposed by llm-judge as**: `{p['category_match']}`")
        lines.append(f"- **stars**: {p['stars']} ({p['band']})")
        lines.append(f"- **is_false_positive**: `{p['is_false_positive']}`")
        lines.append(f"- **LLM verdict**: **{p['verdict']}**")
        lines.append(f"- **LLM reason**: {p['reason']}")
        lines.append("")
        lines.append("**GitHub description:**")
        lines.append("")
        lines.append(f"> {p['description']}")
        lines.append("")
        lines.append("**Topics:**")
        if p["topics"]:
            lines.append(", ".join(f"`{t}`" for t in p["topics"]))
        else:
            lines.append("_(none)_")
        lines.append("")
        lines.append("**README excerpt:**")
        lines.append("")
        lines.append("```markdown")
        lines.append(_readme_section_for(p["readme"]))
        lines.append("```")
        lines.append("")
        lines.append(f"🔗 [view on GitHub](https://github.com/{p['full_name']})")
        lines.append("")
        lines.append("**Human review →** ☐ GOLD  ☐ BORDERLINE (note: ___)  ☐ REJECT")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_md_path.parent.mkdir(parents=True, exist_ok=True)
    out_md_path.write_text("\n".join(lines), encoding="utf-8")

    sidecar = {
        "audit_batch":      args.batch_prefix,
        "auditor_type":     "llm-judge",
        "total":            len(proposals),
        "verdict_counts":   dict(verdict_counts),
        "by_category":      {cat: dict(by_cat[cat]) for cat in cats},
        "proposals": [
            {k: v for k, v in p.items() if k != "readme"} | {"readme_chars": len(p["readme"])}
            for p in proposals
        ],
    }
    out_json_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

    print(f"wrote human-review document → {out_md_path}")
    print(f"wrote aggregated JSON sidecar → {out_json_path}")
    print(f"summary: {dict(verdict_counts)}; total={len(proposals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
