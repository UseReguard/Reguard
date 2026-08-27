#!/usr/bin/env python3
"""Aggregate per-batch verdicts into precision metrics.

Inputs:
    audit/2026-08-28-verdicts-batch-NN.json
    audit/2026-08-28-sample.json       (the deterministic sample)

Output:
    audit/2026-08-28-metrics.json   — summary stats
    audit/2026-08-28-report.md      — human-readable report
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample",    required=True)
    parser.add_argument("--audits-dir", required=True,
                        help="Directory containing ``*-verdicts-batch-NN.json`` files.")
    parser.add_argument("--glob", default=None,
                        help="Optional glob pattern (e.g. '2026-08-28-iter2-verdicts-*') to scope to a single audit iteration.")
    parser.add_argument("--out-json",   required=True)
    parser.add_argument("--out-md",     required=True)
    args = parser.parse_args()

    sample = json.loads(Path(args.sample).read_text())
    sample_by_name = {r["full_name"]: r for r in sample["sample"]}

    verdicts: list[dict] = []
    glob_pattern = args.glob if hasattr(args, "glob") and args.glob else "*-verdicts-batch-*.json"
    batch_files = sorted(Path(args.audits_dir).glob(glob_pattern))
    for bf in batch_files:
        data = json.loads(bf.read_text())
        if isinstance(data, list):
            verdicts.extend(data)
        elif "rows" in data and isinstance(data["rows"], list):
            verdicts.extend(data["rows"])
        elif "results" in data and isinstance(data["results"], list):
            verdicts.extend(data["results"])
    print(f"loaded {len(verdicts)} verdicts from {len(batch_files)} batch files")
    if verdicts:
        print("first verdict keys:", list(verdicts[0].keys()))

    # Match verdicts to sample rows.
    paired = []
    unmatched = []
    for v in verdicts:
        full = v.get("full_name")
        if full in sample_by_name:
            paired.append({**sample_by_name[full], **v})
        else:
            unmatched.append(full)
    print(f"matched {len(paired)} verdicts to sample rows; {len(unmatched)} unmatched")

    if not paired:
        print("ERROR: no paired verdicts", flush=True)
        return 1

    # Tally verdicts.
    verdict_counts = Counter(p["verdict"] for p in paired)
    n = len(paired)
    accepted  = verdict_counts.get("ACCEPT", 0)
    rejected  = verdict_counts.get("REJECT", 0)
    borderln  = verdict_counts.get("BORDERLINE", 0)

    strict_precision = accepted / n if n else 0.0
    inclusive_precision = (accepted + borderln) / n if n else 0.0

    # Stratify by star band.
    by_band: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    for p in paired:
        band = p["band"]
        by_band[band][p["verdict"]] += 1
    band_metrics = {}
    for band, c in by_band.items():
        n_b = sum(c.values())
        a_b = c.get("ACCEPT", 0)
        band_metrics[band] = {
            "n": n_b,
            "accepted": a_b,
            "rejected": c.get("REJECT", 0),
            "borderline": c.get("BORDERLINE", 0),
            "strict_precision": (a_b / n_b) if n_b else 0.0,
        }

    # Stratify by DB category.
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    for p in paired:
        cat = p.get("agent_category") or "unknown"
        by_cat[cat][p["verdict"]] += 1
    category_metrics = {}
    for cat, c in by_cat.items():
        n_c = sum(c.values())
        a_c = c.get("ACCEPT", 0)
        category_metrics[cat] = {
            "n": n_c,
            "accepted": a_c,
            "rejected": c.get("REJECT", 0),
            "borderline": c.get("BORDERLINE", 0),
            "strict_precision": (a_c / n_c) if n_c else 0.0,
        }

    # False-positive breakdown: by category.
    fp_rows = [p for p in paired if p.get("is_false_positive")]
    fp_categories = Counter(p.get("agent_category") or "unknown" for p in fp_rows)

    summary = {
        "audited": n,
        "verdict_counts": dict(verdict_counts),
        "strict_precision": strict_precision,
        "inclusive_precision": inclusive_precision,
        "target": 0.90,
        "meets_target": strict_precision >= 0.90,
        "by_band": band_metrics,
        "by_category": category_metrics,
        "false_positives": {
            "count": len(fp_rows),
            "by_db_category": dict(fp_categories),
        },
        "sample_size": len(paired),
    }

    Path(args.out_json).write_text(json.dumps(summary, indent=2))
    print(f"wrote summary → {args.out_json}")

    # Render markdown report.
    lines: list[str] = []
    lines.append("# Corpus Quality Audit — 2026-08-28 (fresh, post-reclassify)\n")
    lines.append(f"Sample: {n} accepted repos (stratified 20 per star band).")
    lines.append("Independent sub-agent verdicts against the strict accept definition.\n")
    lines.append("## TL;DR\n")
    lines.append("| Metric | Result | Target |")
    lines.append("|---|---|---|")
    lines.append(f"| Accepted strict precision | **{strict_precision:.1%}** | ≥ 90% |")
    lines.append(f"| Accepted inclusive precision | {inclusive_precision:.1%} | — |")
    lines.append(f"| False-positive count | {len(fp_rows)} | — |")
    meets = "✅ **YES**" if strict_precision >= 0.90 else "❌ **NO**"
    lines.append(f"\nMeets 90% target? {meets}\n")

    lines.append("### Verdict counts\n")
    for k in ("ACCEPT", "BORDERLINE", "REJECT"):
        lines.append(f"- {k}: {verdict_counts.get(k, 0)}")
    lines.append("")

    lines.append("### Precision by star band\n")
    lines.append("| band | n | accepted | rejected | borderline | strict precision |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for band in ("5000+", "1000-4999", "100-999", "20-99", "0-19"):
        m = band_metrics.get(band)
        if not m:
            lines.append(f"| {band} | 0 | — | — | — | n/a |")
            continue
        lines.append(f"| {band} | {m['n']} | {m['accepted']} | {m['rejected']} | {m['borderline']} | {m['strict_precision']:.1%} |")

    lines.append("\n### Precision by DB category\n")
    lines.append("| category | n | accepted | rejected | borderline | strict precision |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cat, m in sorted(category_metrics.items(), key=lambda kv: -kv[1]["n"]):
        lines.append(f"| {cat} | {m['n']} | {m['accepted']} | {m['rejected']} | {m['borderline']} | {m['strict_precision']:.1%} |")

    lines.append("\n### False positives (currently accepted, should be rejected)\n")
    if fp_rows:
        for p in fp_rows:
            lines.append(f"- `{p['full_name']}` ({p['stars']}★, {p.get('agent_category')}) — {p['reason']}")
    else:
        lines.append("None.")

    Path(args.out_md).write_text("\n".join(lines) + "\n")
    print(f"wrote report → {args.out_md}")

    # Console
    print("\n=== ACCEPTED STRICT PRECISION ===")
    print(f"  {accepted}/{n} = {strict_precision:.1%}  (target 90%)")
    print(f"  → meets target? {strict_precision >= 0.90}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
