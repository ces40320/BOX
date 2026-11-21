"""Optimize Chest ellipsoid (approach A) for one subject.

Example::

    python RUN_chest_ellipsoid_optimize.py --namecode 260526_PJM --apps MeasuredEHF --limit 6
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from DETECT_muscle_path_wrap_jump import resolve_paths, trouble_cases  # noqa: E402
from chest_diag_lib import iter_subject_ik_cases  # noqa: E402
from chest_ellipsoid_opt_lib import optimize_ellipsoid  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--namecode", required=True)
    p.add_argument("--apps", default="MeasuredEHF")
    p.add_argument("--condition", default=None)
    p.add_argument("--seg", default=None)
    p.add_argument("--from-trouble", action="store_true")
    p.add_argument("--all-ik", action="store_true")
    p.add_argument("--limit", type=int, default=8,
                   help="IK trials used in the objective (default 8)")
    p.add_argument("--maxiter", type=int, default=40)
    p.add_argument("--no-refine", action="store_true")
    args = p.parse_args()

    apps = {a.strip() for a in args.apps.split(",") if a.strip()}
    segs = {s.strip() for s in (args.seg or "").split(",") if s.strip()} or None
    cases: list[dict] = []
    if args.from_trouble or not args.all_ik:
        cases.extend(trouble_cases(
            namecode=args.namecode, condition=args.condition,
            segments=segs, apps=apps,
        ))
    if args.all_ik:
        cases.extend(iter_subject_ik_cases(
            args.namecode, apps=apps,
            conditions=[args.condition] if args.condition else None,
            segments=segs,
        ))
    seen: set[tuple] = set()
    uniq = []
    for c in cases:
        key = (c["namecode"], c["condition"], c["segment"], c["app"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    cases = uniq[: max(1, args.limit)]
    if not cases:
        print("[A] no IK cases")
        return 1

    ik_jobs = []
    baseline = None
    for c in cases:
        model, ik = resolve_paths(c)
        if not os.path.isfile(model) or not os.path.isfile(ik):
            print(f"[A] skip missing {c}")
            continue
        if baseline is None:
            baseline = model
        ik_jobs.append({**c, "model_path": model, "ik_path": ik})
    if not ik_jobs or baseline is None:
        print("[A] no usable IK/model")
        return 1

    print(f"[A] baseline={baseline} n_jobs={len(ik_jobs)}", flush=True)
    payload = optimize_ellipsoid(
        namecode=args.namecode,
        baseline_model_path=baseline,
        ik_jobs=ik_jobs,
        maxiter=args.maxiter,
        refine=not args.no_refine,
    )
    print(f"[A] wrote {payload['out_osim']}", flush=True)
    print(f"[A] params → {payload.get('best_params')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
