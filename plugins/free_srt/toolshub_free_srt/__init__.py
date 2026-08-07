"""Unique import namespace for the FreeSRT plugin.

The implementation remains in the historical ``freesrt`` directory so the
standalone compatibility package and its existing tests continue to work.
"""

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
__path__ = [str(_PACKAGE_DIR), str(_PACKAGE_DIR.parent / "freesrt")]
