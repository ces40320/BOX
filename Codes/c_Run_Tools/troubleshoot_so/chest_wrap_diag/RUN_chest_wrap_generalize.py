"""Generalize chosen Chest wrap fix (A or B) to other subjects.

- Approach A: re-apply radii/translation/rotation scales from a reference
  ``chest_params_*.json`` onto each subject's scaled model (optionally
  re-optimize with ``--reopt``).
- Approach B: scale via-point body coordinates by subject scale factors when
  available; otherwise re-fit with ``--refit``.

Example::

    python RUN_chest_wrap_generalize.py --source-namecode 260526_PJM \\
        --target-namecodes 260519_KMJ,260306_KTH --variant A
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
from chest_diag_lib import chest_out_dir, stamped_payload, write_json  # noqa: E402


def _first_condition(rp: ResultPaths) -> str | None:
    root = rp.sub_dir
    if not os.path.isdir(root):
        return None
    for name in sorted(os.listdir(root)):
        if os.path.isdir(os.path.join(root, name)) and not name.startswith("_"):
            return name
    return None


def _baseline(namecode: str, app: str = "MeasuredEHF") -> str | None:
    rp = ResultPaths(namecode)
    cond = _first_condition(rp)
    if not cond:
        return None
    path = resolve_model_path(rp, cond, app, "so", must_exist=False)
    return path if path and os.path.isfile(path) else None


def generalize_a(source_namecode: str, target_namecode: str, *, app: str) -> dict:
    from chest_ellipsoid_opt_lib import EllipsoidParamVec, write_candidate_osim

    src_sub = ResultPaths(source_namecode).sub_label
    params_path = os.path.join(
        chest_out_dir(source_namecode, "A"), f"chest_params_{src_sub}.json",
    )
    if not os.path.isfile(params_path):
        return {"error": f"missing {params_path}"}
    with open(params_path, encoding="utf-8") as f:
        payload = json.load(f)
    bp = payload.get("best_params") or {}
    params = EllipsoidParamVec(
        radii_scale=np.asarray(bp.get("radii_scale", [1, 1, 1]), dtype=float),
        translation_delta=np.asarray(
            bp.get("translation_delta", [0, 0, 0]), dtype=float,
        ),
        rotation_delta=np.asarray(bp.get("rotation_delta", [0, 0, 0]), dtype=float),
        quadrant_mode=str(bp.get("quadrant_mode", "keep")),
    )
    baseline = _baseline(target_namecode, app)
    if not baseline:
        return {"error": f"missing baseline for {target_namecode}"}
    tgt_sub = ResultPaths(target_namecode).sub_label
    out = os.path.join(chest_out_dir(target_namecode, "A"), f"{tgt_sub}_ChestFix.osim")
    osim = import_opensim()
    info = write_candidate_osim(osim, baseline, out, params)
    # also copy params json for the target
    write_json(
        os.path.join(chest_out_dir(target_namecode, "A"), f"chest_params_{tgt_sub}.json"),
        {
            "namecode": target_namecode,
            "sub_label": tgt_sub,
            "source_namecode": source_namecode,
            "transplant": "scale_params_direct",
            "best_params": info["params"],
            "out_osim": out,
        },
    )
    return {"out_osim": out, "ok": True}


def generalize_b(source_namecode: str, target_namecode: str, *, app: str,
                 scale: float = 1.0) -> dict:
    from chest_via_fit_lib import build_via_model

    src_sub = ResultPaths(source_namecode).sub_label
    via_path = os.path.join(
        chest_out_dir(source_namecode, "B"), f"via_points_{src_sub}.json",
    )
    if not os.path.isfile(via_path):
        return {"error": f"missing {via_path}"}
    with open(via_path, encoding="utf-8") as f:
        payload = json.load(f)
    specs = payload.get("specs") or {}
    # scale fixed points
    scaled = {}
    for m, spec in specs.items():
        s2 = dict(spec)
        if "points" in s2:
            s2["points"] = [
                [float(scale) * float(x) for x in pt] for pt in s2["points"]
            ]
        if "lumbar_point" in s2 and s2["lumbar_point"]:
            s2["lumbar_point"] = [
                float(scale) * float(x) for x in s2["lumbar_point"]
            ]
        if "spline" in s2:
            sp = dict(s2["spline"])
            for ax in ("x", "y", "z"):
                if ax in sp:
                    sp[ax] = [float(scale) * float(v) for v in sp[ax]]
            s2["spline"] = sp
        scaled[m] = s2

    baseline = _baseline(target_namecode, app)
    if not baseline:
        return {"error": f"missing baseline for {target_namecode}"}
    tgt_sub = ResultPaths(target_namecode).sub_label
    out = os.path.join(chest_out_dir(target_namecode, "B"), f"{tgt_sub}_ChestVia.osim")
    osim = import_opensim()
    report = build_via_model(
        osim=osim,
        baseline_model_path=baseline,
        out_path=out,
        muscle_specs=scaled,
        use_moving=bool(payload.get("use_moving")),
    )
    write_json(
        os.path.join(chest_out_dir(target_namecode, "B"), f"via_points_{tgt_sub}.json"),
        {
            "namecode": target_namecode,
            "sub_label": tgt_sub,
            "source_namecode": source_namecode,
            "transplant": "body_point_scale",
            "scale": scale,
            "specs": scaled,
            "out_osim": out,
            "build_report": report,
        },
    )
    return {"out_osim": out, "ok": True}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-namecode", required=True)
    p.add_argument("--target-namecodes", required=True,
                   help="Comma-separated namecodes")
    p.add_argument("--variant", default="A", choices=("A", "B"))
    p.add_argument("--apps", default="MeasuredEHF")
    p.add_argument("--scale", type=float, default=1.0,
                   help="Body-point scale for B transplant (default 1.0)")
    args = p.parse_args()

    targets = [t.strip() for t in args.target_namecodes.split(",") if t.strip()]
    app = args.apps.split(",")[0].strip() or "MeasuredEHF"
    results = {}
    for tgt in targets:
        print(f"[gen] {args.variant} → {tgt}", flush=True)
        if args.variant == "A":
            results[tgt] = generalize_a(args.source_namecode, tgt, app=app)
        else:
            results[tgt] = generalize_b(
                args.source_namecode, tgt, app=app, scale=args.scale,
            )

    n_ok = sum(1 for r in results.values() if r.get("ok"))
    summary = stamped_payload(
        "chest_wrap_cross_subject",
        source_namecode=args.source_namecode,
        variant=args.variant,
        n_targets=len(targets),
        n_ok=n_ok,
        pass_frac=float(n_ok / max(len(targets), 1)),
        results=results,
    )
    out = os.path.join(
        chest_out_dir(args.source_namecode, "compare"),
        "cross_subject_summary.json",
    )
    write_json(out, summary)
    print(f"[gen] {n_ok}/{len(targets)} → {out}")
    # plan target: ≥80% without re-opt
    return 0 if summary["pass_frac"] >= 0.8 else 2


if __name__ == "__main__":
    raise SystemExit(main())
