"""Rerun SO/JR with A/B subject models and write decision JSON.

Uses the subject-level ``*_ChestFix.osim`` / ``*_ChestVia.osim`` as
``model_path`` for ``prepare_so_setup`` / ``run_so`` / ``run_jr``.

Candidate SO/JR outputs (and their setup XMLs) go to
``SO_<app>/troubleshoot_so/chest_wrap_geometry_fitting/`` (variant A) and
``JR_<app>/troubleshoot_so/chest_wrap_geometry_fitting/`` (variant A). The canonical ``SO_<app>`` /
``JR_<app>`` files are only read, as the baseline for the L5–S1 reaction
difference.

Example::

    python RUN_so_jr_and_chest_wrap_compare.py --namecode 260526_PJM --apps MeasuredEHF \\
        --variants A,B --limit 4
    python RUN_so_jr_and_chest_wrap_compare.py --namecode 260526_PJM --decide-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from PATH_RULE import TROUBLESHOOT_SO_DIRNAME, ConditionPaths, ResultPaths  # noqa: E402
from DETECT_muscle_path_wrap_jump import resolve_paths  # noqa: E402
from opensim_pipeline_handlers import (  # noqa: E402
    prepare_jr_setup,
    prepare_so_setup,
    run_jr,
    run_so,
)
from chest_diag_lib import (  # noqa: E402
    add_case_source_args,
    chest_out_dir,
    collect_cases,
    spread_cases,
    stamped_payload,
    write_json,
)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# L5–S1 IVD reaction columns (body frame), matching _tmp_plot.py
JR_COLS = {
    "fx": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fx",
    "fy": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fy",
    "fz": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fz",
}


def _subject_model(namecode: str, variant: str) -> str:
    sub = ResultPaths(namecode).sub_label
    if variant.upper() == "A":
        return os.path.join(chest_out_dir(namecode, "A"), f"{sub}_ChestFix.osim")
    if variant.upper() == "B":
        return os.path.join(chest_out_dir(namecode, "B"), f"{sub}_ChestVia.osim")
    raise ValueError(variant)


def _variant_dirs(case: dict, variant: str) -> dict[str, str]:
    """Canonical and candidate SO/JR folders for one trial."""
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    section = cp.seg_to_section(case["segment"])
    approach = "chest_wrap_geometry_fitting" if variant.upper() == "A" else f"chest_wrap_{variant}"
    so_canon = cp.so_dir(section, case["app"])
    jr_canon = cp.jr_dir(section, case["app"])
    return {
        "so_canon": so_canon,
        "jr_canon": jr_canon,
        "so": os.path.join(so_canon, TROUBLESHOOT_SO_DIRNAME, approach),
        "jr": os.path.join(jr_canon, TROUBLESHOOT_SO_DIRNAME, approach),
    }


def _run_so_jr(case: dict, model_path: str, dirs: dict[str, str], *,
               skip_jr: bool, timeout_s: float | None) -> dict:
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    seg, app = case["segment"], case["app"]
    info = {"so": "ok", "jr": "skipped" if skip_jr else "ok"}
    os.makedirs(dirs["so"], exist_ok=True)
    try:
        prepare_so_setup(cp=cp, rp=rp, seg=seg, app=app, model_path=model_path,
                         results_dir=dirs["so"])
        run_so(cp=cp, rp=rp, seg=seg, app=app, timeout_s=timeout_s,
               model_path=model_path, results_dir=dirs["so"])
    except Exception as exc:  # noqa: BLE001
        info["so"] = f"fail: {exc}"
        return info
    if not skip_jr:
        os.makedirs(dirs["jr"], exist_ok=True)
        try:
            prepare_jr_setup(cp=cp, rp=rp, seg=seg, app=app, model_path=model_path,
                             results_dir=dirs["jr"], so_results_dir=dirs["so"])
            run_jr(cp=cp, rp=rp, seg=seg, app=app, timeout_s=timeout_s,
                   model_path=model_path, results_dir=dirs["jr"])
        except Exception as exc:  # noqa: BLE001
            info["jr"] = f"fail: {exc}"
    return info


def _jr_summary(path: str) -> dict:
    if not os.path.isfile(path):
        return {"error": "missing"}
    try:
        from optimization.ricto_io import read_opensim_storage
        df, _ = read_opensim_storage(path)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    out = {}
    tcol = "time" if "time" in df.columns else "Time"
    t = df[tcol].to_numpy(dtype=float)
    t0, t1 = float(t[0]), float(t[-1])
    dur = max(t1 - t0, 1e-12)
    # high-load window ~30–45% cycle
    cp = 100.0 * (t - t0) / dur
    hi = (cp >= 30.0) & (cp <= 45.0)
    for key, col in JR_COLS.items():
        if col not in df.columns:
            out[key] = None
            continue
        y = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        out[key] = {
            "mean": float(np.nanmean(y)),
            "mean_hi30_45": float(np.nanmean(y[hi])) if hi.any() else float("nan"),
            "peak_abs": float(np.nanmax(np.abs(y))),
        }
    return out


def _jr_sto(case: dict, jr_dir: str) -> str:
    """Canonical-named child-frame JR file for this trial inside ``jr_dir``."""
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    name = os.path.basename(cp.jr_path(case["segment"], case["app"], ""))
    path = os.path.join(jr_dir, name)
    return path if os.path.isfile(path) else ""


def _relative_diff(var: dict, base: dict) -> dict:
    out = {}
    for key in JR_COLS:
        v, b = var.get(key), base.get(key)
        if not isinstance(v, dict) or not isinstance(b, dict):
            out[key] = None
            continue
        row = {}
        for stat in ("mean", "mean_hi30_45", "peak_abs"):
            bv, vv = b.get(stat), v.get(stat)
            if bv is None or vv is None or not np.isfinite(bv) or not np.isfinite(vv):
                row[stat] = None
                continue
            row[f"{stat}_diff"] = float(vv - bv)
            row[f"{stat}_rel"] = float((vv - bv) / abs(bv)) if abs(bv) > 1e-9 else None
        out[key] = row
    return out


def decide(namecode: str) -> dict:
    """Pick A vs B from eval JSON + optional SO/JR compare records."""
    sub = ResultPaths(namecode).sub_label
    cmp_dir = chest_out_dir(namecode, "compare")
    evals = {}
    for var in ("A", "B"):
        path = os.path.join(cmp_dir, f"eval_{sub}_{var}.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                evals[var] = json.load(f)
    sojr_path = os.path.join(cmp_dir, f"so_jr_{sub}.json")
    sojr = {}
    if os.path.isfile(sojr_path):
        with open(sojr_path, encoding="utf-8") as f:
            sojr = json.load(f)

    decision = {
        "preferred": "A",
        "reason": [],
        "hard_pass": {},
    }
    for var, ev in evals.items():
        decision["hard_pass"][var] = bool(ev.get("subject_pass"))
    # both hard-pass → prefer smaller model change (A), else better MA
    a_ok = decision["hard_pass"].get("A", False)
    b_ok = decision["hard_pass"].get("B", False)
    if a_ok and not b_ok:
        decision["preferred"] = "A"
        decision["reason"].append("only A hard-pass")
    elif b_ok and not a_ok:
        decision["preferred"] = "B"
        decision["reason"].append("only B hard-pass")
    elif a_ok and b_ok:
        decision["preferred"] = "A"
        decision["reason"].append("both pass; prefer A (smaller model change)")
    else:
        # neither — still prefer A for geometry retention of LD wraps
        decision["preferred"] = "A"
        decision["reason"].append("neither hard-pass; default A, consider A+local B")
        decision["hybrid_hint"] = "A_plus_local_B"

    if sojr.get("variants"):
        scores = {}
        for var, payload in sojr["variants"].items():
            errs = []
            for trial in payload.get("trials", []):
                d = (trial.get("jr_vs_baseline") or {}).get("fy") or {}
                r = d.get("mean_rel")
                if r is not None:
                    errs.append(abs(float(r)))
            scores[var] = float(np.mean(errs)) if errs else None
        decision["jr_fy_mean_abs_rel_diff_vs_baseline"] = scores
        if a_ok and b_ok:
            sa, sb = scores.get("A"), scores.get("B")
            if sa is not None and sb is not None and sb < sa:
                decision["note_jr"] = "B closer to baseline L5-S1 compression"

    out = stamped_payload(
        "chest_wrap_decision",
        namecode=namecode,
        sub_label=sub,
        decision=decision,
        evals_present=list(evals.keys()),
        sojr_present=bool(sojr),
    )
    path = os.path.join(cmp_dir, f"decision_{sub}.json")
    write_json(path, out)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--namecode", required=True)
    p.add_argument("--apps", default="MeasuredEHF")
    p.add_argument("--condition", default=None)
    p.add_argument("--seg", default=None)
    p.add_argument("--variants", default="A,B")
    p.add_argument("--limit", type=int, default=4)
    add_case_source_args(p)
    p.add_argument("--skip-jr", action="store_true")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--decide-only", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.decide_only:
        out = decide(args.namecode)
        print(json.dumps(out["decision"], indent=2))
        return 0

    apps = {a.strip() for a in args.apps.split(",") if a.strip()}
    segs = {s.strip() for s in (args.seg or "").split(",") if s.strip()} or None
    cases = collect_cases(
        args.namecode,
        from_wrap_fbp=args.from_wrap_fbp,
        from_trouble=args.from_trouble,
        all_ik=args.all_ik,
        condition=args.condition,
        segments=segs,
        apps=apps,
    )
    cases = spread_cases(cases, max(1, args.limit))
    variants = [v.strip().upper() for v in args.variants.split(",") if v.strip()]

    sub = ResultPaths(args.namecode).sub_label
    cmp_dir = chest_out_dir(args.namecode, "compare")
    variant_payloads: dict[str, Any] = {}

    for var in variants:
        model = _subject_model(args.namecode, var)
        if not os.path.isfile(model):
            print(f"[compare] missing {model}")
            variant_payloads[var] = {"error": f"missing {model}"}
            continue
        trials = []
        for case in cases:
            tag = f"{case['condition']}_{case['segment']}_{case['app']}"
            print(f"[compare] {var} {tag}", flush=True)
            dirs = _variant_dirs(case, var)
            if args.dry_run:
                trials.append({
                    **case, "status": "dry_run", "model": model,
                    "so_out": dirs["so"], "jr_out": dirs["jr"],
                })
                continue
            status = _run_so_jr(
                case, model, dirs, skip_jr=args.skip_jr, timeout_s=args.timeout,
            )
            base_jr = _jr_sto(case, dirs["jr_canon"])
            var_jr = _jr_sto(case, dirs["jr"])
            base_summary = _jr_summary(base_jr) if base_jr else {}
            var_summary = _jr_summary(var_jr) if var_jr else {}
            trials.append({
                **case,
                "status": status,
                "model": model,
                "so_out": dirs["so"],
                "jr_out": dirs["jr"],
                "baseline_jr_path": base_jr,
                "jr_path": var_jr,
                "baseline_jr_summary": base_summary,
                "jr_summary": var_summary,
                "jr_vs_baseline": (
                    _relative_diff(var_summary, base_summary)
                    if var_summary and base_summary else {}
                ),
            })
        variant_payloads[var] = {"model": model, "trials": trials}

    payload = stamped_payload(
        "chest_wrap_so_jr",
        namecode=args.namecode,
        sub_label=sub,
        variants=variant_payloads,
    )
    out = os.path.join(cmp_dir, f"so_jr_{sub}.json")
    write_json(out, payload)
    print(f"[compare] → {out}")
    dec = decide(args.namecode)
    print(f"[decision] preferred={dec['decision']['preferred']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
