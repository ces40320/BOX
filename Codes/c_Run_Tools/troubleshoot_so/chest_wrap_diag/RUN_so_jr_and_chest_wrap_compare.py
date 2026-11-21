"""Rerun SO/JR with A/B subject models and write decision JSON.

Uses the subject-level ``*_ChestFix.osim`` / ``*_ChestVia.osim`` as
``model_path`` for ``prepare_so_setup`` / ``run_so`` / ``run_jr``.

The pipeline writes SO/JR into the canonical ``SO_<app>`` / ``JR_<app>``
folders. For each trial the original segment files are first copied to
``compare/baseline/<cond>_<seg>_<app>/``; after each variant run its outputs
are copied to ``compare/runs/<A|B>/…`` and the originals are restored, so the
canonical results are unchanged when the script finishes. L5–S1 reaction is
reported both absolutely and as the difference from the original result.

Example::

    python RUN_so_jr_and_chest_wrap_compare.py --namecode 260526_PJM --apps MeasuredEHF \\
        --variants A,B --limit 4
    python RUN_so_jr_and_chest_wrap_compare.py --namecode 260526_PJM --decide-only
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from DETECT_muscle_path_wrap_jump import resolve_paths, trouble_cases  # noqa: E402
from opensim_pipeline_handlers import (  # noqa: E402
    prepare_jr_setup,
    prepare_so_setup,
    run_jr,
    run_so,
)
from chest_diag_lib import chest_out_dir, stamped_payload, write_json  # noqa: E402

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


def _run_so_jr(case: dict, model_path: str, *, skip_jr: bool, timeout_s: float | None) -> dict:
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    seg, app = case["segment"], case["app"]
    info = {"so": "ok", "jr": "skipped" if skip_jr else "ok"}
    try:
        prepare_so_setup(cp=cp, rp=rp, seg=seg, app=app, model_path=model_path)
        run_so(cp=cp, rp=rp, seg=seg, app=app, timeout_s=timeout_s, model_path=model_path)
    except Exception as exc:  # noqa: BLE001
        info["so"] = f"fail: {exc}"
        return info
    if not skip_jr:
        try:
            prepare_jr_setup(cp=cp, rp=rp, seg=seg, app=app, model_path=model_path)
            run_jr(cp=cp, rp=rp, seg=seg, app=app, timeout_s=timeout_s, model_path=model_path)
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


def _find_jr_path_in(jr_dir: str, seg: str) -> str:
    if not os.path.isdir(jr_dir):
        return ""
    for pat in (f"*_{seg}_*Reaction*.sto", f"*_{seg}_*.sto"):
        hits = sorted(glob.glob(os.path.join(jr_dir, pat)))
        if hits:
            return hits[0]
    return ""


def _canonical_dirs(case: dict) -> dict[str, str]:
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    section = cp.seg_to_section(case["segment"])
    return {
        "so": cp.so_dir(section, case["app"]),
        "jr": cp.jr_dir(section, case["app"]),
    }


def _seg_files(d: str, seg: str) -> list[str]:
    """Top-level files of one segment in a canonical SO/JR dir."""
    if not os.path.isdir(d):
        return []
    tok = f"_{seg}_"
    return sorted(
        os.path.join(d, f) for f in os.listdir(d)
        if tok in f and os.path.isfile(os.path.join(d, f))
    )


def _copy_verified(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src):
        raise OSError(f"copy verification failed: {src} -> {dst}")


def _snapshot(case: dict, dst_root: str) -> dict[str, list[str]]:
    """Copy current canonical segment files to ``dst_root/{so,jr}/``."""
    seg = case["segment"]
    saved: dict[str, list[str]] = {}
    for kind, d in _canonical_dirs(case).items():
        saved[kind] = []
        for src in _seg_files(d, seg):
            dst = os.path.join(dst_root, kind, os.path.basename(src))
            _copy_verified(src, dst)
            saved[kind].append(dst)
    return saved


def _restore(case: dict, backup_root: str, backup: dict[str, list[str]]) -> None:
    """Put canonical segment files back exactly as backed up.

    Every backup file is verified to exist before any canonical file is
    removed; files the variant run created that were not in the backup are
    removed only after the backup has been copied back.
    """
    seg = case["segment"]
    for kind, files in backup.items():
        for b in files:
            if not os.path.isfile(b):
                raise FileNotFoundError(f"backup missing, refusing to restore: {b}")
    for kind, d in _canonical_dirs(case).items():
        keep = set()
        for b in backup.get(kind, []):
            dst = os.path.join(d, os.path.basename(b))
            _copy_verified(b, dst)
            keep.add(os.path.normcase(dst))
        for f in _seg_files(d, seg):
            if os.path.normcase(f) not in keep:
                os.remove(f)


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
    cases = trouble_cases(
        namecode=args.namecode, condition=args.condition,
        segments=segs, apps=apps,
    )[: max(1, args.limit)]
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
            dirs = _canonical_dirs(case)
            if args.dry_run:
                trials.append({
                    **case, "status": "dry_run", "model": model,
                    "would_backup": {k: _seg_files(d, case["segment"]) for k, d in dirs.items()},
                })
                continue
            backup_root = os.path.join(cmp_dir, "baseline", tag)
            run_root = os.path.join(cmp_dir, "runs", var, tag)
            if os.path.isdir(backup_root) and any(os.scandir(backup_root)):
                backup = {
                    k: sorted(glob.glob(os.path.join(backup_root, k, "*")))
                    for k in ("so", "jr")
                }
            else:
                backup = _snapshot(case, backup_root)
            base_jr = _find_jr_path_in(os.path.join(backup_root, "jr"), case["segment"])
            base_summary = _jr_summary(base_jr) if base_jr else {}

            status = _run_so_jr(
                case, model, skip_jr=args.skip_jr, timeout_s=args.timeout,
            )
            run_files = _snapshot(case, run_root)
            _restore(case, backup_root, backup)

            var_jr = _find_jr_path_in(os.path.join(run_root, "jr"), case["segment"])
            var_summary = _jr_summary(var_jr) if var_jr else {}
            trials.append({
                **case,
                "status": status,
                "model": model,
                "baseline_jr_path": base_jr,
                "jr_path": var_jr,
                "baseline_jr_summary": base_summary,
                "jr_summary": var_summary,
                "jr_vs_baseline": (
                    _relative_diff(var_summary, base_summary)
                    if var_summary and base_summary else {}
                ),
                "run_files": run_files,
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
