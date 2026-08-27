#!/usr/bin/env python3
import sys
print("DEBUG sys.path:", sys.path[:5], file=sys.stderr)
import src  # type: ignore
print("DEBUG src loaded:", src, file=sys.stderr)
from src import db
print("DEBUG db loaded:", db, file=sys.stderr)
