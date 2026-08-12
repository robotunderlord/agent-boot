"""Allow `python3 -m agentboot ...` to reach the CLI."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
