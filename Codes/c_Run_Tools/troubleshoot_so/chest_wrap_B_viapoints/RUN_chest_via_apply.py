"""Rebuild ChestVia.osim from saved via_points_*.json.

Example::

    python RUN_chest_via_apply.py --namecode 260526_PJM
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from PATH_RULE import ResultPaths  # noqa: E402
from pipeline_rules import resolve_model_path  # noqa: E402
from wrap_detect_lib import import_opensim  # noqa: E402
from chest_diag_lib import chest_out_dir  # noqa: E402
from chest_via_fit_lib import build_via_model  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--namecode", required=True)
    p.add_argument("--via-json", default=None)
    p.add_argument("--baseline-osim", default=None)
    p.add_argument("--out-osim", default=None)
    p.add_argument("--apps", default="MeasuredEHF")
    args = p.parse_args()

    sub = ResultPaths(args.namecode).sub_label
    via_path = args.via_json or os.path.join(
        chest_out_dir(args.namecode, "B"), f"via_points_{sub}.json",
    )
    if not os.path.isfile(via_path):
        print(f"missing {via_path}")
        return 1
    with open(via_path, encoding="utf-8") as f:
        payload = json.load(f)

    baseline = args.baseline_osim
    if not baseline:
        rp = ResultPaths(args.namecode)
        app = args.apps.split(",")[0].strip() or "MeasuredEHF"
        cond = None
        root = rp.sub_dir
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                if os.path.isdir(os.path.join(root, name)) and not name.startswith("_"):
                    cond = name
                    break
        if cond:
            baseline = resolve_model_path(rp, cond, app, "so", must_exist=False)
    if not baseline or not os.path.isfile(baseline):
        print(f"missing baseline: {baseline}")
        return 1

    out = args.out_osim or os.path.join(
        chest_out_dir(args.namecode, "B"), f"{sub}_ChestVia.osim",
    )
    osim = import_opensim()
    report = build_via_model(
        osim=osim,
        baseline_model_path=baseline,
        out_path=out,
        muscle_specs=payload.get("specs") or {},
        use_moving=bool(payload.get("use_moving")),
    )
    print(f"[B-apply] → {out}")
    print(json.dumps(report.get("muscles", {}), indent=2)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
