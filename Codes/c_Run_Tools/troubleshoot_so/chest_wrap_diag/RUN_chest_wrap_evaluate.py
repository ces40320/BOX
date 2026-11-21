"""Common A/B evaluation: jumps, length & moment-arm RMSE, smoothness.

Compares a candidate model against the original GeometryPath on frames that
were ``ok`` in the diagnosis CSV (or re-scans IK if ``--rescan``).

Examples::

    python RUN_chest_wrap_evaluate.py --namecode 260526_PJM --variant A \\
        --candidate-osim path/to/SUB8_ChestFix.osim
    python RUN_chest_wrap_evaluate.py --self-test
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from PATH_RULE import ResultPaths  # noqa: E402
from DETECT_muscle_path_wrap_jump import resolve_paths  # noqa: E402
from wrap_detect_lib import (  # noqa: E402
    JUMP_DL_M,
    _apply_ik_row,
    import_opensim,
    list_chest_path_muscles,
)
from chest_diag_lib import (  # noqa: E402
    L5S1_COORDS,
    chest_out_dir,
    length_jump_count,
    numerical_moment_arms,
    rmse,
    stamped_payload,
    write_json,
)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Plan thresholds (tunable after diagnosis).
THRESH_LENGTH_RMSE_M = 0.002
THRESH_LENGTH_MAX_M = 0.005
THRESH_MA_RMSE_M = 0.003
THRESH_MA_REL = 0.10


def _ik_in_degrees(meta: dict) -> bool:
    v = str(meta.get("inDegrees") or meta.get("in_degrees") or "").strip().lower()
    if v in ("yes", "true", "1"):
        return True
    if v in ("no", "false", "0"):
        return False
    return True


def _load_ok_times_by_trial(namecode: str) -> dict[tuple, set[float]]:
    """Map (cond, seg, app) → set of ok times from diagnosis CSVs."""
    diag_dir = chest_out_dir(namecode, "diag")
    paths = sorted(glob.glob(os.path.join(diag_dir, "chest_diag_*.csv")))
    paths = [p for p in paths if "chest_diag_all_" not in os.path.basename(p)]
    out: dict[tuple, set[float]] = {}
    for pth in paths:
        df = pd.read_csv(pth)
        if df.empty:
            continue
        for (cond, seg, app), g in df.groupby(["condition", "segment", "app"]):
            ok = g[g["failure_type"] == "ok"]
            key = (str(cond), str(seg), str(app))
            out.setdefault(key, set()).update(
                float(t) for t in ok["time_s"].tolist()
            )
    return out


def evaluate_pair(
    *,
    osim,
    baseline_model: str,
    candidate_model: str,
    ik_path: str,
    ok_times: set[float] | None,
    muscles: list[str] | None = None,
    frame_stride: int = 2,
    time_tol: float = 1e-4,
) -> dict:
    from optimization.ricto_io import read_opensim_storage

    m0 = osim.Model(baseline_model)
    s0 = m0.initSystem()
    m1 = osim.Model(candidate_model)
    s1 = m1.initSystem()
    names = muscles or list_chest_path_muscles(m0)
    names = [n for n in names if m1.getMuscles().contains(n)]
    ik_df, meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    indeg = _ik_in_degrees(meta)
    times = ik_df[tcol].to_numpy(dtype=float)

    len0 = {m: [] for m in names}
    len1 = {m: [] for m in names}
    ma0 = {m: {c: [] for c in L5S1_COORDS} for m in names}
    ma1 = {m: {c: [] for c in L5S1_COORDS} for m in names}
    t_used: list[float] = []

    for fi, (_, row) in enumerate(ik_df.iterrows()):
        if fi % max(1, frame_stride) != 0:
            continue
        t = float(row[tcol])
        if ok_times is not None:
            if not any(abs(t - ot) <= time_tol for ot in ok_times):
                # still collect full series for jump count on candidate
                pass
        _apply_ik_row(osim, m0, s0, row, indeg)
        _apply_ik_row(osim, m1, s1, row, indeg)
        t_used.append(t)
        for m in names:
            mus0 = m0.getMuscles().get(m)
            mus1 = m1.getMuscles().get(m)
            try:
                l0 = float(mus0.getGeometryPath().getLength(s0))
            except Exception:  # noqa: BLE001
                l0 = float("nan")
            try:
                l1 = float(mus1.getGeometryPath().getLength(s1))
            except Exception:  # noqa: BLE001
                l1 = float("nan")
            len0[m].append(l0)
            len1[m].append(l1)
            use_ma = ok_times is None or any(abs(t - ot) <= time_tol for ot in ok_times)
            if use_ma:
                a0 = numerical_moment_arms(osim, m0, s0, mus0)
                a1 = numerical_moment_arms(osim, m1, s1, mus1)
                for c in L5S1_COORDS:
                    ma0[m][c].append(a0.get(c, float("nan")))
                    ma1[m][c].append(a1.get(c, float("nan")))

    per_muscle: dict = {}
    total_jumps = 0
    hard_fail = False
    for m in names:
        a = np.asarray(len0[m], dtype=float)
        b = np.asarray(len1[m], dtype=float)
        # good-frame RMSE: where ok_times match — approximate by finite both
        if ok_times is not None:
            mask = np.array([
                any(abs(t - ot) <= time_tol for ot in ok_times) for t in t_used
            ], dtype=bool)
        else:
            mask = np.isfinite(a) & np.isfinite(b)
        lr = rmse(a[mask], b[mask]) if mask.any() else float("nan")
        lmax = float(np.nanmax(np.abs(a[mask] - b[mask]))) if mask.any() else float("nan")
        # smoothness: 2nd diff of candidate
        if len(b) >= 3 and np.isfinite(b).sum() >= 3:
            d2 = np.diff(b, n=2)
            smooth = float(np.nanpercentile(np.abs(d2), 99))
        else:
            smooth = float("nan")
        nj = length_jump_count(b, np.asarray(t_used, dtype=float))
        total_jumps += nj
        ma_rmse = {}
        ma_ok = True
        for c in L5S1_COORDS:
            x = np.asarray(ma0[m][c], dtype=float)
            y = np.asarray(ma1[m][c], dtype=float)
            r = rmse(x, y)
            ma_rmse[c] = r
            ref = float(np.nanmean(np.abs(x))) if np.isfinite(x).any() else float("nan")
            if np.isfinite(r):
                if r > THRESH_MA_RMSE_M and (
                    not np.isfinite(ref) or r > THRESH_MA_REL * max(ref, 1e-6)
                ):
                    ma_ok = False
        length_ok = (
            (not np.isfinite(lr) or lr <= THRESH_LENGTH_RMSE_M)
            and (not np.isfinite(lmax) or lmax <= THRESH_LENGTH_MAX_M)
        )
        if nj > 0 or not length_ok or not ma_ok:
            hard_fail = True
        per_muscle[m] = {
            "length_rmse_m": lr,
            "length_max_abs_m": lmax,
            "n_jumps": nj,
            "smooth_d2_p99": smooth,
            "moment_arm_rmse_m": ma_rmse,
            "length_ok": bool(length_ok),
            "moment_arm_ok": bool(ma_ok),
            "jumps_ok": nj == 0,
        }

    return {
        "baseline_model": baseline_model,
        "candidate_model": candidate_model,
        "ik_path": ik_path,
        "n_frames_eval": len(t_used),
        "total_jumps": int(total_jumps),
        "pass_hard": bool(total_jumps == 0 and not hard_fail),
        "thresholds": {
            "length_rmse_m": THRESH_LENGTH_RMSE_M,
            "length_max_m": THRESH_LENGTH_MAX_M,
            "ma_rmse_m": THRESH_MA_RMSE_M,
            "ma_rel": THRESH_MA_REL,
        },
        "per_muscle": per_muscle,
    }


def run_self_test() -> None:
    a = np.array([1.0, 1.0, 1.0])
    b = np.array([1.0, 1.002, 1.0])
    assert abs(rmse(a, b) - np.sqrt(((0.002) ** 2) / 3)) < 1e-9
    L = np.array([0.5, 0.5, 0.76, 0.76, 0.5])
    assert length_jump_count(L, np.arange(5) * 0.01) >= 1
    print("[eval self-test] OK")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--namecode", default=None)
    p.add_argument("--variant", default="A", help="A|B|label for output name")
    p.add_argument("--candidate-osim", default=None)
    p.add_argument("--baseline-osim", default=None)
    p.add_argument("--condition", default=None)
    p.add_argument("--seg", default=None)
    p.add_argument("--apps", default="MeasuredEHF")
    p.add_argument("--frame-stride", type=int, default=2)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        run_self_test()
        return 0
    if not args.namecode or not args.candidate_osim:
        p.error("--namecode and --candidate-osim required (or --self-test)")
    if not os.path.isfile(args.candidate_osim):
        print(f"missing candidate: {args.candidate_osim}")
        return 1

    apps = {a.strip() for a in args.apps.split(",") if a.strip()}
    segs = {s.strip() for s in (args.seg or "").split(",") if s.strip()} or None
    ok_map = _load_ok_times_by_trial(args.namecode)

    # Build case list from diagnosis CSVs keys, else trouble
    from DETECT_muscle_path_wrap_jump import trouble_cases

    cases = trouble_cases(
        namecode=args.namecode,
        condition=args.condition,
        segments=segs,
        apps=apps,
    )
    if not cases:
        from chest_diag_lib import iter_subject_ik_cases
        cases = iter_subject_ik_cases(
            args.namecode, apps=apps,
            conditions=[args.condition] if args.condition else None,
            segments=segs,
        )
    if args.limit:
        cases = cases[: args.limit]

    osim = import_opensim()
    trial_results = []
    for case in cases:
        base, ik = resolve_paths(case)
        if args.baseline_osim:
            base = args.baseline_osim
        if not os.path.isfile(base) or not os.path.isfile(ik):
            trial_results.append({**case, "error": "missing base/ik"})
            continue
        key = (case["condition"], case["segment"], case["app"])
        ok_times = ok_map.get(key)
        print(f"[eval] {key}", flush=True)
        res = evaluate_pair(
            osim=osim,
            baseline_model=base,
            candidate_model=args.candidate_osim,
            ik_path=ik,
            ok_times=ok_times,
            frame_stride=args.frame_stride,
        )
        trial_results.append({**case, **res})

    n_pass = sum(1 for r in trial_results if r.get("pass_hard"))
    n_jump = sum(int(r.get("total_jumps") or 0) for r in trial_results)
    sub = ResultPaths(args.namecode).sub_label
    out_dir = chest_out_dir(args.namecode, "compare")
    payload = stamped_payload(
        "chest_wrap_eval",
        namecode=args.namecode,
        sub_label=sub,
        variant=args.variant,
        candidate_osim=args.candidate_osim,
        n_trials=len(trial_results),
        n_pass_hard=n_pass,
        total_jumps=n_jump,
        subject_pass=bool(n_jump == 0 and n_pass == len(trial_results) and trial_results),
        trials=trial_results,
    )
    out = os.path.join(out_dir, f"eval_{sub}_{args.variant}.json")
    write_json(out, payload)
    print(f"[eval] pass {n_pass}/{len(trial_results)} jumps={n_jump} → {out}")
    return 0 if payload["subject_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
