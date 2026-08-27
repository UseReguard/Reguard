#!/usr/bin/env bash
# Convenience wrapper around `python -m compliance.corpus`.
# Sets PYTHONPATH so the user does not have to.
#
# Usage:
#   ./scripts/run_repo_corpus.sh discover --limit 5000
#   ./scripts/run_repo_corpus.sh stats
#   ./scripts/run_repo_corpus.sh list --status candidate
#   ./scripts/run_repo_corpus.sh refresh --limit 20

set -euo pipefail
cd "$(dirname "$0")/.."
exec env PYTHONPATH=src python3 -m compliance.corpus "$@"
