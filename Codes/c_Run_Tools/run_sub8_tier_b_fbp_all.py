"""SUB8: Tier-B FunctionBasedPath (numpy l(q)) SO for all MeasuredEHF failures.

Writes SO into the normal SO_MeasuredEHF folders. Shared scaled .osim is never
overwritten. Fit scratch / reports go under
``Codes/c_Run_Tools/chest_wrap_work/SUB8/``. JR is skipped.

Resume: re-run skips cases already marked so_ok in the report JSON.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
sys.path[:0] = [CODES_DIR, THIS_DIR]

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from chest_wrap_lib import (  # noqa: E402
    _apply_ik_row,
    _ik_in_degrees,
    import_opensim,
    repair_dir,
)
from chest_wrap_tier_b import _run_full_so, build_fbp_sidecar  # noqa: E402
from pipeline_rules import resolve_model_path  # noqa: E402
from update_pipeline_progress import (  # noqa: E402
    extract_freeze_sim_time,
    load_troubles,
)
from optimization.ricto_io import read_opensim_storage  # noqa: E402

NAMECODE = "260526_PJM"
APP = "MeasuredEHF"
MUSCLES = ["LTpT_T3_l", "LTpT_T3_r", "LTpT_T4_l", "LTpT_T4_r"]
SWAP_DL = 0.05
PAD_S = 0.01
TIMEOUT_S = 600.0
REPORT = os.path.join(repair_dir(NAMECODE), "sub8_tier_b_fbp_all_report.json")


def trouble_cases() -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for e in load_troubles():
        if str(e.get("namecode") or "") != NAMECODE:
            continue
        if str(e.get("tool") or "").lower() != "so":
            continue
        app = str(e.get("app") or APP)
        if app != APP:
            continue
        key = (str(e.get("condition") or ""), str(e.get("segment") or ""), app)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "namecode": NAMECODE,
            "condition": key[0],
            "segment": key[1],
            "app": app,
            "freeze_s": extract_freeze_sim_time(e),
            "tier": "B",
        })
    out.sort(key=lambda r: (r["condition"], r["segment"]))
    return out


def jump_islands(osim, model_path: str, ik_path: str) -> list[list[float]]:
    model = osim.Model(model_path)
    state = model.initSystem()
    ik_df, meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    indeg = _ik_in_degrees(meta)
    times = ik_df[tcol].to_numpy(dtype=float)
    objs = {m: model.getMuscles().get(m) for m in MUSCLES}
    lengths = {m: np.full(len(times), np.nan) for m in MUSCLES}
    for fi, (_, row) in enumerate(ik_df.iterrows()):
        _apply_ik_row(osim, model, state, row, indeg)
        for m, mus in objs.items():
            lengths[m][fi] = float(mus.getGeometryPath().getLength(state))
    raw: list[list[float]] = []
    for m in MUSCLES:
        a = lengths[m]
        jump = np.zeros(len(times), dtype=bool)
        for i in range(1, len(times)):
            if np.isfinite(a[i]) and np.isfinite(a[i - 1]) and abs(a[i] - a[i - 1]) >= SWAP_DL:
                jump[i] = True
        i = 1
        while i < len(times):
            if not jump[i]:
                i += 1
                continue
            sign = float(a[i] - a[i - 1])
            mag = abs(sign)
            j = i + 1
            while j < len(times):
                if jump[j] and np.isfinite(a[j]) and np.isfinite(a[j - 1]):
                    d = float(a[j] - a[j - 1])
                    if sign * d < 0 and abs(d) >= 0.5 * mag:
                        break
                j += 1
            end = j - 1 if j < len(times) else len(times) - 1
            raw.append([float(times[i]) - PAD_S, float(times[end]) + PAD_S])
            i = j + 1 if j < len(times) else len(times)
    raw.sort()
    merged: list[list[float]] = []
    for a, b in raw:
        if not merged or a > merged[-1][1] + 1e-9:
            merged.append([a, b])
        else:
            merged[-1][1] = max(merged[-1][1], b)
    return merged


def _load_report() -> dict:
    if os.path.isfile(REPORT):
        with open(REPORT, encoding="utf-8") as f:
            return json.load(f)
    return {"n_done": 0, "results": []}


def _save_report(report: dict) -> None:
    report["n_done"] = len(report["results"])
    report["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def main() -> None:
    cases = trouble_cases()
    report = _load_report()
    done = {
        (r["condition"], r["segment"]): r
        for r in report.get("results", [])
        if r.get("status") == "so_ok"
    }
    print(f"cases={len(cases)} already_ok={len(done)} report={REPORT}", flush=True)
    osim = import_opensim()
    rp = ResultPaths(NAMECODE)

    for k, case in enumerate(cases, start=1):
        key = (case["condition"], case["segment"])
        if key in done:
            print(f"[{k}/{len(cases)}] SKIP ok {key[0]} {key[1]}", flush=True)
            continue

        cp = ConditionPaths(rp, case["condition"])
        seg = case["segment"]
        model = resolve_model_path(rp, case["condition"], APP, "so", must_exist=True)
        ik = cp.ik_path(seg)
        row = {
            "condition": case["condition"],
            "segment": seg,
            "app": APP,
            "freeze_s": case.get("freeze_s"),
            "status": "pending",
        }
        if not os.path.isfile(ik):
            row["status"] = "missing_ik"
            report["results"] = [r for r in report["results"] if (r["condition"], r["segment"]) != key]
            report["results"].append(row)
            _save_report(report)
            print(f"[{k}/{len(cases)}] missing IK {key}", flush=True)
            continue

        work = os.path.join(
            repair_dir(NAMECODE),
            "tier_b_fbp_all",
            f"{case['condition']}_{seg}",
        )
        os.makedirs(work, exist_ok=True)
        try:
            islands = jump_islands(osim, model, ik)
        except Exception as exc:  # noqa: BLE001
            row["status"] = "island_scan_failed"
            row["error"] = str(exc)
            report["results"] = [r for r in report["results"] if (r["condition"], r["segment"]) != key]
            report["results"].append(row)
            _save_report(report)
            print(f"[{k}/{len(cases)}] island fail {key}: {exc}", flush=True)
            continue
        row["n_islands"] = len(islands)
        row["islands"] = islands

        sidecar = os.path.join(
            os.path.dirname(cp.so_path(seg, APP, "force")),
            f"SUB8_{case['condition']}_{seg}_{APP}_WrapFBP.osim",
        )
        print(
            f"[{k}/{len(cases)}] {case['condition']} {seg} "
            f"freeze={case.get('freeze_s')} islands={len(islands)}",
            flush=True,
        )
        t_fit = time.time()
        built = build_fbp_sidecar(
            model_path=model,
            ik_path=ik,
            islands=islands,
            muscles=MUSCLES,
            out_osim=sidecar,
            work_dir=work,
        )
        row["fit_s"] = round(time.time() - t_fit, 1)
        if not built:
            row["status"] = "fbp_fit_failed"
            report["results"] = [r for r in report["results"] if (r["condition"], r["segment"]) != key]
            report["results"].append(row)
            _save_report(report)
            continue
        row["sidecar"] = built

        t_so = time.time()
        try:
            _run_full_so(case, built, skip_jr=True, timeout_s=TIMEOUT_S)
            row["status"] = "so_ok"
            force = cp.so_path(seg, APP, "force")
            row["so_force"] = force
            row["so_force_exists"] = os.path.isfile(force)
            if os.path.isfile(force):
                row["so_force_bytes"] = os.path.getsize(force)
        except Exception as exc:  # noqa: BLE001
            row["status"] = "so_failed"
            row["error"] = str(exc)
            row["traceback"] = traceback.format_exc()[-1500:]
            ft = getattr(exc, "freeze_sim_time", None)
            if ft is not None:
                row["new_freeze_s"] = float(ft)
        row["so_s"] = round(time.time() - t_so, 1)

        report["results"] = [r for r in report["results"] if (r["condition"], r["segment"]) != key]
        report["results"].append(row)
        _save_report(report)
        print(
            f">>> {row['status']} fit={row.get('fit_s')} so={row.get('so_s')} "
            f"new_fr={row.get('new_freeze_s')}",
            flush=True,
        )

    ok = sum(1 for r in report["results"] if r.get("status") == "so_ok")
    fail = sum(1 for r in report["results"] if r.get("status") != "so_ok")
    print(f"DONE ok={ok} other={fail} report={REPORT}", flush=True)


if __name__ == "__main__":
    main()
