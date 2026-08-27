"""Configuration loaded from environment variables.

DATABASE_URL: SQLAlchemy URL. Defaults to local SQLite in data/ directory.
"""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CHUNKS_DIR = DATA_DIR / "chunks"

DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

# Default to SQLite for local dev. Set DATABASE_URL env var for production.
DEFAULT_DB_URL = f"sqlite:///{DATA_DIR / 'eu_ai_compliance.db'}"

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
EUR_LEX_HTML = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
EUR_LEX_TXT = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"

# Connection pool config
SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true"