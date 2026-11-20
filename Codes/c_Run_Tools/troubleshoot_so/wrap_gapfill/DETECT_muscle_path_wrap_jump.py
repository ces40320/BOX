"""Detect Chest wrap path anomalies on SO-failed trials and assign tier A/B/C.

Does not modify shared scaled models. Writes
``Analysis/<protocol>/_diagnosis/wrap_gapfill/<SUB#>/chest_wrap_detect_report.json``
and ``chest_wrap_detect_flags.csv``.

Example::

    python DETECT_muscle_path_wrap_jump.py --from-trouble --namecode 260519_KMJ
    python DETECT_muscle_path_wrap_jump.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from wrap_detect_lib import (  # noqa: E402
    Severity,
    classify_tier,
    good_intervals,
    import_opensim,
    merge_intervals,
    repair_dir,
    scan_trial,
    stamped_payload,
    stitch_sto_cubic,
    write_json,
)
from pipeline_rules import resolve_model_path  # noqa: E402
from UPDATE_pipeline_progress import (  # noqa: E402
    extract_freeze_sim_time,
    load_troubles,
)

import numpy as np  # noqa: E402


def trouble_cases(
    *,
    namecode: str | None,
    condition: str | None,
    segments: set[str] | None,
    apps: set[str] | None,
) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for e in load_troubles():
        if str(e.get("tool") or "").lower() != "so":
            continue
        nc = str(e.get("namecode") or "")
        cond = str(e.get("condition") or "")
        seg = str(e.get("segment") or "")
        app = str(e.get("app") or "MeasuredEHF")
        if namecode and nc != namecode:
            continue
        if condition and cond != condition:
            continue
        if segments and seg not in segments:
            continue
        if apps and app not in apps:
            continue
        key = (nc, cond, seg, app)
        if key in seen:
            continue
        seen.add(key)
        ft = extract_freeze_sim_time(e)
        out.append({
            "namecode": nc,
            "condition": cond,
            "segment": seg,
            "app": app,
            "freeze_sim_time": ft,
        })
    return out


def resolve_paths(case: dict) -> tuple[str, str]:
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    model = resolve_model_path(rp, case["condition"], case["app"], "so", must_exist=False)
    ik = cp.ik_path(case["segment"])
    return model, ik


def run_self_test() -> None:
    """Tier math and interval merge without OpenSim."""
    times = np.array([0.0, 0.01, 0.02, 0.10, 0.11])
    mask = np.array([False, True, True, False, True])
    islands = merge_intervals(times, mask, pad_s=0.0, t0=0.0, t1=0.11)
    assert islands == [[0.01, 0.02], [0.11, 0.11]], islands
    goods = good_intervals(0.0, 1.0, [[0.2, 0.22]])
    assert goods[0][0] == 0.0 and abs(goods[0][1] - 0.2) < 1e-9

    short = Severity(
        0, 2, 2, bad_frac=0.01, n_islands=1, max_island_s=0.02,
        total_bad_s=0.02, max_muscles_simul=1, n_muscles_ever=1,
    )
    assert classify_tier(short)[0] == "A"
    long = Severity(
        0, 2, 2, bad_frac=0.1, n_islands=5, max_island_s=0.3,
        total_bad_s=0.4, max_muscles_simul=4, n_muscles_ever=6,
    )
    assert classify_tier(long)[0] == "B"
    hopeless = Severity(
        0, 2, 2, bad_frac=0.4, n_islands=2, max_island_s=0.5,
        total_bad_s=0.8, max_muscles_simul=1, n_muscles_ever=1,
    )
    assert classify_tier(hopeless)[0] == "C"

    import tempfile
    import pandas as pd
    from optimization.ricto_io import write_opensim_storage

    meta = {"header_lines": ["version=1\n", "nRows=2\n", "nColumns=2\n", "endheader\n"]}
    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "a.sto")
        b = os.path.join(td, "b.sto")
        out = os.path.join(td, "out.sto")
        write_opensim_storage(
            a, pd.DataFrame({"time": [0.0, 0.01], "f": [0.0, 1.0]}), meta,
        )
        write_opensim_storage(
            b, pd.DataFrame({"time": [0.03, 0.04], "f": [3.0, 4.0]}), meta,
        )
        n, t0, t1 = stitch_sto_cubic([a, b], out)
        assert n >= 4 and t0 == 0.0 and abs(t1 - 0.04) < 1e-6
    print("[self-test] tier + interval merge + cubic stitch OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-trouble", action="store_true")
    parser.add_argument("--namecode", default=None)
    parser.add_argument("--condition", default=None)
    parser.add_argument("--seg", default=None, help="Comma-separated segments")
    parser.add_argument("--apps", default="", help="Comma-separated apps (default: all in trouble)")
    parser.add_argument("--pad-s", type=float, default=0.01)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--window-around-freeze",
        type=float,
        default=0.0,
        help="If >0, scan only freeze_sim_time ± this many seconds.",
    )
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        if not args.from_trouble and not args.namecode:
            return

    if not args.from_trouble:
        parser.error("--from-trouble is required unless --self-test only")

    segs = {s.strip() for s in args.seg.split(",") if s.strip()} if args.seg else None
    apps = {a.strip() for a in args.apps.split(",") if a.strip()} if args.apps else None
    cases = trouble_cases(
        namecode=args.namecode,
        condition=args.condition,
        segments=segs,
        apps=apps,
    )
    if not cases:
        print("No SO trouble cases matched.")
        return

    osim = import_opensim()
    by_subject: dict[str, list] = {}
    for case in cases:
        model, ik = resolve_paths(case)
        window = None
        ft = case.get("freeze_sim_time")
        if args.window_around_freeze > 0 and ft is not None:
            window = (float(ft) - args.window_around_freeze, float(ft) + args.window_around_freeze)
        print(
            f"[scan] {case['namecode']} {case['condition']} {case['segment']} {case['app']}"
        )
        res = scan_trial(
            osim=osim,
            model_path=model,
            ik_path=ik,
            namecode=case["namecode"],
            condition=case["condition"],
            segment=case["segment"],
            app=case["app"],
            pad_s=args.pad_s,
            time_window=window,
        )
        print(
            f"  tier={res.tier} ({res.tier_reason}) "
            f"islands={res.severity.n_islands} bad_frac={res.severity.bad_frac:.3f} "
            f"muscles={res.severity.n_muscles_ever}"
            + (f" err={res.error}" if res.error else "")
        )
        by_subject.setdefault(case["namecode"], []).append(res)

    for nc, results in by_subject.items():
        out_dir = repair_dir(nc, "wrap_gapfill")
        report = os.path.join(out_dir, "chest_wrap_detect_report.json")
        write_json(report, stamped_payload(results))
        csv_path = os.path.join(out_dir, "chest_wrap_detect_flags.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["namecode", "condition", "segment", "app", "tier",
                            "time_s", "muscle", "flag", "path_length", "dL"],
            )
            w.writeheader()
            for res in results:
                if not res.frame_flags:
                    w.writerow({
                        "namecode": res.namecode,
                        "condition": res.condition,
                        "segment": res.segment,
                        "app": res.app,
                        "tier": res.tier,
                        "time_s": "",
                        "muscle": "",
                        "flag": res.tier_reason,
                        "path_length": "",
                        "dL": "",
                    })
                for row in res.frame_flags:
                    w.writerow({
                        "namecode": res.namecode,
                        "condition": res.condition,
                        "segment": res.segment,
                        "app": res.app,
                        "tier": res.tier,
                        "time_s": row.get("time_s", ""),
                        "muscle": row.get("muscle", ""),
                        "flag": row.get("flag", ""),
                        "path_length": row.get("path_length", ""),
                        "dL": row.get("dL", ""),
                    })
        print(f"[wrote] {report}")
        print(f"[wrote] {csv_path}")


if __name__ == "__main__":
    main()
