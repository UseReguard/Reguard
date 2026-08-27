#!/bin/bash
# Initialize the database.
# Creates the data/ directory and SQLite DB, runs schema (creates all tables).

set -e
cd "$(dirname "$0")/../.."

# Ensure dependencies
python3 -c "import sqlalchemy" 2>/dev/null || {
    echo "Installing SQLAlchemy..."
    pip3 install --quiet --break-system-packages sqlalchemy
}

echo "Initializing database..."
python3 -c "
import sys
sys.path.insert(0, '.')
from compliance.db import init_db, DATABASE_URL
print(f'DATABASE_URL={DATABASE_URL}')
init_db()
print('Database initialized.')
"
echo "Done."