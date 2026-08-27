#!/bin/bash
# Import all 28 canonical EU laws into the database.
# Downloads XHTML from EUR-Lex, parses, chunks, and stores.

set -e
cd "$(dirname "$0")/../.."

echo "Importing all 28 canonical laws..."
python3 -c "
import sys
sys.path.insert(0, '.')
from compliance.legal.ingest import ingest_all

stats = ingest_all()
print()
print(f'Result: {stats[\"ok\"]}/{stats[\"total\"]} laws imported, {stats[\"total_chunks\"]} chunks')
print(f'Elapsed: {stats[\"elapsed_seconds\"]:.1f}s')
"