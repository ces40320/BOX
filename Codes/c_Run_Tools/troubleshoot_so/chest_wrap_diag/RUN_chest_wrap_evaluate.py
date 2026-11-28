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
from concurrent.futures import ProcessPoolExecutor, as_completed
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
    add_case_source_args,
    batch_moment_arms,
    chest_out_dir,
    collect_cases,
    good_frame_mask,
    length_jump_count,
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


_DIAG_COLS = {
    "condition",
    "segment",
    "app",
    "muscle",
    "time_s",
    "failure_type",
    "in_jump_island",
}


def _filter_good_diag_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Keep baseline rows that are ok, outside jump islands, and after frame 0."""
    if df.empty:
        return df
    work = df
    if "in_jump_island" in work.columns and work["in_jump_island"].dtype != bool:
        work = work.copy()
        work["in_jump_island"] = work["in_jump_island"].astype(bool)
    mask = good_frame_mask(work)
    t0 = work.groupby(["condition", "segment", "app"])["time_s"].transform("min")
    mask = mask & (work["time_s"] > t0)
    return work[mask]


def _load_ok_times_by_trial(namecode: str) -> dict[tuple, dict[str, set[float]]]:
    """Map (cond, seg, app) → {muscle: good times} from diagnosis CSVs.

    Per muscle: excludes non-ok frames, baseline jump-island frames
    (via good_frame_mask), and each trial's first frame (no prev frame).
    """
    diag_dir = chest_out_dir(namecode, "diag")
    paths = sorted(glob.glob(os.path.join(diag_dir, "chest_diag_*.csv")))
    paths = [p for p in paths if "chest_diag_all_" not in os.path.basename(p)]
    out: dict[tuple, dict[str, set[float]]] = {}
    for pth in paths:
        df = pd.read_csv(pth, usecols=lambda c: c in _DIAG_COLS)
        if df.empty:
            continue
        ok = _filter_good_diag_rows(df)
        for (cond, seg, app, mus), g in ok.groupby(["condition", "segment", "app", "muscle"]):
            key = (str(cond), str(seg), str(app))
            out.setdefault(key, {}).setdefault(str(mus), set()).update(
                round(float(t), 4) for t in g["time_s"].tolist()
            )
    return out


def evaluate_pair(
    *,
    osim,
    baseline_model: str,
    candidate_model: str,
    ik_path: str,
    ok_times: dict[str, set[float]] | None,
    muscles: list[str] | None = None,
    frame_stride: int = 2,
    _models: tuple | None = None,
) -> dict:
    from optimization.ricto_io import read_opensim_storage

    if _models is not None:
        m0, s0, m1, s1, names, mus0_list, mus1_list = _models
    else:
        m0 = osim.Model(baseline_model)
        s0 = m0.initSystem()
        m1 = osim.Model(candidate_model)
        s1 = m1.initSystem()
        names = muscles or list_chest_path_muscles(m0)
        names = [n for n in names if m1.getMuscles().contains(n)]
        mus0_list = [(m, m0.getMuscles().get(m)) for m in names]
        mus1_list = [(m, m1.getMuscles().get(m)) for m in names]
    ik_df, meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    indeg = _ik_in_degrees(meta)

    len0 = {m: [] for m in names}
    len1 = {m: [] for m in names}
    ma0 = {m: {c: [] for c in L5S1_COORDS} for m in names}
    ma1 = {m: {c: [] for c in L5S1_COORDS} for m in names}
    t_used: list[float] = []
    ok_mask = {m: [] for m in names}

    def _is_ok(m: str, t: float) -> bool:
        if ok_times is None:
            return True
        return round(t, 4) in ok_times.get(m, ())

    for fi in range(0, len(ik_df), max(1, frame_stride)):
        row = ik_df.iloc[fi]
        t = float(row[tcol])
        _apply_ik_row(osim, m0, s0, row, indeg)
        _apply_ik_row(osim, m1, s1, row, indeg)
        t_used.append(t)
        any_ok = False
        for (m, mus0), (_, mus1) in zip(mus0_list, mus1_list):
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
            use_ma = _is_ok(m, t)
            ok_mask[m].append(use_ma)
            if use_ma:
                any_ok = True
        if any_ok:
            b0 = batch_moment_arms(osim, m0, s0, mus0_list)
            b1 = batch_moment_arms(osim, m1, s1, mus1_list)
            for m in names:
                if ok_mask[m][-1]:
                    for ci, c in enumerate(L5S1_COORDS):
                        ma0[m][c].append(float(b0[m][ci]))
                        ma1[m][c].append(float(b1[m][ci]))

    per_muscle: dict = {}
    total_jumps = 0
    hard_fail = False
    for m in names:
        a = np.asarray(len0[m], dtype=float)
        b = np.asarray(len1[m], dtype=float)
        # good-frame RMSE: frames this muscle was ok in the baseline diagnosis
        mask = np.asarray(ok_mask[m], dtype=bool) & np.isfinite(a) & np.isfinite(b)
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
            "n_ok_frames": int(mask.sum()),
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


_WORKER_CACHE: dict = {}


def _eval_worker_run(task: tuple) -> tuple[int, dict]:
    idx, case, base, cand, ik, ok_times, frame_stride = task
    osim = _WORKER_CACHE.get("osim")
    if osim is None:
        osim = import_opensim()
        _WORKER_CACHE["osim"] = osim
    key = (base, cand)
    models = _WORKER_CACHE.get(key)
    if models is None:
        m0 = osim.Model(base)
        s0 = m0.initSystem()
        m1 = osim.Model(cand)
        s1 = m1.initSystem()
        names = [n for n in list_chest_path_muscles(m0) if m1.getMuscles().contains(n)]
        mus0_list = [(m, m0.getMuscles().get(m)) for m in names]
        mus1_list = [(m, m1.getMuscles().get(m)) for m in names]
        models = (m0, s0, m1, s1, names, mus0_list, mus1_list)
        _WORKER_CACHE[key] = models
    res = evaluate_pair(
        osim=osim,
        baseline_model=base,
        candidate_model=cand,
        ik_path=ik,
        ok_times=ok_times,
        frame_stride=frame_stride,
        _models=models,
    )
    return idx, {**case, **res}


def run_self_test() -> None:
    a = np.array([1.0, 1.0, 1.0])
    b = np.array([1.0, 1.002, 1.0])
    assert abs(rmse(a, b) - np.sqrt(((0.002) ** 2) / 3)) < 1e-9
    L = np.array([0.5, 0.5, 0.76, 0.76, 0.5])
    assert length_jump_count(L, np.arange(5) * 0.01) >= 1
    df = pd.DataFrame(
        [
            {"condition": "c", "segment": "s", "app": "a", "muscle": "m", "time_s": 0.0, "failure_type": "ok", "in_jump_island": False},
            {"condition": "c", "segment": "s", "app": "a", "muscle": "m", "time_s": 0.1, "failure_type": "ok", "in_jump_island": True},
            {"condition": "c", "segment": "s", "app": "a", "muscle": "m", "time_s": 0.2, "failure_type": "pierce", "in_jump_island": False},
            {"condition": "c", "segment": "s", "app": "a", "muscle": "m", "time_s": 0.3, "failure_type": "ok", "in_jump_island": False},
        ]
    )
    kept = _filter_good_diag_rows(df)
    assert kept["time_s"].tolist() == [0.3], f"unexpected kept times: {kept['time_s'].tolist()}"
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
    p.add_argument("--workers", type=int, default=16,
                   help="Parallel worker processes (default 16; 1=sequential)")
    add_case_source_args(p)
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

    cases = collect_cases(
        args.namecode,
        from_wrap_fbp=args.from_wrap_fbp,
        from_trouble=args.from_trouble,
        all_ik=args.all_ik,
        condition=args.condition,
        segments=segs,
        apps=apps,
    )
    if args.limit:
        cases = cases[: args.limit]

    tasks: list[tuple] = []
    trial_results: list[dict | None] = [None] * len(cases)
    for idx, case in enumerate(cases):
        base, ik = resolve_paths(case)
        if args.baseline_osim:
            base = args.baseline_osim
        if not os.path.isfile(base) or not os.path.isfile(ik):
            trial_results[idx] = {**case, "error": "missing base/ik"}
            continue
        key = (case["condition"], case["segment"], case["app"])
        ok_times = ok_map.get(key)
        tasks.append((idx, case, base, args.candidate_osim, ik, ok_times, args.frame_stride))

    n_workers = max(1, min(int(args.workers), len(tasks) or 1))
    print(f"[eval] {len(tasks)} trials, stride={args.frame_stride}, workers={n_workers}", flush=True)
    if n_workers == 1:
        for t in tasks:
            idx, out_rec = _eval_worker_run(t)
            trial_results[idx] = out_rec
            print(f"[eval] done ({idx + 1}/{len(cases)}) {out_rec['condition']} {out_rec['segment']}", flush=True)
    else:
        done = 0
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futs = [pool.submit(_eval_worker_run, t) for t in tasks]
            for fut in as_completed(futs):
                idx, out_rec = fut.result()
                trial_results[idx] = out_rec
                done += 1
                if done % 10 == 0 or done == len(tasks):
                    print(f"[eval] done {done}/{len(tasks)}", flush=True)
    trial_results = [r for r in trial_results if r is not None]

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
