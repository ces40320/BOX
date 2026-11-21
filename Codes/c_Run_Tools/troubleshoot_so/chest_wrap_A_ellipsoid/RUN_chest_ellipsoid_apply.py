"""Apply saved Chest ellipsoid params to a subject model (or re-emit ChestFix).

Example::

    python RUN_chest_ellipsoid_apply.py --namecode 260526_PJM \\
        --params-json path/to/chest_params_SUB8.json \\
        --baseline-osim path/to/SUB8_Scaled.osim
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

import numpy as np  # noqa: E402

from PATH_RULE import ResultPaths  # noqa: E402
from pipeline_rules import resolve_model_path  # noqa: E402
from wrap_detect_lib import import_opensim  # noqa: E402
from chest_diag_lib import chest_out_dir  # noqa: E402
from chest_ellipsoid_opt_lib import (  # noqa: E402
    EllipsoidParamVec,
    write_candidate_osim,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--namecode", required=True)
    p.add_argument("--params-json", default=None)
    p.add_argument("--baseline-osim", default=None)
    p.add_argument("--out-osim", default=None)
    p.add_argument("--apps", default="MeasuredEHF")
    args = p.parse_args()

    sub = ResultPaths(args.namecode).sub_label
    params_path = args.params_json or os.path.join(
        chest_out_dir(args.namecode, "A"), f"chest_params_{sub}.json",
    )
    if not os.path.isfile(params_path):
        print(f"missing params: {params_path}")
        return 1
    with open(params_path, encoding="utf-8") as f:
        payload = json.load(f)
    bp = payload.get("best_params") or payload.get("params") or {}
    params = EllipsoidParamVec(
        radii_scale=np.asarray(bp.get("radii_scale", [1, 1, 1]), dtype=float),
        translation_delta=np.asarray(
            bp.get("translation_delta", [0, 0, 0]), dtype=float,
        ),
        rotation_delta=np.asarray(bp.get("rotation_delta", [0, 0, 0]), dtype=float),
        quadrant_mode=str(bp.get("quadrant_mode", "keep")),
    )

    baseline = args.baseline_osim
    if not baseline:
        rp = ResultPaths(args.namecode)
        # pick first condition folder for resolve; model is shared scaled
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
        print(f"missing baseline osim: {baseline}")
        return 1

    out = args.out_osim or os.path.join(
        chest_out_dir(args.namecode, "A"), f"{sub}_ChestFix.osim",
    )
    osim = import_opensim()
    info = write_candidate_osim(osim, baseline, out, params)
    print(f"[A-apply] → {out}")
    print(json.dumps(info["params"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
