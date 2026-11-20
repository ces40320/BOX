"""Tier A only: run SO on good time islands and cubic-fill the short gaps.

Refuses Tier B/C. Does not edit the shared scaled model.

Per-island SO pieces are kept in ``SO_<app>/troubleshoot_so/wrap_gapfill/``
while running and removed once the stitched canonical SO is written.

Example::

    python RETRY_so_gapfill_wrap_jump.py --detect-json path/to/chest_wrap_detect_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from wrap_detect_lib import good_intervals, stitch_sto_cubic, write_json  # noqa: E402
from opensim_pipeline_handlers import (  # noqa: E402
    prepare_jr_setup,
    prepare_so_setup,
    run_jr,
    run_so,
)
from RETRY_so_skipping_freeze_time import (  # noqa: E402
    SO_TYPES,
    _delete_if_exists,
    _move_so_outputs,
    _side_path,
    _so_paths,
)

APPROACH = "wrap_gapfill"


def _log(msg: str) -> None:
    print(msg, flush=True)


def repair_tier_a(
    case: dict,
    *,
    islands: list,
    t0: float,
    t1: float,
    skip_jr: bool = False,
    timeout_s: float | None = 120.0,
    dry_run: bool = False,
    model_path: str | None = None,
) -> dict:
    """SO on good intervals of one trial, cubic-stitch force and activation."""
    tier = str(case.get("tier") or "A")
    if tier != "A":
        raise ValueError(
            f"gap-fill refused for tier {tier} "
            f"({case.get('condition')}/{case.get('segment')})"
        )
    goods = good_intervals(t0, t1, islands)
    if not goods:
        raise ValueError("no good time intervals left after masking")

    namecode = case["namecode"]
    cond = case["condition"]
    seg = case["segment"]
    app = case["app"]
    rp = ResultPaths(namecode)
    cp = ConditionPaths(rp, cond)
    paths = _so_paths(cp, seg, app)
    ctrl = paths["force"].replace("_force.sto", "_controls.xml")

    _log(
        f"[Tier A] {namecode} {cond} {seg} {app}  "
        f"good={[(round(a, 3), round(b, 3)) for a, b in goods]}  "
        f"bad={islands}"
    )
    if dry_run:
        return {"status": "dry_run", "n_good": len(goods), "islands": islands}

    pieces = [
        _side_path(p, f"g{i}", APPROACH)
        for i in range(len(goods))
        for p in [*paths.values(), ctrl]
    ]
    _delete_if_exists(list(paths.values()) + [ctrl] + pieces)

    seg_paths: dict[str, list[str]] = {k: [] for k in SO_TYPES}
    try:
        for i, (a, b) in enumerate(goods):
            _log(f"[SO g{i}] {a:.4g} → {b:.4g}")
            prepare_so_setup(
                cp=cp, rp=rp, seg=seg, app=app,
                start_time=a, end_time=b, model_path=model_path,
            )
            run_so(
                cp=cp, rp=rp, seg=seg, app=app,
                timeout_s=timeout_s, model_path=model_path,
            )
            moved = _move_so_outputs(paths, f"g{i}", APPROACH)
            for kind in SO_TYPES:
                seg_paths[kind].append(moved[kind])

        for kind in SO_TYPES:
            n, ts, te = stitch_sto_cubic(seg_paths[kind], paths[kind])
            _log(f"  [stitch {kind}] n={n} t=[{ts:.4g}, {te:.4g}]")

        last_ctrl = _side_path(ctrl, f"g{len(goods) - 1}", APPROACH)
        if os.path.isfile(last_ctrl):
            shutil.copy2(last_ctrl, ctrl)
        _delete_if_exists(pieces)

        if not skip_jr:
            _log("[JR] full window on stitched SO")
            prepare_jr_setup(
                cp=cp, rp=rp, seg=seg, app=app, model_path=model_path,
            )
            run_jr(
                cp=cp, rp=rp, seg=seg, app=app,
                timeout_s=timeout_s, model_path=model_path,
            )
        return {
            "status": "ok",
            "fill": "cubic",
            "tier": "A",
            "n_good": len(goods),
            "islands": islands,
            "gapfill_s": float(sum(b - a for a, b in islands)),
        }
    except Exception:
        _delete_if_exists(list(paths.values()) + [ctrl])
        raise


def _cases_from_detect(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    rows = []
    for res in payload.get("results") or []:
        sev = res.get("severity") or {}
        rows.append({
            **{k: res.get(k) for k in ("namecode", "condition", "segment", "app", "tier", "tier_reason")},
            "islands": sev.get("islands") or [],
            "t0": float(sev.get("trial_t0") or 0.0),
            "t1": float(sev.get("trial_t1") or 0.0),
            "n_islands": int(sev.get("n_islands") or 0),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detect-json", required=True)
    parser.add_argument("--skip-jr", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=120.0)
    args = parser.parse_args()

    cases = _cases_from_detect(args.detect_json)
    done = []
    skipped = []
    failed = []
    for case in cases:
        tag = f"{case['condition']}/{case['segment']}/{case['app']}"
        if case.get("tier") != "A":
            _log(f"[skip] {tag} tier={case.get('tier')} (gap-fill not allowed)")
            skipped.append({**case, "reason": "not_tier_A"})
            continue
        if not case["n_islands"]:
            _log(f"[skip] {tag} no bad islands")
            skipped.append({**case, "reason": "no_islands"})
            continue
        try:
            info = repair_tier_a(
                case,
                islands=case["islands"],
                t0=case["t0"],
                t1=case["t1"],
                skip_jr=args.skip_jr,
                timeout_s=None if args.timeout_s <= 0 else args.timeout_s,
                dry_run=args.dry_run,
            )
            done.append({**case, **info})
        except Exception as exc:  # noqa: BLE001
            _log(f"[FAIL] {tag}: {exc}")
            failed.append({**case, "error": str(exc)})

    report = os.path.join(os.path.dirname(args.detect_json), "wrap_repair_tier_a.json")
    write_json(report, {"succeeded": done, "skipped": skipped, "failed": failed})
    _log(f"[wrote] {report}  ok={len(done)} skip={len(skipped)} fail={len(failed)}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
