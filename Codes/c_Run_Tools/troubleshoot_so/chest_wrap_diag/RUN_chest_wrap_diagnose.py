"""Run Chest wrap geometric diagnosis (SUB8-first).

Writes frame×muscle CSV and summary JSON under
``Analysis/<protocol>/_diagnosis/chest_wrap/<SUB>/diag/``.

Examples::

    python RUN_chest_wrap_diagnose.py --namecode 260526_PJM --apps MeasuredEHF
    python RUN_chest_wrap_diagnose.py --all-ik --namecode 260526_PJM --apps MeasuredEHF

With no source flag the wrap_fbp-repaired trials are diagnosed.
    python RUN_chest_wrap_diagnose.py --self-test
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from pipeline_rules import resolve_model_path  # noqa: E402
from wrap_detect_lib import import_opensim  # noqa: E402
from DETECT_muscle_path_wrap_jump import resolve_paths  # noqa: E402
from chest_diag_lib import (  # noqa: E402
    add_case_source_args,
    chest_out_dir,
    collect_cases,
    diagnose_trial,
    get_chest_ellipsoid_params,
    stamped_payload,
    summarize_diag_frames,
    write_json,
)

import numpy as np  # noqa: E402


def _case_stem(case: dict) -> str:
    return (
        f"{case['condition']}_{case['segment']}_{case['app']}"
    )


def run_self_test() -> None:
    from chest_diag_lib import classify_failure, cycle_percent, length_jump_count

    assert classify_failure(
        wrap_active=False, prev_wrap_active=True, chord_hits=False,
        endpoint_inside=False, wrong_side=False, tangent_jump=False,
        length_jump=False, length_m=0.45, chord_m=0.44,
    ) == "unwrap_rewrap"
    assert classify_failure(
        wrap_active=False, prev_wrap_active=False, chord_hits=True,
        endpoint_inside=False, wrong_side=False, tangent_jump=False,
        length_jump=False, length_m=0.40, chord_m=0.40,
    ) == "pierce"
    t = np.linspace(0, 1, 11)
    cp = cycle_percent(t)
    assert abs(cp[0] - 0) < 1e-9 and abs(cp[-1] - 100) < 1e-9
    L = np.array([0.5, 0.5, 0.76, 0.76, 0.5, 0.5])
    assert length_jump_count(L, np.arange(len(L)) * 0.01) >= 1
    print("[self-test] OK")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_case_source_args(p)
    p.add_argument("--namecode", default=None)
    p.add_argument("--condition", default=None)
    p.add_argument("--seg", default=None, help="Comma-separated segments")
    p.add_argument("--apps", default="")
    p.add_argument("--frame-stride", type=int, default=1)
    p.add_argument("--no-moment-arms", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Max trials (0=all)")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        run_self_test()
        return 0

    if not args.namecode and not args.from_trouble:
        p.error("--namecode is required unless only --from-trouble is used")

    apps = {a.strip() for a in args.apps.split(",") if a.strip()} or None
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
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]

    if not cases:
        print("[diag] no cases")
        return 1

    osim = import_opensim()
    namecode = cases[0]["namecode"]
    diag_dir = chest_out_dir(namecode, "diag")
    trial_summaries: list[dict] = []
    all_frames = []

    # Baseline ellipsoid params from first available model
    model0, _ = resolve_paths(cases[0])
    ell_params = {}
    if os.path.isfile(model0):
        m = osim.Model(model0)
        m.initSystem()
        ell_params = get_chest_ellipsoid_params(osim, m)

    for i, case in enumerate(cases):
        model_path, ik_path = resolve_paths(case)
        print(
            f"[diag] ({i + 1}/{len(cases)}) "
            f"{case['condition']} {case['segment']} {case['app']}",
            flush=True,
        )
        df, meta = diagnose_trial(
            osim=osim,
            model_path=model_path,
            ik_path=ik_path,
            namecode=case["namecode"],
            condition=case["condition"],
            segment=case["segment"],
            app=case["app"],
            frame_stride=args.frame_stride,
            compute_moment_arms=not args.no_moment_arms,
        )
        stem = _case_stem(case)
        csv_path = os.path.join(diag_dir, f"chest_diag_{stem}.csv")
        if not df.empty:
            df.to_csv(csv_path, index=False)
            all_frames.append(df)
        meta.csv_path = csv_path
        summary = summarize_diag_frames(df)
        trial_summaries.append({
            **case,
            "model_path": model_path,
            "ik_path": ik_path,
            "csv_path": csv_path,
            "error": meta.error,
            "n_frames": meta.n_frames,
            "n_fail_rows": meta.n_fail_rows,
            "failure_counts": meta.failure_counts,
            "summary": summary,
            "chest_muscles": meta.chest_muscles,
        })
        if meta.error:
            print(f"  ERROR: {meta.error}", flush=True)
        else:
            print(
                f"  rows={len(df)} fail_rows={meta.n_fail_rows} "
                f"types={meta.failure_counts}",
                flush=True,
            )

    import pandas as pd

    concat = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
    sub_label = ResultPaths(namecode).sub_label
    overall = summarize_diag_frames(concat)
    payload = stamped_payload(
        "chest_wrap_diag_summary",
        namecode=namecode,
        sub_label=sub_label,
        n_trials=len(cases),
        ellipsoid_params=ell_params,
        overall=overall,
        trials=trial_summaries,
    )
    out_json = os.path.join(diag_dir, f"chest_diag_summary_{sub_label}.json")
    write_json(out_json, payload)
    if not concat.empty:
        concat_path = os.path.join(diag_dir, f"chest_diag_all_{sub_label}.csv")
        # keep a compact all-file may be huge; write only if modest
        if len(concat) <= 2_000_000:
            concat.to_csv(concat_path, index=False)
            print(f"[diag] wrote {concat_path}", flush=True)
    print(f"[diag] summary → {out_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
