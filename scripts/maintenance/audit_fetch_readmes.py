#!/usr/bin/env python3
"""Fetch README excerpts for every repo in an audit sample.

Uses ``gh api repos/{owner}/{repo}/readme`` (which `gh` returns base64-
encoded). We then decode and trim to a max char budget so the audit
LLM context stays small.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

# Bootstrap sys.path (matches scripts/audit_sample.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def fetch_one(full_name: str, max_chars: int = 4000) -> dict:
    """Return ``{full_name, readme_excerpt, error?}``."""
    try:
        out = subprocess.check_output(
            ["gh", "api", f"repos/{full_name}/readme"],
            timeout=20,
        )
        data = json.loads(out)
        content_b64 = data.get("content", "")
        text = base64.b64decode(content_b64).decode("utf-8", errors="replace")
        excerpt = text[:max_chars]
        return {"full_name": full_name, "readme_excerpt": excerpt}
    except subprocess.TimeoutExpired:
        return {"full_name": full_name, "readme_excerpt": "", "error": "timeout"}
    except subprocess.CalledProcessError as exc:
        return {"full_name": full_name, "readme_excerpt": "", "error": str(exc)[:200]}
    except Exception as exc:
        return {"full_name": full_name, "readme_excerpt": "", "error": repr(exc)[:200]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", required=True, help="JSON from audit_sample.py")
    parser.add_argument("--out",    required=True, help="Output JSON.")
    parser.add_argument("--max-chars", type=int, default=4000)
    parser.add_argument("--sleep", type=float, default=0.05,
                        help="Seconds to wait between GitHub API calls (default 0.05).")
    args = parser.parse_args()

    sample = json.loads(Path(args.sample).read_text())
    rows = sample["sample"]
    print(f"fetching READMEs for {len(rows)} repos (max_chars={args.max_chars})")

    results: list[dict] = []
    fail = 0
    for i, row in enumerate(rows):
        if i > 0:
            time.sleep(args.sleep)
        r = fetch_one(row["full_name"], max_chars=args.max_chars)
        if r.get("error"):
            fail += 1
        results.append({**row, **r})
        if (i + 1) % 10 == 0 or i == len(rows) - 1:
            print(f"  {i+1}/{len(rows)} ({fail} failures)")

    out_path = Path(args.out)
    out_path.write_text(json.dumps({"seed": sample["seed"], "results": results}, indent=2))
    print(f"\nwrote {len(results)} rows ({fail} failures) → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
