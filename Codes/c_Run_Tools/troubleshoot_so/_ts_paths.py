"""``sys.path`` bootstrap for SO troubleshooting scripts.

Scripts here are run as files (``python troubleshoot_so/<approach>/x.py``),
not as a package, so each one inserts ``troubleshoot_so/`` and imports this
module. Afterwards the official pipeline modules (``PATH_RULE``,
``opensim_pipeline_handlers``, ``pipeline_rules``, …) and every approach
sub-folder are importable by flat module name.
"""

from __future__ import annotations

import os
import sys

TS_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_TOOLS_DIR = os.path.dirname(TS_DIR)
CODES_DIR = os.path.dirname(RUN_TOOLS_DIR)

APPROACHES = (
    "rerun_freeze",
    "wrap_gapfill",
    "wrap_fbp",
    "diagnosis",
    "chest_wrap_diag",
    "chest_wrap_A_ellipsoid",
    "chest_wrap_B_viapoints",
)

for _p in (
    CODES_DIR,
    RUN_TOOLS_DIR,
    TS_DIR,
    *(os.path.join(TS_DIR, a) for a in APPROACHES),
):
    if _p not in sys.path:
        sys.path.append(_p)
