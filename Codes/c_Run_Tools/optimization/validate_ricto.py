#!/usr/bin/env python3
"""Validate RiCTO policies: sign convention, solvers, real-data batch checks.

Usage
-----
    python validate_ricto.py --dummy
    python validate_ricto.py --dummy --solvers
    python validate_ricto.py --legacy-trial 1   # if OpenSim data present

    # Real-data batch: MeasuredEHF GT contact vs f_est / RicTO times
    python validate_ricto.py --all --protocols Asymmetric
    python validate_ricto.py --all --protocols Asymmetric --fy-thresh 2
    # → writes realdata_all_summary_fy5.csv / _fy2.csv (no clobber)
    python validate_ricto.py --all --namecodes 260306_KTY --conditions 7kg_10bpm \\
        --segments 1AB --dry-run

    # Overlay MeasuredEHF / preRiCTO / postRiCTO hand forces
    python validate_ricto.py --plot --namecode 260306_KTY --condition 7kg_10bpm \\
        --segments 1AB
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

_THIS = Path(__file__).resolve().parent
_CODES = _THIS.parent.parent
_RUN_TOOLS = _THIS.parent
for p in (_CODES, _RUN_TOOLS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from optimization.ricto_ehf import (  # noqa: E402
    ehf_from_bk_pos,
    estimate_ehf_from_acc,
    static_dummy_force,
)
from optimization.ricto_io import (  # noqa: E402
    extract_residual,
    read_opensim_storage,
    save_csv,
)
from optimization.ricto_optimize import (  # noqa: E402
    baseline_theory,
    compare_solvers,
    optimize_ricto,
    smooth_weight_curve,
)
from optimization import ricto_config as cfg  # noqa: E402
from optimization.run_ricto import (  # noqa: E402
    _csv_set,
    box_mass_from_condition,
    iter_modern_jobs,
)
import PATH_RULE as _path  # noqa: E402

# Match config_methods Asymmetric segmentation defaults (validation GT only).
DEFAULT_FY_THRESH_N: float = 5.0
DEFAULT_MIN_CONTACT_DUR_S: float = 0.30


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
    cand_force = list(so_post.glob(f"*_{task_num}_APP2_OneCycle_StaticOptimization_force_1st_half.sto"))
    cand_pos = list(Path(dirs["bk"]).glob("*BodyKinematics_pos_global.sto")) if Path(dirs["bk"]).is_dir() else []
    if not cand_force:
        return {"ok": False, "reason": f"no SO force half sto under {so_post}"}

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


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size < 3 or b.size < 3:
        return float("nan")
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _rmse(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((a - b) ** 2)))


def detect_contact_windows(
    time_s: np.ndarray,
    fy_l: np.ndarray,
    fy_r: np.ndarray,
    *,
    thresh_n: float = DEFAULT_FY_THRESH_N,
    min_dur_s: float = DEFAULT_MIN_CONTACT_DUR_S,
) -> list[tuple[float, float]]:
    """Contact windows where |Fy_L| + |Fy_R| exceeds threshold for >= min_dur."""
    t = np.asarray(time_s, dtype=float)
    total = np.abs(np.asarray(fy_l, dtype=float)) + np.abs(np.asarray(fy_r, dtype=float))
    contact = total > float(thresh_n)
    if not np.any(contact):
        return []

    padded = np.concatenate([[False], contact, [False]])
    d = np.diff(padded.astype(int))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]  # exclusive index into contact
    wins: list[tuple[float, float]] = []
    for s, e in zip(starts, ends):
        if e <= s:
            continue
        t_on = float(t[s])
        t_off = float(t[e - 1])
        if (t_off - t_on) >= float(min_dur_s):
            wins.append((t_on, t_off))
    return wins


def _longest_window(wins: list[tuple[float, float]]) -> Optional[tuple[float, float]]:
    if not wins:
        return None
    return max(wins, key=lambda w: w[1] - w[0])


def _interp_force_onto(
    t_src: np.ndarray,
    cols: dict[str, np.ndarray],
    t_dst: np.ndarray,
) -> dict[str, np.ndarray]:
    t_src = np.asarray(t_src, dtype=float)
    t_dst = np.asarray(t_dst, dtype=float)
    out = {}
    for k, y in cols.items():
        out[k] = np.interp(t_dst, t_src, np.asarray(y, dtype=float))
    return out


def _axis_pair_metrics(
    est: np.ndarray,
    meas: np.ndarray,
    mask: np.ndarray,
    prefix: str,
) -> dict[str, float]:
    e = est[mask]
    m = meas[mask]
    return {
        f"corr_{prefix}": _corr(e, m),
        f"rmse_{prefix}": _rmse(e, m),
        f"n_{prefix}": int(mask.sum()),
    }


def validate_modern_segment(
    *,
    namecode: str,
    condition: str,
    seg: str,
    box_mass_kg: float,
    solver: str = cfg.DEFAULT_SOLVER,
    fy_thresh_n: float = DEFAULT_FY_THRESH_N,
    min_contact_dur_s: float = DEFAULT_MIN_CONTACT_DUR_S,
) -> dict:
    """Compare kinematics EHF vs MeasuredEHF and RicTO times vs GT contact."""
    rp = _path.ResultPaths(namecode)
    cp = rp.for_condition(condition)

    id_path = cp.id_path(seg, "HeavyHand")
    so_path = cp.so_path(seg, "HeavyHand", "force")
    bk_path = cp.bk_path(seg, "pos_global")
    me_path = cp.extload_path(seg, "MeasuredEHF")

    residual_path = id_path if os.path.isfile(id_path) else so_path
    prefer = "id" if residual_path == id_path else "so"
    for pth, label in (
        (residual_path, "residual ID/SO"),
        (bk_path, "BK pos_global"),
        (me_path, "MeasuredEHF MOT"),
    ):
        if not os.path.isfile(pth):
            raise FileNotFoundError(f"missing {label}: {pth}")

    rdf, _ = read_opensim_storage(residual_path)
    t_res, r, tag = extract_residual(rdf, prefer=prefer)
    ric = optimize_ricto(t_res, r, box_mass_kg, solver=solver)

    pos_df, _ = read_opensim_storage(bk_path)
    ehf, _hands, qc = ehf_from_bk_pos(pos_df, box_mass_kg)
    t_bk = ehf["time"]

    me_df, _ = read_opensim_storage(me_path)
    need = [
        "hand_force3_vx",
        "hand_force3_vy",
        "hand_force3_vz",
        "hand_force4_vx",
        "hand_force4_vy",
        "hand_force4_vz",
    ]
    missing = [c for c in need if c not in me_df.columns]
    if missing:
        raise KeyError(f"MeasuredEHF missing columns: {missing}")

    t_me = me_df["time"].to_numpy(dtype=float)
    meas_hi = {
        "fx_l": me_df["hand_force3_vx"].to_numpy(dtype=float),
        "fy_l": me_df["hand_force3_vy"].to_numpy(dtype=float),
        "fz_l": me_df["hand_force3_vz"].to_numpy(dtype=float),
        "fx_r": me_df["hand_force4_vx"].to_numpy(dtype=float),
        "fy_r": me_df["hand_force4_vy"].to_numpy(dtype=float),
        "fz_r": me_df["hand_force4_vz"].to_numpy(dtype=float),
    }
    # GT windows on native MeasuredEHF rate; metrics on BK grid.
    wins = detect_contact_windows(
        t_me,
        meas_hi["fy_l"],
        meas_hi["fy_r"],
        thresh_n=fy_thresh_n,
        min_dur_s=min_contact_dur_s,
    )
    primary = _longest_window(wins)
    if primary is None:
        raise RuntimeError(
            f"no MeasuredEHF contact window (|Fy_L|+|Fy_R|>{fy_thresh_n}N, "
            f">={min_contact_dur_s}s)"
        )
    gt_onset, gt_offset = primary

    meas = _interp_force_onto(t_me, meas_hi, t_bk)
    contact_mask = (t_bk >= gt_onset) & (t_bk <= gt_offset)

    row: dict = {
        "ok": True,
        "namecode": namecode,
        "protocol": rp.protocol,
        "sub": rp.sub_label,
        "condition": condition,
        "seg": seg,
        "box_mass_kg": float(box_mass_kg),
        "residual_source": tag,
        "solver": ric["solver"],
        "success": bool(ric["success"]),
        "cost": float(ric["cost"]),
        "t1": float(ric["t1"]),
        "d1": float(ric["d1"]),
        "t2": float(ric["t2"]),
        "d2": float(ric["d2"]),
        "ricto_onset": float(ric["t1"]),
        "ricto_offset": float(ric["t2"] + ric["d2"]),
        "gt_onset": float(gt_onset),
        "gt_offset": float(gt_offset),
        "err_onset_s": float(ric["t1"] - gt_onset),
        "err_offset_s": float((ric["t2"] + ric["d2"]) - gt_offset),
        "n_gt_windows": len(wins),
        "gt_dur_s": float(gt_offset - gt_onset),
        "fy_thresh_n": float(fy_thresh_n),
        "qc_warning": qc.get("warning", ""),
    }

    for axis, est_l, est_r, meas_l, meas_r in (
        ("fx", ehf["fx_l"], ehf["fx_r"], meas["fx_l"], meas["fx_r"]),
        ("fy", ehf["fy_l"], ehf["fy_r"], meas["fy_l"], meas["fy_r"]),
        ("fz", ehf["fz_l"], ehf["fz_r"], meas["fz_l"], meas["fz_r"]),
    ):
        row.update(_axis_pair_metrics(est_l, meas_l, contact_mask, f"{axis}_l"))
        row.update(_axis_pair_metrics(est_r, meas_r, contact_mask, f"{axis}_r"))
        row.update(
            _axis_pair_metrics(
                est_l + est_r,
                meas_l + meas_r,
                contact_mask,
                f"{axis}_sum",
            )
        )

    # Sign sanity: contact-window mean fy should be negative for both.
    row["meas_fy_l_mean_contact"] = float(np.mean(meas["fy_l"][contact_mask]))
    row["meas_fy_r_mean_contact"] = float(np.mean(meas["fy_r"][contact_mask]))
    row["est_fy_l_mean_contact"] = float(np.mean(ehf["fy_l"][contact_mask]))
    row["est_fy_r_mean_contact"] = float(np.mean(ehf["fy_r"][contact_mask]))
    row["fy_sign_ok"] = bool(
        row["meas_fy_l_mean_contact"] < 0
        and row["meas_fy_r_mean_contact"] < 0
        and row["est_fy_l_mean_contact"] < 0
        and row["est_fy_r_mean_contact"] < 0
    )
    # Correlation sign check (same direction).
    for key in ("corr_fy_l", "corr_fy_r", "corr_fy_sum"):
        v = row.get(key)
        row[f"{key}_positive"] = bool(isinstance(v, float) and v == v and v > 0.0)

    return row


def _is_error_log_seg(namecode: str, condition: str, seg: str) -> bool:
    """True if segment is listed in SUB_Info error_log (pipeline skips these)."""
    try:
        cp = _path.ResultPaths(namecode).for_condition(condition)
    except Exception:
        return False
    err = {str(x).strip() for x in (cp.error_log or []) if str(x).strip()}
    return str(seg).strip() in err


def _drop_error_log_validation_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop validation rows for error_log segments (no FALSE placeholders)."""
    if df is None or df.empty:
        return df
    need = {"namecode", "condition", "seg"}
    if not need.issubset(df.columns):
        return df
    mask = [
        not _is_error_log_seg(str(nc), str(cond), str(seg))
        for nc, cond, seg in zip(df["namecode"], df["condition"], df["seg"])
    ]
    return df.loc[mask].reset_index(drop=True)


