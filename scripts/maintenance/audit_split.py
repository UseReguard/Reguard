#!/usr/bin/env python3
"""Split an audit sample into N JSON batch files for parallel judging."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readmes", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args()

    data = json.loads(Path(args.readmes).read_text())
    rows = data["results"]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    batches = []
    for i in range(0, len(rows), args.batch_size):
        chunk = rows[i : i + args.batch_size]
        out_path = out_dir / f"batch-{i // args.batch_size:02d}.json"
        out_path.write_text(json.dumps({"seed": data["seed"], "rows": chunk}, indent=2))
        batches.append(str(out_path))
        print(f"  {out_path.name}: {len(chunk)} rows")

    print(f"\n{len(batches)} batches written to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
