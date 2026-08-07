"""Top-level entry point for Tools Hub."""
import os
import sys

# Ensure the project root is on the import path so that
# ``import hub`` resolves correctly when running from source.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hub.launcher import main  # noqa: E402

if __name__ == "__main__":
    main()