def _default_all_summary_path(analysis: Path, fy_thresh_n: float) -> Path:
    """``realdata_all_summary_fy5.csv`` — thresh in name so runs do not clobber."""
    tag = f"{fy_thresh_n:g}".replace(".", "p")
    return analysis / f"realdata_all_summary_fy{tag}.csv"


def validate_all_modern(
    *,
    solver: str = cfg.DEFAULT_SOLVER,
    namecodes: Optional[Iterable[str]] = None,
    protocols: Optional[Iterable[str]] = None,
    conditions: Optional[Iterable[str]] = None,
    segments: Optional[Iterable[str]] = None,
    fy_thresh_n: float = DEFAULT_FY_THRESH_N,
    min_contact_dur_s: float = DEFAULT_MIN_CONTACT_DUR_S,
    continue_on_error: bool = True,
    dry_run: bool = False,
    out_dir: Optional[Path] = None,
    out_csv: Optional[Path] = None,
) -> dict:
    """Batch MeasuredEHF validation over SUB_Info modern tree."""
    jobs = iter_modern_jobs(
        namecodes=namecodes,
        protocols=protocols,
        conditions=conditions,
        segments=segments,
    )
    analysis = Path(out_dir) if out_dir else Path(_path.ANALYSIS_DIR) / "Asymmetric" / "RiCTO" / "_validation"
    analysis.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    ok, fail = 0, 0
    print(
        f"[all] {len(jobs)} jobs | solver={solver} "
        f"fy_thresh={fy_thresh_n}N min_dur={min_contact_dur_s}s"
    )
    for namecode, cond, seg, mass in jobs:
        tag = f"{namecode} {cond} {seg} ({mass:g}kg)"
        if dry_run:
            print(f"[dry-run] {tag}")
            ok += 1
            continue
        try:
            row = validate_modern_segment(
                namecode=namecode,
                condition=cond,
                seg=seg,
                box_mass_kg=mass,
                solver=solver,
                fy_thresh_n=fy_thresh_n,
                min_contact_dur_s=min_contact_dur_s,
            )
            rows.append(row)
            print(
                f"[ok] {tag} | corr_fy_sum={row['corr_fy_sum']:.3f} "
                f"rmse_fy_sum={row['rmse_fy_sum']:.2f} "
                f"err_on={row['err_onset_s']:+.3f}s "
                f"err_off={row['err_offset_s']:+.3f}s"
            )
            ok += 1
        except Exception as e:
            # error_log segs are excluded from jobs; never persist FALSE rows for them
            if _is_error_log_seg(namecode, cond, seg):
                print(f"[skip] {tag}: error_log ({e})")
                continue
            fail += 1
            rows.append(
                {
                    "ok": False,
                    "namecode": namecode,
                    "condition": cond,
                    "seg": seg,
                    "box_mass_kg": float(mass),
                    "error": str(e),
                }
            )
            print(f"[fail] {tag}: {e}")
            if not continue_on_error:
                traceback.print_exc()
                raise

    summary = {"n_jobs": len(jobs), "ok": ok, "fail": fail, "summary_csv": None}
    if not dry_run:
        batch_df = _drop_error_log_validation_rows(pd.DataFrame(rows))
        out = Path(out_csv) if out_csv else _default_all_summary_path(analysis, fy_thresh_n)
        out.parent.mkdir(parents=True, exist_ok=True)
        # Merge into existing all-subjects table when filtering a subset
        if out.is_file() and not batch_df.empty and "namecode" in batch_df.columns:
            prev = _drop_error_log_validation_rows(pd.read_csv(out))
            drop_nc = set(batch_df["namecode"].astype(str).unique())
            if "namecode" in prev.columns:
                prev = prev[~prev["namecode"].astype(str).isin(drop_nc)]
            df = pd.concat([prev, batch_df], ignore_index=True)
        elif out.is_file() and batch_df.empty:
            df = _drop_error_log_validation_rows(pd.read_csv(out))
        else:
            df = batch_df
        df = _drop_error_log_validation_rows(df)
        save_csv(out, df)
        # Also write subject-scoped copies for convenience
        if not batch_df.empty and "namecode" in batch_df.columns:
            for nc, g in batch_df.groupby("namecode"):
                sub_out = analysis / f"realdata_{nc}_fy{fy_thresh_n:g}.csv"
                save_csv(sub_out, _drop_error_log_validation_rows(g))
                print(f"[all] wrote {sub_out}")
        summary["summary_csv"] = str(out)
        if ok and "corr_fy_sum" in df.columns:
            good = df.loc[df["ok"].eq(True)]
            # stats only for this batch's namecodes when possible
            batch_nc = set(batch_df["namecode"].astype(str)) if not batch_df.empty else set()
            if batch_nc and "namecode" in good.columns:
                good = good[good["namecode"].astype(str).isin(batch_nc)]
            if len(good):
                print(
                    f"[all] corr_fy_sum median={good['corr_fy_sum'].median():.3f} "
                    f"|err_onset| median={good['err_onset_s'].abs().median():.3f}s "
                    f"|err_offset| median={good['err_offset_s'].abs().median():.3f}s"
                )
        print(f"[all] wrote {out}")
    print(f"[all] done {summary}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate RiCTO core policies / real-data batch")
    ap.add_argument("--dummy", action="store_true", help="Run sign-convention dummies")
    ap.add_argument("--solvers", action="store_true", help="Compare solvers on synthetic residual")
    ap.add_argument("--legacy-trial", type=int, default=None, help="Optional real-data trial index")
    ap.add_argument(
        "--all",
        action="store_true",
        help="Batch real-data validation over modern subjects/conditions/segments",
    )
    ap.add_argument("--namecode", default=None, help="Modern: SUB_Info namecode e.g. 260512_KCH")
    ap.add_argument(
        "--namecodes",
        default=None,
        help="Comma filter for --all (e.g. 260512_KCH,260519_SHY)",
    )
    ap.add_argument(
        "--protocols",
        default="Asymmetric",
        help="Comma filter for --all (default: Asymmetric; empty = all)",
    )
    ap.add_argument("--condition", default=None)
    ap.add_argument(
        "--conditions",
        default=None,
        help="Comma filter for --all (e.g. 7kg_10bpm,15kg_10bpm)",
    )
    ap.add_argument("--segments", default=None, help="Comma-separated e.g. 1AB,1BC")
    ap.add_argument(
        "--box-mass",
        type=float,
        default=None,
        help="Box mass kg (unit tests / single-run). For --all, parsed from condition name.",
    )
    ap.add_argument("--solver", default=cfg.DEFAULT_SOLVER, choices=list(cfg.SOLVERS))
    ap.add_argument(
        "--fy-thresh",
        type=float,
        default=DEFAULT_FY_THRESH_N,
        help="MeasuredEHF |Fy_L|+|Fy_R| contact threshold (N)",
    )
    ap.add_argument(
        "--min-contact-dur",
        type=float,
        default=DEFAULT_MIN_CONTACT_DUR_S,
        help="Minimum GT contact duration (s)",
    )
    ap.add_argument(
        "--stop-on-error",
        action="store_true",
        help="For --all: abort on first failure (default: continue)",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Summary CSV path for --all (default: _validation/realdata_all_summary_fy{thresh}.csv)",
    )
    ap.add_argument(
        "--plot",
        action="store_true",
        help="Plot MeasuredEHF vs preRiCTO vs postRiCTO hand forces (needs --namecode/--condition/--segments)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    box_mass = 7.0 if args.box_mass is None else float(args.box_mass)

    if args.plot:
        if not (args.namecode and args.condition and args.segments):
            raise SystemExit("--plot requires --namecode --condition --segments")
        from optimization.ricto_plot import plot_ehf_compare_many

        segs = [s.strip() for s in str(args.segments).split(",") if s.strip()]
        paths = plot_ehf_compare_many(
            namecode=args.namecode,
            condition=args.condition,
            segments=segs,
        )
        for p in paths:
            print("[plot]", p)
        return

    if args.all:
        proto = _csv_set(args.protocols)
        validate_all_modern(
            solver=args.solver,
            namecodes=_csv_set(args.namecodes) or (_csv_set(args.namecode) if args.namecode else None),
            protocols=proto,
            conditions=_csv_set(args.conditions) or (_csv_set(args.condition) if args.condition else None),
            segments=_csv_set(args.segments),
            fy_thresh_n=args.fy_thresh,
            min_contact_dur_s=args.min_contact_dur,
            continue_on_error=not args.stop_on_error,
            dry_run=args.dry_run,
            out_csv=Path(args.out) if args.out else None,
        )
        return

    # Single modern segment without --all
    if args.namecode and args.condition and args.segments:
        segs = [s.strip() for s in str(args.segments).split(",") if s.strip()]
        mass = box_mass_from_condition(args.condition, default=box_mass)
        rows = []
        for seg in segs:
            row = validate_modern_segment(
                namecode=args.namecode,
                condition=args.condition,
                seg=seg,
                box_mass_kg=mass if args.box_mass is None else box_mass,
                solver=args.solver,
                fy_thresh_n=args.fy_thresh,
                min_contact_dur_s=args.min_contact_dur,
            )
            rows.append(row)
            print("[modern]", {k: row[k] for k in (
                "namecode", "condition", "seg", "corr_fy_sum", "rmse_fy_sum",
                "err_onset_s", "err_offset_s", "fy_sign_ok",
            )})
        analysis = Path(_path.ANALYSIS_DIR) / "Asymmetric" / "RiCTO" / "_validation"
        analysis.mkdir(parents=True, exist_ok=True)
        out = analysis / f"realdata_{args.namecode}_{args.condition}.csv"
        save_csv(out, pd.DataFrame(rows))
        print("[modern] wrote", out)
        return

    if not args.dummy and not args.solvers and args.legacy_trial is None:
        args.dummy = True
        args.solvers = True

    analysis = Path(_path.ANALYSIS_DIR) / "Asymmetric" / "RiCTO" / "_validation"
    analysis.mkdir(parents=True, exist_ok=True)

    if args.dummy:
        res = test_sign_dummies(box_mass)
        print("[sign-dummy]", res)
        if not res["pass"]:
            raise SystemExit("Sign dummy FAILED")
        print("[sign-dummy] PASS")

    if args.solvers:
        df = test_solvers_synthetic(box_mass)
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
        info = try_legacy_trial(args.legacy_trial, box_mass_kg=box_mass)
        print("[legacy]", info)


if __name__ == "__main__":
    main()
