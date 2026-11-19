"""SUB8: JR for MeasuredEHF trials that completed Tier-B FBP SO.

Uses the WrapFBP sidecar model and the SO force/activation already written
to SO_MeasuredEHF. Resumes from report JSON (skips jr_ok).
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
sys.path[:0] = [CODES_DIR, THIS_DIR]

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from chest_wrap_lib import repair_dir  # noqa: E402
from opensim_pipeline_handlers import prepare_jr_setup, run_jr  # noqa: E402

NAMECODE = "260526_PJM"
APP = "MeasuredEHF"
TIMEOUT_S = 600.0
SO_REPORT = os.path.join(repair_dir(NAMECODE), "sub8_tier_b_fbp_all_report.json")
JR_REPORT = os.path.join(repair_dir(NAMECODE), "sub8_tier_b_jr_all_report.json")


def so_ok_cases() -> list[dict]:
    with open(SO_REPORT, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for r in data.get("results", []):
        if r.get("status") != "so_ok":
            continue
        out.append({
            "condition": r["condition"],
            "segment": r["segment"],
            "app": APP,
            "sidecar": r.get("sidecar"),
            "so_force": r.get("so_force"),
        })
    out.sort(key=lambda x: (x["condition"], x["segment"]))
    return out


def _load_report() -> dict:
    if os.path.isfile(JR_REPORT):
        with open(JR_REPORT, encoding="utf-8") as f:
            return json.load(f)
    return {"results": []}


def _save_report(report: dict) -> None:
    report["n_done"] = len(report["results"])
    report["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(JR_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def main() -> None:
    cases = so_ok_cases()
    report = _load_report()
    done = {
        (r["condition"], r["segment"]): r
        for r in report.get("results", [])
        if r.get("status") == "jr_ok"
    }
    print(f"cases={len(cases)} already_ok={len(done)} report={JR_REPORT}", flush=True)
    rp = ResultPaths(NAMECODE)

    for k, case in enumerate(cases, start=1):
        key = (case["condition"], case["segment"])
        if key in done:
            print(f"[{k}/{len(cases)}] SKIP ok {key[0]} {key[1]}", flush=True)
            continue

        cp = ConditionPaths(rp, case["condition"])
        seg = case["segment"]
        sidecar = case.get("sidecar") or ""
        row = {
            "condition": case["condition"],
            "segment": seg,
            "app": APP,
            "sidecar": sidecar,
            "status": "pending",
        }
        if not os.path.isfile(sidecar):
            row["status"] = "missing_sidecar"
            report["results"] = [
                r for r in report["results"] if (r["condition"], r["segment"]) != key
            ]
            report["results"].append(row)
            _save_report(report)
            print(f"[{k}/{len(cases)}] missing sidecar {key}", flush=True)
            continue
        force = cp.so_path(seg, APP, "force")
        act = cp.so_path(seg, APP, "activation")
        if not os.path.isfile(force) or not os.path.isfile(act):
            row["status"] = "missing_so"
            report["results"] = [
                r for r in report["results"] if (r["condition"], r["segment"]) != key
            ]
            report["results"].append(row)
            _save_report(report)
            print(f"[{k}/{len(cases)}] missing SO {key}", flush=True)
            continue

        print(f"[{k}/{len(cases)}] JR {case['condition']} {seg}", flush=True)
        t0 = time.time()
        try:
            prepare_jr_setup(
                cp=cp, rp=rp, seg=seg, app=APP, model_path=sidecar,
            )
            run_jr(
                cp=cp, rp=rp, seg=seg, app=APP,
                timeout_s=TIMEOUT_S, model_path=sidecar,
            )
            row["status"] = "jr_ok"
            jr_child = cp.jr_path(seg, APP, "")
            row["jr_path"] = jr_child
            row["jr_exists"] = os.path.isfile(jr_child)
            if os.path.isfile(jr_child):
                row["jr_bytes"] = os.path.getsize(jr_child)
        except Exception as exc:  # noqa: BLE001
            row["status"] = "jr_failed"
            row["error"] = str(exc)
            row["traceback"] = traceback.format_exc()[-1500:]
        row["jr_s"] = round(time.time() - t0, 1)

        report["results"] = [
            r for r in report["results"] if (r["condition"], r["segment"]) != key
        ]
        report["results"].append(row)
        _save_report(report)
        print(
            f">>> {row['status']} jr_s={row.get('jr_s')} "
            f"exists={row.get('jr_exists')}",
            flush=True,
        )

    ok = sum(1 for r in report["results"] if r.get("status") == "jr_ok")
    other = sum(1 for r in report["results"] if r.get("status") != "jr_ok")
    print(f"DONE ok={ok} other={other} report={JR_REPORT}", flush=True)


if __name__ == "__main__":
    main()
