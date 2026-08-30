"""`reguard init` — create a minimal reguard.yml template."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..integrations.config import render_default_reguard_yml


def cmd_init(args: argparse.Namespace) -> int:
    out = Path(args.output)
    if out.exists():
        print(f"refusing to overwrite existing file at {out!s}", file=__import__("sys").stderr)
        return 1
    out.write_text(render_default_reguard_yml(), encoding="utf-8")
    print(f"wrote {out}")
    return 0
