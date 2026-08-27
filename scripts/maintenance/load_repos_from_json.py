"""Load repos from JSON file into PostgreSQL (re-run insert without re-collecting)."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("load_repos")

# Reuse the insert function from collect_eu_ai_repos
from collect_eu_ai_repos import insert_to_postgres  # noqa: E402

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/eu_ai_repos.json"
    repos = json.loads(Path(json_path).read_text())
    log.info(f"Loaded {len(repos)} repos from {json_path}")
    insert_to_postgres(repos)
