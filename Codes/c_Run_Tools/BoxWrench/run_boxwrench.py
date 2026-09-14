"""CLI for BoxWrench ExtLoad generation (Approach-5 allocation × RiCTO gate).

Examples
--------
# Synthetic smoke test (no OpenSim box BK required)
python run_boxwrench.py --synthetic --box-mass 7

# From box BK/States + RiCTO timeseries + HeavyHand ExtLoad template
python run_boxwrench.py --namecode 260512_KCH --condition 7kg_10bpm --segment 1AB \\
    --bk-vel PATH/Load_BodyKinematics_vel_global.sto \\
    --bk-pos PATH/Load_BodyKinematics_pos_global.sto \\
    --states PATH/Load_StatesReporter_states.sto
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_THIS = os.path.dirname(os.path.abspath(__file__))
_RUN_TOOLS = os.path.dirname(_THIS)
_CODES = os.path.dirname(_RUN_TOOLS)
for _p in (_CODES, _RUN_TOOLS, _THIS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import PATH_RULE as _path  # noqa: E402
from optimization.ricto_io import read_opensim_storage, save_csv  # noqa: E402

from boxwrench_allocate import allocate_hand_loads  # noqa: E402
from boxwrench_config import (  # noqa: E402
    APP_NAME,
    DEFAULT_BOX_OSIM,
    FORCE_ZERO_HAND_TORQUE,
    HANDLE_L_NOM,
    HANDLE_R_NOM,
    HANDLE_X_NOM,
    RICTO_WEIGHT_MODE,
)
from boxwrench_extload import (  # noqa: E402
    assert_no_measured_leak,
    build_boxwrench_extload,
    write_boxwrench_mot,
)
from boxwrench_inertia import load_box_props_for_condition  # noqa: E402
from boxwrench_kinematics import (  # noqa: E402
    compute_box_com_motion,
    compute_box_net_wrench,
)
from boxwrench_rotation import batch_rotmats  # noqa: E402


def _synthetic_motion(n: int = 200, dt: float = 0.01, mass_kg: float = 7.0):
    """Simple vertical lift kinematics for smoke test."""
    t = np.arange(n) * dt
    # COM rises then holds
    y = 0.3 + 0.4 * (1 - np.cos(np.pi * np.clip(t / 1.5, 0, 1))) / 2
    pos = np.column_stack([np.zeros(n), y, np.zeros(n)])
    vel = np.gradient(pos, dt, axis=0)
    acc = np.gradient(vel, dt, axis=0)
    ori = np.zeros((n, 3))
    R = batch_rotmats(ori)
    omega = np.zeros((n, 3))
    alpha = np.zeros((n, 3))
    motion = {
        "time": t,
        "pos_com_g": pos,
        "vel_com_g": vel,
        "acc_com_g": acc,
        "ori_deg": ori,
        "R_b2g": R,
        "omega": omega,
        "alpha": alpha,
    }
    props = load_box_props_for_condition(mass_kg, osim_path=DEFAULT_BOX_OSIM)
    wrench = compute_box_net_wrench(motion, props)
    return motion, wrench, props


def _make_heavyhand_template(t: np.ndarray, grf_y: float = 350.0) -> pd.DataFrame:
    n = len(t)
    z = np.zeros(n)
    data = {"time": t}
    for plate in (1, 2):
        data[f"ground_force{plate}_vx"] = z.copy()
        data[f"ground_force{plate}_vy"] = np.full(n, grf_y / 2)
        data[f"ground_force{plate}_vz"] = z.copy()
        for ax in ("x", "y", "z"):
            data[f"ground_force{plate}_p{ax}"] = z.copy()
            data[f"ground_torque{plate}_{ax}"] = z.copy()
    for plate in (3, 4):
        for ax in ("x", "y", "z"):
            data[f"hand_force{plate}_v{ax}"] = z.copy()
            data[f"hand_force{plate}_p{ax}"] = z.copy()
            data[f"hand_torque{plate}_{ax}"] = z.copy()
    return pd.DataFrame(data)


def run_synthetic(box_mass_kg: float, weight_mode: str) -> dict:
    motion, wrench, props = _synthetic_motion(mass_kg=box_mass_kg)
    t = motion["time"]
    # Fake RiCTO window covering mid lift
    ric = {"t1": 0.2, "d1": 0.15, "t2": 1.2, "d2": 0.15}
    # Active while weight would be on (rect for allocation mask)
    from optimization.ricto_optimize import rectangle_weight_curve, smooth_weight_curve

    w_rect = rectangle_weight_curve(t, ric["t1"], ric["d1"], ric["t2"], ric["d2"])
    alloc = allocate_hand_loads(wrench, motion, active_mask=w_rect > 0.5)
    ric["time"] = t
    ric["smooth_w"] = smooth_weight_curve(t, ric["t1"], ric["d1"], ric["t2"], ric["d2"])
    ric["rect_w"] = w_rect

    hh = _make_heavyhand_template(t)
    meta = {
        "header_lines": [
            f"name synthetic_{APP_NAME}.mot\n",
            f"nRows={len(t)}\n",
            f"nColumns={hh.shape[1]}\n",
            "inDegrees=no\n",
            "endheader\n",
        ]
    }
    with tempfile.TemporaryDirectory(prefix="boxwrench_syn_") as tmp:
        out = Path(tmp) / f"synthetic_ExtLoad_{APP_NAME}.mot"
        write_boxwrench_mot(
            str(out), hh, meta, alloc, ric=ric, weight_mode=weight_mode
        )
        df, _ = read_opensim_storage(out)
        leak = assert_no_measured_leak(df, None)

    fy_l = alloc["f_l"][:, 1]
    fy_r = alloc["f_r"][:, 1]
    return {
        "mass": props["mass"],
        "handle_l": tuple(HANDLE_L_NOM),
        "handle_r": tuple(HANDLE_R_NOM),
        "handle_x_nom": HANDLE_X_NOM,
        "n_success": int(alloc["n_success"][0]),
        "n_active": int(alloc["n_active"][0]),
        "fy_l_mean_active": float(np.mean(fy_l[w_rect > 0.5])) if np.any(w_rect > 0.5) else 0.0,
        "fy_r_mean_active": float(np.mean(fy_r[w_rect > 0.5])) if np.any(w_rect > 0.5) else 0.0,
        "static_half_weight": float(-0.5 * props["mass"] * abs(__import__("boxwrench_config", fromlist=["GRAVITY_Y"]).GRAVITY_Y)),
        "torque_zero": FORCE_ZERO_HAND_TORQUE,
        "leak_checks": leak,
        "weight_mode": weight_mode,
    }


def run_from_files(
    *,
    bk_vel: str,
    bk_pos: str,
    states: str,
    heavyhand_mot: str,
    out_mot: str,
    box_mass_kg: float,
    weight_mode: str,
    ricto_timeseries: Optional[str] = None,
    t1: Optional[float] = None,
    d1: Optional[float] = None,
    t2: Optional[float] = None,
    d2: Optional[float] = None,
    analysis_csv: Optional[str] = None,
) -> dict:
    props = load_box_props_for_condition(box_mass_kg, osim_path=DEFAULT_BOX_OSIM)
    motion = compute_box_com_motion(
        bk_vel_path=bk_vel, bk_pos_path=bk_pos, states_path=states
    )
    wrench = compute_box_net_wrench(motion, props)

    ts_df = None
    ric = None
    if ricto_timeseries and os.path.isfile(ricto_timeseries):
        ts_df = pd.read_csv(ricto_timeseries)
        w_for_mask = ts_df["w_rect"].to_numpy(dtype=float) if "w_rect" in ts_df.columns else ts_df["w_smooth"].to_numpy(dtype=float)
        t_w = ts_df["time"].to_numpy(dtype=float)
        active = np.interp(motion["time"], t_w, w_for_mask) > 0.5
    elif None not in (t1, d1, t2, d2):
        from optimization.ricto_optimize import rectangle_weight_curve, smooth_weight_curve

        ric = {
            "t1": float(t1),
            "d1": float(d1),
            "t2": float(t2),
            "d2": float(d2),
            "time": motion["time"],
            "smooth_w": smooth_weight_curve(motion["time"], float(t1), float(d1), float(t2), float(d2)),
            "rect_w": rectangle_weight_curve(motion["time"], float(t1), float(d1), float(t2), float(d2)),
        }
        active = ric["rect_w"] > 0.5
    else:
        active = np.ones(len(motion["time"]), dtype=bool)

    alloc = allocate_hand_loads(wrench, motion, active_mask=active)
    hh_df, hh_meta = read_opensim_storage(heavyhand_mot)
    write_boxwrench_mot(
        out_mot,
        hh_df,
        hh_meta,
        alloc,
        ric=ric,
        timeseries_df=ts_df,
        weight_mode=weight_mode,
    )

    if analysis_csv:
        save_csv(
            analysis_csv,
            pd.DataFrame(
                {
                    "time": alloc["time"],
                    "fx_l": alloc["f_l"][:, 0],
                    "fy_l": alloc["f_l"][:, 1],
                    "fz_l": alloc["f_l"][:, 2],
                    "fx_r": alloc["f_r"][:, 0],
                    "fy_r": alloc["f_r"][:, 1],
                    "fz_r": alloc["f_r"][:, 2],
                    "success": alloc["success"].astype(int),
                }
            ),
        )

    return {
        "out_mot": out_mot,
        "analysis_csv": analysis_csv,
        "n_success": int(alloc["n_success"][0]),
        "n_active": int(alloc["n_active"][0]),
        "mass": props["mass"],
    }


def run_modern_segment(
    *,
    namecode: str,
    condition: str,
    seg: str,
    bk_vel: str,
    bk_pos: str,
    states: str,
    weight_mode: str,
    box_mass_kg: Optional[float] = None,
) -> dict:
    rp = _path.ResultPaths(namecode)
    cp = rp.for_condition(condition)
    if box_mass_kg is None:
        from optimization.run_ricto import box_mass_from_condition

        box_mass_kg = box_mass_from_condition(condition)

    hh = cp.extload_path(seg, "HeavyHand")
    out = cp.extload_path(seg, APP_NAME)
    ts = cp.ricto_timeseries_path(seg) if hasattr(cp, "ricto_timeseries_path") else None
    # ConditionPaths may expose via parent
    if ts is None or not os.path.isfile(str(ts)):
        ts = os.path.join(
            rp.ricto_timeseries_dir(condition),
            f"{rp.sub_label}_{condition}_{seg}_RiCTO_timeseries.csv",
        )
    ana = os.path.join(
        rp.boxwrench_timeseries_dir(condition),
        f"{rp.sub_label}_{condition}_{seg}_BoxWrench_forces.csv",
    )
    return run_from_files(
        bk_vel=bk_vel,
        bk_pos=bk_pos,
        states=states,
        heavyhand_mot=hh,
        out_mot=out,
        box_mass_kg=float(box_mass_kg),
        weight_mode=weight_mode,
        ricto_timeseries=ts if os.path.isfile(ts) else None,
        analysis_csv=ana,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=f"{APP_NAME}: box wrench → L/R ExtLoad × RiCTO gate")
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--box-mass", type=float, default=7.0)
    p.add_argument("--ricto-weight", choices=("smooth", "rect"), default=RICTO_WEIGHT_MODE)
    p.add_argument("--namecode", default=None)
    p.add_argument("--condition", default=None)
    p.add_argument("--segment", default=None)
    p.add_argument("--bk-vel", default=None)
    p.add_argument("--bk-pos", default=None)
    p.add_argument("--states", default=None)
    p.add_argument("--heavyhand-mot", default=None)
    p.add_argument("--out-mot", default=None)
    p.add_argument("--ricto-timeseries", default=None)
    p.add_argument("--t1", type=float, default=None)
    p.add_argument("--d1", type=float, default=None)
    p.add_argument("--t2", type=float, default=None)
    p.add_argument("--d2", type=float, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if args.dry_run:
        print(f"[{APP_NAME}] dry-run ok | osim={DEFAULT_BOX_OSIM} exists={os.path.isfile(DEFAULT_BOX_OSIM)}")
        return 0

    if args.synthetic or not (args.bk_vel and args.bk_pos and args.states):
        if not args.synthetic and not (args.bk_vel and args.bk_pos and args.states):
            print(f"[{APP_NAME}] no box BK/States → synthetic smoke test")
        res = run_synthetic(args.box_mass, args.ricto_weight)
        print(f"[synthetic] {res}")
        # Sanity: mean vertical hand force should be near -mg/2 each when active & static-ish
        return 0

    if args.namecode and args.condition and args.segment:
        res = run_modern_segment(
            namecode=args.namecode,
            condition=args.condition,
            seg=args.segment,
            bk_vel=args.bk_vel,
            bk_pos=args.bk_pos,
            states=args.states,
            weight_mode=args.ricto_weight,
            box_mass_kg=args.box_mass,
        )
        print(f"[modern] {res}")
        return 0

    if not args.heavyhand_mot or not args.out_mot:
        print("Need --heavyhand-mot and --out-mot (or --namecode/--condition/--segment)")
        return 2

    res = run_from_files(
        bk_vel=args.bk_vel,
        bk_pos=args.bk_pos,
        states=args.states,
        heavyhand_mot=args.heavyhand_mot,
        out_mot=args.out_mot,
        box_mass_kg=args.box_mass,
        weight_mode=args.ricto_weight,
        ricto_timeseries=args.ricto_timeseries,
        t1=args.t1,
        d1=args.d1,
        t2=args.t2,
        d2=args.d2,
    )
    print(f"[files] {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
