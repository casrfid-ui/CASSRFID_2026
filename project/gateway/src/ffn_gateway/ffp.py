"""Import shim: the frame codec lives in project/protocol/python (package `ffp`). This module makes it importable whether the
package was installed or the repository is used in place."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import ffp as _ffp  # noqa: F401
except ImportError:  # in-place repository use
    _root = Path(__file__).resolve().parents[3] / "protocol" / "python"
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    import ffp as _ffp  # noqa: F401

from ffp import frame  # noqa: E402,F401
