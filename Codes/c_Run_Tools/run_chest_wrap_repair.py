"""Detect Chest wrap anomalies on SO failures and repair by tier.

- Tier A: cubic gap-fill of short islands (``retry_so_path_gapfill``).
- Tier B: trial FunctionBasedPath sidecar, else Chest sidecar. No gap-fill.
- Tier C: no fabricated SO; mark ``exclude_from_primary`` on the trouble entry.

The shared scaled model and successful trials are not rewritten.

Example::

    python run_chest_wrap_repair.py --from-trouble --namecode 260519_KMJ --detect-only
    python run_chest_wrap_repair.py --from-trouble --namecode 260519_KMJ
"""

from __future__ import annotations

import argparse
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.append(CODES_DIR)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from chest_wrap_lib import (  # noqa: E402
    import_opensim,
    repair_dir,
    scan_trial,
    stamped_payload,
    write_json,
)
from chest_wrap_tier_b import repair_tier_b  # noqa: E402
from detect_chest_wrap_anomalies import resolve_paths, trouble_cases  # noqa: E402
from retry_so_path_gapfill import repair_tier_a  # noqa: E402
from update_pipeline_progress import load_troubles, save_troubles  # noqa: E402


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-trouble", action="store_true", required=True)
    parser.add_argument("--namecode", default=None)
    parser.add_argument("--condition", default=None)
    parser.add_argument("--seg", default=None)
    parser.add_argument("--apps", default="")
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

    for case in cases:
        model, ik = resolve_paths(case)
        _log(f"[scan] {case['namecode']} {case['condition']} {case['segment']} {case['app']}")
        res = scan_trial(
            osim=osim,
            model_path=model,
            ik_path=ik,
            namecode=case["namecode"],
            condition=case["condition"],
            segment=case["segment"],
            app=case["app"],
        )
        _log(
            f"  tier={res.tier} ({res.tier_reason}) "
            f"islands={res.severity.n_islands} bad_s={res.severity.total_bad_s:.3f}"
        )
        by_subject.setdefault(case["namecode"], []).append(res)
        row = {
            "namecode": case["namecode"],
            "condition": case["condition"],
            "segment": case["segment"],
            "app": case["app"],
            "tier": res.tier,
            "tier_reason": res.tier_reason,
        }
        if args.detect_only or args.dry_run:
            row["status"] = "detect_only" if args.detect_only else "dry_run"
            repairs.append(row)
            continue

        try:
            if res.tier == "A" and res.severity.n_islands:
                info = repair_tier_a(
                    row,
                    islands=res.severity.islands,
                    t0=res.severity.trial_t0,
                    t1=res.severity.trial_t1,
                    skip_jr=args.skip_jr,
                    timeout_s=timeout,
                )
                row.update(info)
            elif res.tier == "A":
                row["status"] = "no_bad_frames"
            elif res.tier == "B":
                if res.error:
                    row["status"] = "tier_C"
                    row["exclude_from_primary"] = True
                    row["error"] = res.error
                else:
                    info = repair_tier_b(
                        row,
                        model_path=model,
                        ik_path=ik,
                        islands=res.severity.islands,
                        muscles=res.severity.muscles_ever,
                        baseline_bad_s=res.severity.total_bad_s,
                        skip_jr=args.skip_jr,
                        timeout_s=timeout,
                    )
                    row.update(info)
            else:
                row["status"] = "tier_C"
                row["exclude_from_primary"] = True
                row["gapfill_rejected_reason"] = res.tier_reason
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
                wrap_tier=res.tier,
                exclude_from_primary=False,
                wrap_method=row.get("method") or row.get("fill") or "cubic",
            )
        repairs.append(row)

    for nc, results in by_subject.items():
        out = os.path.join(repair_dir(nc), "chest_wrap_detect_report.json")
        write_json(out, stamped_payload(results))
        _log(f"[wrote] {out}")
        rep = os.path.join(repair_dir(nc), "wrap_repair_report.json")
        mine = [r for r in repairs if r["namecode"] == nc]
        write_json(rep, {"repairs": mine})
        _log(f"[wrote] {rep}")


if __name__ == "__main__":
    main()
