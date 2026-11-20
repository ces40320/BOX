"""Detect Chest wrap anomalies on SO failures and repair by tier.

- Tier A: cubic gap-fill of short islands (``RETRY_so_gapfill_wrap_jump``).
- Tier B: trial FunctionBasedPath sidecar, else Chest sidecar. No gap-fill.
- Tier C: no fabricated SO; mark ``exclude_from_primary`` on the trouble entry.

``--tier auto`` classifies each trial with the wrap-pierce scan.
``--tier b-only`` skips classification: it finds short mid-trial path-length
jumps (Chest wrap side swaps) from IK, replaces only the jumping muscles'
paths with l(q), and reruns SO (+JR unless ``--skip-jr``).

The shared scaled model and successful trials are not rewritten. Trials that
already have a trial model and canonical SO force are skipped unless
``--rerun``.

Outputs:
- canonical SO / JR files (``SO_<app>/``, ``JR_<app>/``)
- trial model + record: ``SO_<app>/troubleshoot_so/wrap_fbp/``
- reports: ``Analysis/<protocol>/_diagnosis/{wrap_gapfill,wrap_fbp}/<SUB>/``

Example::

    python RUN_fix_muscle_path_wrap_fail.py --from-trouble --namecode 260519_KMJ --detect-only
    python RUN_fix_muscle_path_wrap_fail.py --from-trouble --namecode 260519_KMJ
    python RUN_fix_muscle_path_wrap_fail.py --from-trouble --namecode 260526_PJM --apps MeasuredEHF --tier b-only
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ts_paths  # noqa: E402,F401

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from wrap_detect_lib import (  # noqa: E402
    detect_length_jumps,
    import_opensim,
    repair_dir,
    scan_trial,
    stamped_payload,
    write_json,
)
from wrap_fbp_lib import repair_tier_b  # noqa: E402
from DETECT_muscle_path_wrap_jump import resolve_paths, trouble_cases  # noqa: E402
from pipeline_rules import trial_model_path  # noqa: E402
from RETRY_so_gapfill_wrap_jump import repair_tier_a  # noqa: E402
from UPDATE_pipeline_progress import load_troubles, save_troubles  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


def _mark_trouble(case: dict, **fields) -> None:
    entries = load_troubles()
    hit = False
    for e in entries:
        if (
            str(e.get("namecode")) == case["namecode"]
            and str(e.get("condition")) == case["condition"]
            and str(e.get("segment")) == case["segment"]
            and str(e.get("app") or "") == case["app"]
            and str(e.get("tool") or "").lower() == "so"
        ):
            e.update(fields)
            hit = True
    if hit:
        save_troubles(entries)


def _already_repaired(case: dict) -> bool:
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    seg, app = case["segment"], case["app"]
    return (
        trial_model_path(rp, case["condition"], app, seg) is not None
        and os.path.isfile(cp.so_path(seg, app, "force"))
    )


def _repair_b_only(case: dict, row: dict, *, osim, model: str, ik: str,
                   skip_jr: bool, timeout) -> None:
    islands, jumped = detect_length_jumps(osim, model, ik)
    row["islands"] = islands
    row["muscles"] = jumped
    _log(f"  jumps: islands={len(islands)} muscles={jumped}")
    if not islands:
        row["status"] = "no_jump"
        return
    bad_s = float(sum(b - a for a, b in islands))
    row["tier"] = "B"
    row.update(repair_tier_b(
        row,
        model_path=model,
        ik_path=ik,
        islands=islands,
        muscles=jumped,
        baseline_bad_s=bad_s,
        skip_jr=skip_jr,
        timeout_s=timeout,
    ))


def _repair_classified(case: dict, row: dict, res, *, model: str, ik: str,
                       tier_mode: str, skip_jr: bool, timeout) -> None:
    if res.tier == "A" and tier_mode in ("auto", "a-only") and res.severity.n_islands:
        row.update(repair_tier_a(
            row,
            islands=res.severity.islands,
            t0=res.severity.trial_t0,
            t1=res.severity.trial_t1,
            skip_jr=skip_jr,
            timeout_s=timeout,
        ))
    elif res.tier == "A" and not res.severity.n_islands:
        row["status"] = "no_bad_frames"
    elif res.tier == "B" and tier_mode == "auto":
        if res.error:
            row["status"] = "tier_C"
            row["exclude_from_primary"] = True
            row["error"] = res.error
        else:
            row.update(repair_tier_b(
                row,
                model_path=model,
                ik_path=ik,
                islands=res.severity.islands,
                muscles=res.severity.muscles_ever,
                baseline_bad_s=res.severity.total_bad_s,
                skip_jr=skip_jr,
                timeout_s=timeout,
            ))
    elif res.tier == "C":
        row["status"] = "tier_C"
        row["exclude_from_primary"] = True
        row["gapfill_rejected_reason"] = res.tier_reason
    else:
        row["status"] = f"skipped_tier_{res.tier}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-trouble", action="store_true", required=True)
    parser.add_argument("--namecode", default=None)
    parser.add_argument("--condition", default=None)
    parser.add_argument("--seg", default=None)
    parser.add_argument("--apps", default="")
    parser.add_argument("--tier", choices=("auto", "a-only", "b-only"), default="auto",
                        help="auto: classify then A/B/C. a-only: gap-fill only. "
                             "b-only: IK length-jump islands → trial l(q) model.")
    parser.add_argument("--rerun", action="store_true",
                        help="Repair again even if a trial model + SO force exist")
    parser.add_argument("--detect-only", action="store_true")
    parser.add_argument("--skip-jr", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=120.0)
    args = parser.parse_args()

    segs = {s.strip() for s in args.seg.split(",") if s.strip()} if args.seg else None
    apps = {a.strip() for a in args.apps.split(",") if a.strip()} if args.apps else None
    cases = trouble_cases(
        namecode=args.namecode,
        condition=args.condition,
        segments=segs,
        apps=apps,
    )
    if not cases:
        _log("No SO trouble cases matched.")
        return

    try:
        osim = import_opensim()
    except ImportError as exc:
        raise SystemExit(
            "opensim is not importable in this interpreter. "
            "Use the conda env `osim` (OpenSim 4.5)."
        ) from exc
    timeout = None if args.timeout_s <= 0 else args.timeout_s
    by_subject: dict[str, list] = {}
    repairs: list[dict] = []

    for k, case in enumerate(cases, start=1):
        model, ik = resolve_paths(case)
        tag = f"[{k}/{len(cases)}] {case['namecode']} {case['condition']} {case['segment']} {case['app']}"
        row = {
            "namecode": case["namecode"],
            "condition": case["condition"],
            "segment": case["segment"],
            "app": case["app"],
            "tier_mode": args.tier,
        }
        if not args.rerun and not args.detect_only and _already_repaired(case):
            _log(f"{tag} SKIP already repaired")
            row["status"] = "already_repaired"
            repairs.append(row)
            continue

        _log(f"{tag} scan")
        res = None
        if args.tier != "b-only":
            res = scan_trial(
                osim=osim,
                model_path=model,
                ik_path=ik,
                namecode=case["namecode"],
                condition=case["condition"],
                segment=case["segment"],
                app=case["app"],
            )
            by_subject.setdefault(case["namecode"], []).append(res)
            row.update(tier=res.tier, tier_reason=res.tier_reason)
            _log(
                f"  tier={res.tier} ({res.tier_reason}) "
                f"islands={res.severity.n_islands} bad_s={res.severity.total_bad_s:.3f}"
            )
        if args.detect_only or args.dry_run:
            row["status"] = "detect_only" if args.detect_only else "dry_run"
            repairs.append(row)
            continue

        try:
            if args.tier == "b-only":
                _repair_b_only(case, row, osim=osim, model=model, ik=ik,
                               skip_jr=args.skip_jr, timeout=timeout)
            else:
                _repair_classified(case, row, res, model=model, ik=ik,
                                   tier_mode=args.tier, skip_jr=args.skip_jr,
                                   timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            _log(f"[FAIL] {case['segment']}/{case['app']}: {exc}")
            row["status"] = "error"
            row["error"] = str(exc)
            row["exclude_from_primary"] = True

        if row.get("exclude_from_primary") or row.get("status") == "tier_C":
            _mark_trouble(
                case,
                wrap_tier="C",
                exclude_from_primary=True,
                wrap_note=row.get("tier_reason") or row.get("error") or "tier_C",
            )
        elif row.get("status") == "ok":
            _mark_trouble(
                case,
                wrap_tier=row.get("tier"),
                exclude_from_primary=False,
                wrap_method=row.get("method") or row.get("fill") or "cubic",
            )
        _log(f"  >>> {row.get('status')}")
        repairs.append(row)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for nc, results in by_subject.items():
        out = os.path.join(repair_dir(nc, "wrap_gapfill"), "chest_wrap_detect_report.json")
        write_json(out, stamped_payload(results))
        _log(f"[wrote] {out}")
    for nc in sorted({r["namecode"] for r in repairs}):
        approach = "wrap_fbp" if args.tier == "b-only" else "wrap_gapfill"
        rep = os.path.join(repair_dir(nc, approach), f"wrap_repair_report_{stamp}.json")
        mine = [r for r in repairs if r["namecode"] == nc]
        write_json(rep, {"tier_mode": args.tier, "repairs": mine})
        _log(f"[wrote] {rep}")


if __name__ == "__main__":
    main()
