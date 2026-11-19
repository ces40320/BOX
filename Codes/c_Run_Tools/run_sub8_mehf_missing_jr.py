"""SUB8 MeasuredEHF: JR for segments that have SO but no JR (non-TierB leftovers)."""
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
from pipeline_rules import jr_suffixes, resolve_model_path  # noqa: E402

NAMECODE = "260526_PJM"
APP = "MeasuredEHF"
TIMEOUT_S = 600.0
REPORT = os.path.join(repair_dir(NAMECODE), "sub8_mehf_missing_jr_report.json")


def missing_jr_cases() -> list[dict]:
    rp = ResultPaths(NAMECODE)
    out = []
    for cond in ["7kg_10bpm", "15kg_10bpm", "7kg_16bpm", "15kg_16bpm"]:
        cp = ConditionPaths(rp, cond)
        cond_dir = os.path.join(rp.sub_dir, cond)
        if not os.path.isdir(cond_dir):
            continue
        for sec in sorted(os.listdir(cond_dir)):
            ik_dir = os.path.join(cond_dir, sec, "IK")
            if not os.path.isdir(ik_dir):
                continue
            for f in sorted(os.listdir(ik_dir)):
                if not f.endswith("_IK.mot"):
                    continue
                seg = f.replace(f"SUB8_{cond}_", "").replace("_IK.mot", "")
                so = cp.so_path(seg, APP, "force")
                jr = cp.jr_path(seg, APP, "")
                if os.path.isfile(so) and not os.path.isfile(jr):
                    fbp = os.path.join(
                        os.path.dirname(so),
                        f"SUB8_{cond}_{seg}_{APP}_WrapFBP.osim",
                    )
                    out.append({
                        "condition": cond,
                        "segment": seg,
                        "sidecar": fbp if os.path.isfile(fbp) else None,
                    })
    return out


def main() -> None:
    cases = missing_jr_cases()
    print(f"missing JR cases: {len(cases)}", flush=True)
    rp = ResultPaths(NAMECODE)
    results = []
    for k, case in enumerate(cases, start=1):
        cp = ConditionPaths(rp, case["condition"])
        seg = case["segment"]
        model = case["sidecar"] or resolve_model_path(
            rp, case["condition"], APP, "jr", must_exist=True,
        )
        row = {
            "condition": case["condition"],
            "segment": seg,
            "model": model,
            "used_fbp": bool(case["sidecar"]),
        }
        print(f"[{k}/{len(cases)}] JR {case['condition']} {seg} fbp={row['used_fbp']}", flush=True)
        t0 = time.time()
        try:
            prepare_jr_setup(cp=cp, rp=rp, seg=seg, app=APP, model_path=model)
            run_jr(cp=cp, rp=rp, seg=seg, app=APP, timeout_s=TIMEOUT_S, model_path=model)
            row["status"] = "jr_ok"
            row["jr_exists"] = os.path.isfile(cp.jr_path(seg, APP, ""))
        except Exception as exc:  # noqa: BLE001
            row["status"] = "jr_failed"
            row["error"] = str(exc)
            row["traceback"] = traceback.format_exc()[-1200:]
        row["jr_s"] = round(time.time() - t0, 1)
        results.append(row)
        with open(REPORT, "w", encoding="utf-8") as f:
            json.dump({"n": len(results), "results": results}, f, indent=2, ensure_ascii=False)
        print(f">>> {row['status']} jr_s={row['jr_s']}", flush=True)

    ok = sum(1 for r in results if r.get("status") == "jr_ok")
    print(f"DONE ok={ok}/{len(results)} report={REPORT}", flush=True)


if __name__ == "__main__":
    main()
