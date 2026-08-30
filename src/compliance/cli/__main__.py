"""Allow `python -m compliance.cli`."""
from .main import main
import sys

if __name__ == "__main__":
    sys.exit(main())
