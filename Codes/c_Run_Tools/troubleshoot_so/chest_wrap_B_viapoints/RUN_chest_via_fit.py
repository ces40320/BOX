"""Fit via / moving path points (approach B) for failing Chest-wrap muscles.

Example::

    python RUN_chest_via_fit.py --namecode 260526_PJM --apps MeasuredEHF --limit 8
    python RUN_chest_via_fit.py --namecode 260526_PJM --use-moving --include-lumbar1
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

import pandas as pd  # noqa: E402

from DETECT_muscle_path_wrap_jump import resolve_paths  # noqa: E402
from chest_diag_lib import (  # noqa: E402
    add_case_source_args,
    chest_out_dir,
    collect_cases,
    spread_cases,
)
from chest_via_fit_lib import DEFAULT_FAIL_MUSCLES, fit_subject_via_points  # noqa: E402


def _ok_times_from_diag(namecode: str) -> dict[tuple, set[float]]:
    diag = chest_out_dir(namecode, "diag")
    paths = sorted(glob.glob(os.path.join(diag, "chest_diag_*.csv")))
    paths = [p for p in paths if "chest_diag_all_" not in os.path.basename(p)]
    out: dict[tuple, set[float]] = {}
    for pth in paths:
        df = pd.read_csv(pth)
        if df.empty:
            continue
        for (cond, seg, app), g in df.groupby(["condition", "segment", "app"]):
            ok = g[g["failure_type"] == "ok"]
            out.setdefault((str(cond), str(seg), str(app)), set()).update(
                float(t) for t in ok["time_s"].tolist()
            )
    return out


def _muscles_from_diag(namecode: str, min_fail: int = 1) -> list[str]:
    diag = chest_out_dir(namecode, "diag")
    paths = sorted(glob.glob(os.path.join(diag, "chest_diag_*.csv")))
    paths = [p for p in paths if "chest_diag_all_" not in os.path.basename(p)]
    if not paths:
        return list(DEFAULT_FAIL_MUSCLES)
    df = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    fail = df[df["failure_type"] != "ok"]
    counts = fail.groupby("muscle").size().sort_values(ascending=False)
    mus = [m for m, n in counts.items() if int(n) >= min_fail]
    return mus or list(DEFAULT_FAIL_MUSCLES)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--namecode", required=True)
    p.add_argument("--apps", default="MeasuredEHF")
    p.add_argument("--condition", default=None)
    p.add_argument("--seg", default=None)
    add_case_source_args(p)
    p.add_argument("--limit", type=int, default=8,
                   help="IK trials used for fitting, spread across conditions")
    p.add_argument("--n-via", type=int, default=2)
    p.add_argument("--include-lumbar1", action="store_true")
    p.add_argument("--use-moving", action="store_true")
    p.add_argument("--muscles", default="",
                   help="Comma list; default = diagnosis failures or LTpT T3/T4")
    args = p.parse_args()

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

    ik_jobs = []
    baseline = None
    for c in cases:
        model, ik = resolve_paths(c)
        if not os.path.isfile(model) or not os.path.isfile(ik):
            continue
        if baseline is None:
            baseline = model
        ik_jobs.append({**c, "model_path": model, "ik_path": ik})
    if not ik_jobs or baseline is None:
        print("[B] no usable IK/model")
        return 1

    if args.muscles.strip():
        muscles = [m.strip() for m in args.muscles.split(",") if m.strip()]
    else:
        muscles = _muscles_from_diag(args.namecode)

    ok_map = _ok_times_from_diag(args.namecode)
    print(
        f"[B] baseline={baseline} muscles={muscles} n_jobs={len(ik_jobs)}",
        flush=True,
    )
    payload = fit_subject_via_points(
        namecode=args.namecode,
        baseline_model_path=baseline,
        ik_jobs=ik_jobs,
        muscles=muscles,
        n_via=args.n_via,
        include_lumbar1=args.include_lumbar1,
        use_moving=args.use_moving,
        ok_times_by_trial=ok_map or None,
    )
    print(f"[B] wrote {payload['out_osim']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
