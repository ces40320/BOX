#!/usr/bin/env python3
"""CLI for BoxWrench ExtLoad generation (scaffolding).

Usage (once assets arrive)::

    python run_boxwrench.py --namecode 260306_KTH --condition 7kg_10bpm

Until Approach-5 sources and the box ``.osim`` are present, this CLI only
prints the plan status and exits non-zero.
"""

from __future__ import annotations

import argparse
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
_RUN_TOOLS = os.path.dirname(_THIS)
_CODES = os.path.dirname(_RUN_TOOLS)
for _p in (_CODES, _RUN_TOOLS, _THIS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from boxwrench_config import (  # noqa: E402
    APP_NAME,
    BLOCKED_REASON,
    BOX_OSIM_HINTS,
    FORCE_ZERO_HAND_TORQUE,
    RICTO_WEIGHT_MODE,
    VENDOR_SOURCE_HINTS,
)


def _assets_present() -> dict[str, bool]:
    """Heuristic scan for vendor sources / box osim (not a full integration)."""
    found_py = False
    candidates = [
        os.path.join(_THIS, "_vendor"),
        os.path.join(_RUN_TOOLS, "BoxWrench", "_vendor"),
        os.path.join(os.path.dirname(_CODES), "vendor", "Approach5"),
        os.path.join(_CODES, "vendor", "Approach5"),
    ]
    for c in candidates:
        if not os.path.isdir(c):
            continue
        try:
            names = os.listdir(c)
        except OSError:
            continue
        if any(n.endswith(".py") for n in names if os.path.isfile(os.path.join(c, n))):
            found_py = True
            break

    found_osim = False
    model_dirs = [
        os.path.join(os.path.dirname(_CODES), "OpenSim_Process", "Model"),
        os.path.join(_CODES, "..", "OpenSim_Process", "Model"),
        os.path.join(_THIS, "models"),
    ]
    repo_root = os.path.dirname(_CODES)
    model_dirs = [
        os.path.join(repo_root, "OpenSim_Process", "Model"),
        os.path.join(_THIS, "models"),
    ]
    for d in model_dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in files:
                low = f.lower()
                # Require a dedicated box body .osim (STL halves / WeldBox subject
                # models alone are not the Approach-5 box asset).
                if low.endswith(".osim") and (
                    low.startswith("box") or "boxwrench" in low or "approach5" in low
                ):
                    found_osim = True
                    break
            if found_osim:
                break
        if found_osim:
            break

    return {"approach5_sources": found_py, "box_osim": found_osim}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME}: box wrench → L/R ExtLoad gated by RiCTO timing."
    )
    parser.add_argument("--namecode", default=None, help="SUB_Info namecode")
    parser.add_argument("--condition", default=None, help="e.g. 7kg_10bpm")
    parser.add_argument(
        "--segments",
        default=None,
        help="Comma-separated segments; default all when implemented",
    )
    parser.add_argument(
        "--ricto-weight",
        choices=("smooth", "rect"),
        default=RICTO_WEIGHT_MODE,
        help="RiCTO contact weight (default: smooth)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned paths / status only",
    )
    args = parser.parse_args(argv)

    assets = _assets_present()
    print(f"[{APP_NAME}] scaffolding CLI")
    print(f"  ricto_weight     : {args.ricto_weight}")
    print(f"  zero_hand_torque : {FORCE_ZERO_HAND_TORQUE}")
    print(f"  namecode         : {args.namecode!r}")
    print(f"  condition        : {args.condition!r}")
    print(f"  assets.sources   : {assets['approach5_sources']}")
    print(f"  assets.box_osim  : {assets['box_osim']}")
    print(f"  vendor hints     : {VENDOR_SOURCE_HINTS}")
    print(f"  box osim hints   : {BOX_OSIM_HINTS}")
    print(f"  status           : BLOCKED")
    print(f"  reason           : {BLOCKED_REASON}")

    if args.dry_run:
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
