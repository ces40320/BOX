#!/usr/bin/env python3
"""Validate RiCTO policies: sign convention, solvers, optional real-data checks.

Usage
-----
    python validate_ricto.py --dummy
    python validate_ricto.py --dummy --solvers
    python validate_ricto.py --legacy-trial 1   # if OpenSim data present
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_THIS = Path(__file__).resolve().parent
_CODES = _THIS.parent.parent
if str(_CODES) not in sys.path:
    sys.path.insert(0, str(_CODES))
if str(_THIS.parent) not in sys.path:
    sys.path.insert(0, str(_THIS.parent))

from optimization.ricto_ehf import (  # noqa: E402
    estimate_ehf_from_acc,
    static_dummy_force,
)
from optimization.ricto_optimize import (  # noqa: E402
    compare_solvers,
    optimize_ricto,
    smooth_weight_curve,
    baseline_theory,
)
from optimization import ricto_config as cfg  # noqa: E402
import PATH_RULE as _path  # noqa: E402


def test_sign_dummies(box_mass_kg: float = 7.0) -> dict:
    """(a) static a=0 → fy < 0; (b) +ax → fx < 0."""
    f_static = static_dummy_force(box_mass_kg)
    m_h = box_mass_kg * cfg.MASS_SPLIT_ALPHA
    expect_fy = -m_h * abs(cfg.GRAVITY_Y)

    a_pos_x = np.array([[2.0, 0.0, 0.0]])
    pack = estimate_ehf_from_acc(
        np.array([0.0]), a_pos_x, a_pos_x, box_mass_kg
    )
    fx = float(pack["fx_r"][0])

    results = {
        "static_f": f_static.tolist(),
        "static_fy": float(f_static[1]),
        "expect_fy": float(expect_fy),
        "static_fy_ok": bool(np.isclose(f_static[1], expect_fy, rtol=1e-6)),
        "static_fx_ok": bool(np.isclose(f_static[0], 0.0, atol=1e-9)),
        "static_fz_ok": bool(np.isclose(f_static[2], 0.0, atol=1e-9)),
        "pos_x_acc_fx": fx,
        "pos_x_acc_fx_negative": bool(fx < 0.0),
        "hand_map": "force3=L, force4=R",
        "formula": "f = -m_h (a - g_vec)",
    }
    results["pass"] = all(
        [
            results["static_fy_ok"],
            results["static_fx_ok"],
            results["static_fz_ok"],
            results["pos_x_acc_fx_negative"],
        ]
    )
    return results


def _synthetic_residual(
    T: float = 6.0,
    dt: float = 0.01,
    box_mass_kg: float = 7.0,
    t1: float = 1.5,
    d1: float = 0.25,
    t2: float = 4.0,
    d2: float = 0.30,
    noise: float = 1.0,
    seed: int = 0,
):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, T + 1e-12, dt)
    B = baseline_theory(box_mass_kg)
    w = smooth_weight_curve(t, t1, d1, t2, d2)
    r = B * (1.0 - w) + rng.normal(0.0, noise, size=t.shape)
    return t, r, B, (t1, d1, t2, d2)


def test_solvers_synthetic(box_mass_kg: float = 7.0) -> pd.DataFrame:
    t, r, B, truth = _synthetic_residual(box_mass_kg=box_mass_kg)
    rows = compare_solvers(t, r, box_mass_kg)
    df = pd.DataFrame(rows)
    df["truth_t1"] = truth[0]
    df["truth_t2"] = truth[2]
    df["err_t1"] = df["t1"] - truth[0]
    df["err_t2"] = df["t2"] - truth[2]
    df["B_theory"] = B
    return df


def try_legacy_trial(task_num: int = 1, box_mass_kg: float = 15.0) -> dict:
    """Attempt real-data validation on legacy OneCycle layout if files exist."""
    from optimization.legacy_paths import legacy_onecycle_dirs

    dirs = legacy_onecycle_dirs()
    so_post = Path(dirs["so_postsim"])
    # typical half filenames from get_optimized_solution_and_EHF.py
    cand_force = list(so_post.glob(f"*_{task_num}_APP2_OneCycle_StaticOptimization_force_1st_half.sto"))
    cand_pos = list(Path(dirs["bk"]).glob("*BodyKinematics_pos_global.sto")) if Path(dirs["bk"]).is_dir() else []
    if not cand_force:
        return {"ok": False, "reason": f"no SO force half sto under {so_post}"}
    from optimization.ricto_io import extract_residual, read_opensim_storage, save_csv
    from optimization.ricto_ehf import ehf_from_bk_pos

    force_df, _ = read_opensim_storage(cand_force[0])
    t, r, tag = extract_residual(force_df, prefer="so")
    # shift to relative for this half file (legacy style) — also try absolute
    t_rel = t - t[0]
    sol_df = pd.DataFrame(compare_solvers(t_rel, r, box_mass_kg))
    out_csv = Path(dirs["analysis"]) / f"solver_compare_task{task_num}.csv"
    save_csv(out_csv, sol_df)

    ehf_info = {}
    if cand_pos:
        pos_df, _ = read_opensim_storage(cand_pos[0])
        # if full 12s pos, take first half by time for rough QC
        ehf, hands, qc = ehf_from_bk_pos(pos_df, box_mass_kg)
        ehf_info = {"qc": qc, "fy_r_mean": float(np.mean(ehf["fy_r"]))}

    return {
        "ok": True,
        "residual_source": tag,
        "force_file": str(cand_force[0]),
        "solver_csv": str(out_csv),
        "best_solver": sol_df.sort_values("cost").iloc[0].to_dict(),
        "ehf": ehf_info,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate RiCTO core policies")
    ap.add_argument("--dummy", action="store_true", help="Run sign-convention dummies")
    ap.add_argument("--solvers", action="store_true", help="Compare solvers on synthetic residual")
    ap.add_argument("--legacy-trial", type=int, default=None, help="Optional real-data trial index")
    ap.add_argument("--box-mass", type=float, default=7.0)
    args = ap.parse_args()

    if not args.dummy and not args.solvers and args.legacy_trial is None:
        args.dummy = True
        args.solvers = True

    analysis = Path(_path.ANALYSIS_DIR) / "RiCTO" / "_validation"
    analysis.mkdir(parents=True, exist_ok=True)

    if args.dummy:
        res = test_sign_dummies(args.box_mass)
        print("[sign-dummy]", res)
        if not res["pass"]:
            raise SystemExit("Sign dummy FAILED")
        print("[sign-dummy] PASS")

    if args.solvers:
        df = test_solvers_synthetic(args.box_mass)
        out = analysis / "solver_compare_synthetic.csv"
        df.to_csv(out, index=False)
        print("[solvers] wrote", out)
        print(df.to_string(index=False))
        best = df.sort_values("cost").iloc[0]
        print(
            f"[solvers] best={best['solver']} cost={best['cost']:.3f} "
            f"err_t1={best['err_t1']:.3f}s err_t2={best['err_t2']:.3f}s"
        )

    if args.legacy_trial is not None:
        info = try_legacy_trial(args.legacy_trial, box_mass_kg=args.box_mass)
        print("[legacy]", info)


if __name__ == "__main__":
    main()
