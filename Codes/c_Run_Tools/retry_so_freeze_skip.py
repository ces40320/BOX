"""Skip a mid-window SO freeze frame by stitching front + back segments.

For each (namecode, condition, segment, app, freeze_sim_time):

1. SO front: TRC start → freeze − ``skip_before`` (exclusive of the hung frame)
2. SO back: freeze + ``skip_after`` → TRC end
3. Stitch force/activation (gap filled by holding the last front row)
4. JR on the stitched SO over the full TRC window

The skipped ~0.04 s is not physics — it is a hold bridge so downstream
time grids stay continuous. ``controls.xml`` is left as the back-only
OpenSim dump (JR consumes activation + force).

Example::

    python retry_so_freeze_skip.py
    python retry_so_freeze_skip.py --seg 4CA --skip-jr
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.append(CODES_DIR)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from opensim_pipeline_handlers import (  # noqa: E402
    prepare_jr_setup,
    prepare_so_setup,
    run_jr,
    run_so,
)
from optimization.ricto_io import (  # noqa: E402
    read_opensim_storage,
    write_opensim_storage,
)
from update_pipeline_progress import (  # noqa: E402
    default_trouble_path,
    extract_freeze_sim_time,
    load_troubles,
    record_trouble,
    refresh_progress_sheet,
    sub_number_for_namecode,
    sync_freeze_sim_times_from_troubles,
)

# KMJ segments that hung at the same sim-time across all ExtLoad apps.
DEFAULT_NAMECODE = "260519_KMJ"
DEFAULT_CONDITION = "10kg_16bpm"
SEGMENT_FREEZES_S: dict[str, float] = {
    "4CA": 1.42,
    "8CA": 1.51,
    "9CA": 1.43,
    "10BC": 2.2,
}
ALL_APPS: tuple[str, ...] = (
    "MeasuredEHF",
    "HeavyHand",
    "preRiCTO",
    "postRiCTO",
)


def _builtin_cases(apps: list[str]) -> list[dict]:
    return [
        {
            "namecode": DEFAULT_NAMECODE,
            "condition": DEFAULT_CONDITION,
            "segment": seg,
            "app": app,
            "freeze_sim_time": freeze,
        }
        for seg, freeze in SEGMENT_FREEZES_S.items()
        for app in apps
    ]

SO_TYPES = ("force", "activation")
SKIP_BEFORE_S = 0.01
SKIP_AFTER_S = 0.03
_TIME_TOL = 5e-4

# Live batch status written on every fail (and at end).
FREEZE_SKIP_REPORT_NAME = "pipeline_freeze_skip_report.json"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _freeze_from_exc(exc: BaseException) -> float | None:
    """New hang time from AnalyzeTool stall ``RuntimeError``, if known."""
    raw = getattr(exc, "freeze_sim_time", None)
    if raw is not None and raw != "":
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    return extract_freeze_sim_time({"error": str(exc)})


def _report_path() -> str:
    return os.path.join(
        os.path.dirname(default_trouble_path()),
        FREEZE_SKIP_REPORT_NAME,
    )


def _write_freeze_skip_report(
    *,
    succeeded: list[dict],
    failed: list[dict],
    namecode: str | None,
) -> str:
    """Overwrite the live freeze-skip report JSON; return its path."""
    import json
    from datetime import datetime

    path = _report_path()
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "namecode": namecode,
        "n_succeeded": len(succeeded),
        "n_failed": len(failed),
        "succeeded": succeeded,
        "failed": failed,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def _format_case_list(rows: list[dict]) -> str:
    if not rows:
        return "(none)"
    parts = []
    for r in rows:
        ft = r.get("freeze_sim_time")
        prior = r.get("prior_freeze")
        if ft is not None:
            parts.append(
                f"{r['condition']}/{r['segment']}@{float(ft):g}s"
            )
        elif prior is not None:
            parts.append(
                f"{r['condition']}/{r['segment']}(skip@{float(prior):g})"
            )
        else:
            parts.append(f"{r['condition']}/{r['segment']}")
    return ", ".join(parts)


def _print_fail_report(
    *,
    fail_row: dict,
    succeeded: list[dict],
    failed: list[dict],
    report_path: str,
) -> None:
    prior = fail_row.get("prior_freeze")
    new_ft = fail_row.get("freeze_sim_time")
    prior_txt = f"{float(prior):g}" if prior is not None else "?"
    new_txt = f"{float(new_ft):g}" if new_ft is not None else "unknown"
    _log("=" * 60)
    _log(
        f"[REPORT] FAIL  {fail_row['condition']} / {fail_row['segment']}  "
        f"app={fail_row.get('app')}  "
        f"this_freeze={new_txt}s  (prior_skip_target={prior_txt}s)"
    )
    _log(f"  failed so far ({len(failed)}): {_format_case_list(failed)}")
    _log(
        f"  succeeded so far ({len(succeeded)}): "
        f"{_format_case_list(succeeded)}"
    )
    _log(f"  json → {report_path}")
    _log("=" * 60)


def _round_time(t: float) -> float:
    return round(float(t) + 1e-9, 2)


def _so_paths(cp: ConditionPaths, seg: str, app: str) -> dict[str, str]:
    return {t: cp.so_path(seg, app, t) for t in SO_TYPES}


def _side_path(canonical: str, tag: str) -> str:
    p = Path(canonical)
    return str(p.with_name(p.stem + f".{tag}" + p.suffix))


def _move_so_outputs(paths: dict[str, str], tag: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for kind, src in paths.items():
        if not os.path.isfile(src):
            raise FileNotFoundError(f"SO {kind} missing after run: {src}")
        dst = _side_path(src, tag)
        if os.path.isfile(dst):
            os.remove(dst)
        shutil.move(src, dst)
        out[kind] = dst
    # Drop controls.xml so a later back run is not confused with a partial.
    sample = next(iter(paths.values()))
    controls = sample.replace("_force.sto", "_controls.xml").replace(
        "_activation.sto", "_controls.xml"
    )
    if controls.endswith("_controls.xml") and os.path.isfile(controls):
        side = _side_path(controls, tag)
        if os.path.isfile(side):
            os.remove(side)
        shutil.move(controls, side)
    return out


def _delete_if_exists(paths: list[str]) -> None:
    for p in paths:
        if os.path.isfile(p):
            os.remove(p)


def _infer_dt(times: np.ndarray) -> float:
    if len(times) < 2:
        return 0.01
    d = np.diff(times)
    d = d[d > 1e-6]
    if len(d) == 0:
        return 0.01
    return float(np.median(d))


def stitch_storage(
    front_path: str,
    back_path: str,
    out_path: str,
) -> tuple[int, float, float]:
    """Concat front + hold-gap + back → ``out_path``. Returns (n, t0, t1)."""
    fdf, fmeta = read_opensim_storage(front_path)
    bdf, _ = read_opensim_storage(back_path)
    tcol = "time" if "time" in fdf.columns else "Time"
    if tcol not in bdf.columns:
        raise ValueError(f"back sto missing time column: {back_path}")

    # Align columns (back may miss rare labels — intersect keep order of front).
    cols = [c for c in fdf.columns if c in bdf.columns]
    if tcol not in cols:
        raise ValueError("time column lost during column align")
    fdf = fdf[cols].copy()
    bdf = bdf[cols].copy()

    ft = float(fdf[tcol].iloc[-1])
    bt = float(bdf[tcol].iloc[0])
    dt = _infer_dt(fdf[tcol].to_numpy(dtype=float))

    pieces = [fdf]
    if bt > ft + _TIME_TOL:
        hold = fdf.iloc[[-1]].copy()
        gap_rows = []
        t = ft + dt
        while t < bt - _TIME_TOL:
            row = hold.copy()
            row.loc[:, tcol] = t
            gap_rows.append(row)
            t = _round_time(t + dt)
        if gap_rows:
            pieces.append(pd.concat(gap_rows, ignore_index=True))
    pieces.append(bdf)

    out = pd.concat(pieces, ignore_index=True)
    out = out.drop_duplicates(subset=[tcol], keep="first")
    out = out.sort_values(tcol).reset_index(drop=True)
    write_opensim_storage(out_path, out, fmeta)
    return len(out), float(out[tcol].iloc[0]), float(out[tcol].iloc[-1])


def resolve_cases(
    *,
    namecode: str | None,
    condition: str | None,
    segments: set[str] | None,
    apps: set[str] | None,
    from_trouble: bool,
) -> list[dict]:
    if from_trouble:
        cases: list[dict] = []
        for e in load_troubles():
            if str(e.get("tool") or "").lower() != "so":
                continue
            ft = extract_freeze_sim_time(e)
            if ft is None:
                continue
            cases.append(
                {
                    "namecode": str(e["namecode"]),
                    "condition": str(e["condition"]),
                    "segment": str(e["segment"]),
                    "app": str(e.get("app") or "MeasuredEHF"),
                    "freeze_sim_time": float(ft),
                }
            )
    else:
        use_apps = sorted(apps) if apps else list(ALL_APPS[:1])  # MeasuredEHF
        cases = _builtin_cases(use_apps)

    out: list[dict] = []
    for c in cases:
        if namecode and c["namecode"] != namecode:
            continue
        if condition and c["condition"] != condition:
            continue
        if segments and c["segment"] not in segments:
            continue
        if apps and c["app"] not in apps:
            continue
        out.append(c)
    return out


def run_one_case(
    case: dict,
    *,
    skip_before: float,
    skip_after: float,
    skip_jr: bool,
    timeout_s: float | None,
    dry_run: bool,
) -> None:
    namecode = case["namecode"]
    cond = case["condition"]
    seg = case["segment"]
    app = case["app"]
    freeze = float(case["freeze_sim_time"])
    front_end = _round_time(freeze - skip_before)
    back_start = _round_time(freeze + skip_after)

    rp = ResultPaths(namecode)
    cp = ConditionPaths(rp, cond)
    paths = _so_paths(cp, seg, app)
    ctrl = paths["force"].replace("_force.sto", "_controls.xml")
    all_scratch = (
        list(paths.values())
        + [_side_path(p, "front") for p in paths.values()]
        + [_side_path(p, "back") for p in paths.values()]
        + [ctrl, _side_path(ctrl, "front"), _side_path(ctrl, "back")]
    )

    _log(
        f"===== {namecode} {cond} {seg} {app}  "
        f"freeze={freeze:g}  front_end={front_end:g}  "
        f"back_start={back_start:g} ====="
    )
    if not (front_end < freeze < back_start):
        raise ValueError(
            f"bad skip window: front_end={front_end} freeze={freeze} "
            f"back_start={back_start}"
        )

    if dry_run:
        _log(f"  [dry] would SO front → {front_end:g}, back → {back_start:g}, stitch, JR")
        return

    # Clear stale canonical / side outputs before front.
    _delete_if_exists(all_scratch)

    try:
        _log(f"[SO front] end={front_end:g}")
        prepare_so_setup(cp=cp, rp=rp, seg=seg, app=app, end_time=front_end)
        run_so(cp=cp, rp=rp, seg=seg, app=app, timeout_s=timeout_s)
        front_paths = _move_so_outputs(paths, "front")
        _log(f"  front saved → {front_paths['force']}")

        _log(f"[SO back] start={back_start:g}")
        prepare_so_setup(cp=cp, rp=rp, seg=seg, app=app, start_time=back_start)
        run_so(cp=cp, rp=rp, seg=seg, app=app, timeout_s=timeout_s)
        back_paths = _move_so_outputs(paths, "back")
        _log(f"  back saved → {back_paths['force']}")

        for kind in SO_TYPES:
            n, t0, t1 = stitch_storage(
                front_paths[kind], back_paths[kind], paths[kind]
            )
            _log(
                f"  [stitch {kind}] n={n}  t=[{t0:.4g}, {t1:.4g}] → {paths[kind]}"
            )

        back_ctrl = _side_path(ctrl, "back")
        if os.path.isfile(back_ctrl):
            shutil.copy2(back_ctrl, ctrl)

        if skip_jr:
            _log(f"[OK] {seg}/{app} SO stitch done (JR skipped)")
            return

        _log("[JR] full TRC window on stitched SO")
        prepare_jr_setup(cp=cp, rp=rp, seg=seg, app=app)
        run_jr(cp=cp, rp=rp, seg=seg, app=app, timeout_s=timeout_s)
        _log(f"[OK] {seg}/{app} SO stitch + JR done")
    except Exception:
        # Leave no half-written canonical SO that looks "resolved".
        _delete_if_exists(list(paths.values()) + [ctrl])
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SO freeze-skip stitch (front + back) then JR",
    )
    parser.add_argument(
        "--namecode",
        default=None,
        help="Subject namecode filter. Default: built-in KMJ when not "
             "--from-trouble, else all namecodes in trouble file.",
    )
    parser.add_argument(
        "--condition",
        default=None,
        help="Condition filter (e.g. 10kg_16bpm). Default: no filter "
             "(built-in KMJ list uses 10kg_16bpm).",
    )
    parser.add_argument(
        "--seg",
        default=None,
        help="Comma-separated segments (default: built-in KMJ freeze list)",
    )
    parser.add_argument(
        "--exclude",
        default=None,
        help="Comma-separated skips: 'SEG' or 'cond/SEG' "
             "(e.g. 1AB,15kg_10bpm/1AB).",
    )
    parser.add_argument(
        "--apps",
        default="MeasuredEHF",
        help="Comma-separated ExtLoad apps "
             "(MeasuredEHF,HeavyHand,preRiCTO,postRiCTO). "
             "Default: MeasuredEHF only.",
    )
    parser.add_argument(
        "--cascade-apps",
        default="",
        help="After each primary-app success, also run these apps with the "
             "same freeze window (e.g. HeavyHand,preRiCTO,postRiCTO).",
    )
    parser.add_argument(
        "--from-trouble",
        action="store_true",
        help="Take cases from pipeline_trouble.json (SO + freeze_sim_time)",
    )
    parser.add_argument(
        "--skip-before",
        type=float,
        default=SKIP_BEFORE_S,
        help="Front ends at freeze − this (s). Default 0.01",
    )
    parser.add_argument(
        "--skip-after",
        type=float,
        default=SKIP_AFTER_S,
        help="Back starts at freeze + this (s). Default 0.03",
    )
    parser.add_argument("--skip-jr", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=120.0,
        help="AnalyzeTool log-stall budget in seconds (default: 120). "
             "On stall the case is cancelled and the next trial starts. "
             "Pass 0 or a negative value to use the handler default (300s).",
    )
    parser.add_argument(
        "--soft-exit",
        action="store_true",
        help="Exit 0 even if some cases failed (still prints failed list).",
    )
    parser.add_argument(
        "--no-refresh-sheet",
        action="store_true",
        help="Do not refresh pipeline_progress.xlsx after success",
    )
    args = parser.parse_args()

    timeout_s = args.timeout_s
    if timeout_s is not None and timeout_s <= 0:
        timeout_s = None  # handler DEFAULT_ANALYZE_TIMEOUT_S (300s)

    segs = None
    if args.seg:
        segs = {s.strip() for s in args.seg.split(",") if s.strip()}
    apps = {a.strip() for a in args.apps.split(",") if a.strip()}
    cascade = [a.strip() for a in args.cascade_apps.split(",") if a.strip()]
    exclude_raw = [
        x.strip() for x in (args.exclude or "").split(",") if x.strip()
    ]

    def _excluded(cond: str, seg: str) -> bool:
        for ex in exclude_raw:
            if "/" in ex:
                c, s = ex.split("/", 1)
                if cond == c and seg == s:
                    return True
            elif seg == ex:
                return True
        return False

    namecode = args.namecode
    condition = args.condition
    if not args.from_trouble:
        namecode = namecode or DEFAULT_NAMECODE
        condition = condition or DEFAULT_CONDITION
        if not apps:
            apps = {"MeasuredEHF"}

    cases = resolve_cases(
        namecode=namecode,
        condition=condition,
        segments=segs,
        apps=apps or None,
        from_trouble=args.from_trouble,
    )
    if exclude_raw:
        before = len(cases)
        cases = [c for c in cases if not _excluded(c["condition"], c["segment"])]
        _log(f"[exclude] dropped {before - len(cases)} case(s); {exclude_raw}")

    if not cases:
        raise SystemExit("No cases to run")

    def _seg_key(seg: str) -> tuple:
        digits = "".join(ch for ch in seg if ch.isdigit())
        return (int(digits) if digits else 0, seg)

    cases.sort(
        key=lambda c: (
            c["condition"],
            _seg_key(c["segment"]),
            c["app"],
        )
    )

    _log(f"cases ({len(cases)}):")
    for c in cases:
        _log(
            f"  {c['namecode']} {c['condition']} {c['segment']} "
            f"{c['app']} freeze={c['freeze_sim_time']:g}"
        )
    if cascade:
        _log(f"cascade after success: {cascade}")
    stall_txt = (
        f"{timeout_s:.0f}s" if timeout_s is not None else "handler-default"
    )
    _log(f"log-stall timeout: {stall_txt}  skip_jr={args.skip_jr}")

    failed: list[str] = []
    ok_namecodes: set[str] = set()
    succeeded_rows: list[dict] = []
    failed_rows: list[dict] = []

    def _run_labeled(case: dict) -> bool:
        label = f"{case['condition']}/{case['segment']}/{case['app']}"
        prior = float(case["freeze_sim_time"])
        try:
            run_one_case(
                case,
                skip_before=args.skip_before,
                skip_after=args.skip_after,
                skip_jr=args.skip_jr,
                timeout_s=timeout_s,
                dry_run=args.dry_run,
            )
            ok_namecodes.add(case["namecode"])
            succeeded_rows.append(
                {
                    "namecode": case["namecode"],
                    "condition": case["condition"],
                    "segment": case["segment"],
                    "app": case["app"],
                    "prior_freeze": prior,
                }
            )
            return True
        except Exception as exc:
            new_ft = _freeze_from_exc(exc)
            fail_row = {
                "namecode": case["namecode"],
                "condition": case["condition"],
                "segment": case["segment"],
                "app": case["app"],
                "prior_freeze": prior,
                "freeze_sim_time": new_ft,
                "error": str(exc)[:500],
            }
            failed_rows.append(fail_row)
            failed.append(label)
            _log(f"[FAIL] {label}: {type(exc).__name__}: {exc}")

            if not args.dry_run:
                try:
                    err_txt = (
                        f"freeze-skip retry failed "
                        f"(prior_skip_target_s={prior:g}).\n{exc}"
                    )
                    record_trouble(
                        namecode=case["namecode"],
                        condition=case["condition"],
                        segment=case["segment"],
                        tool="so",
                        app=case["app"],
                        error=err_txt,
                        freeze_sim_time=new_ft,
                    )
                    sync_freeze_sim_times_from_troubles(
                        namecodes=[case["namecode"]],
                    )
                except Exception as rec_exc:
                    _log(f"[WARN] trouble JSON update failed: {rec_exc}")

                try:
                    path = _write_freeze_skip_report(
                        succeeded=succeeded_rows,
                        failed=failed_rows,
                        namecode=args.namecode,
                    )
                    _print_fail_report(
                        fail_row=fail_row,
                        succeeded=succeeded_rows,
                        failed=failed_rows,
                        report_path=path,
                    )
                except Exception as rep_exc:
                    _log(f"[WARN] freeze-skip report failed: {rep_exc}")

            _log("[SKIP] moving on → next trial")
            return False

    for c in cases:
        if not _run_labeled(c):
            continue
        for app in cascade:
            if app == c["app"]:
                continue
            _run_labeled({**c, "app": app})

    if not args.dry_run:
        try:
            path = _write_freeze_skip_report(
                succeeded=succeeded_rows,
                failed=failed_rows,
                namecode=args.namecode,
            )
            _log(
                f"[report] final  ok={len(succeeded_rows)}  "
                f"fail={len(failed_rows)}  → {path}"
            )
        except Exception as exc:
            _log(f"[report] final write skipped: {exc}")

    if not args.dry_run and not args.no_refresh_sheet and ok_namecodes:
        try:
            subs = []
            for nc in sorted(ok_namecodes):
                try:
                    subs.append(sub_number_for_namecode(nc))
                except Exception:
                    pass
            if subs:
                refresh_progress_sheet(sorted(set(subs)))
                _log(f"[sheet] refreshed SUB{sorted(set(subs))}")
        except Exception as exc:
            _log(f"[sheet] refresh skipped: {exc}")

    if failed:
        _log(f"failed ({len(failed)}): {', '.join(failed)}")
        if not args.soft_exit:
            raise SystemExit(f"failed: {', '.join(failed)}")
    _log("all cases OK" if not failed else "batch finished (some failed)")


if __name__ == "__main__":
    main()
