#!/usr/bin/env python3
"""Run RiCTO for one or more segments / legacy OneCycle trials.

Examples
--------
# Synthetic dry-run (no OpenSim files required)
python run_ricto.py --synthetic --box-mass 7 --modes pre,post

# Legacy OneCycle (requires OpenSim data on disk)
python run_ricto.py --legacy --task 1 --box-mass 15 --solver least_squares

# Modern tree (OpenSim_Process) — one subject / condition
python run_ricto.py --namecode 260512_KCH --condition 7kg_10bpm \\
    --segments 1AB,1BC --box-mass 7

# All Asymmetric subjects / conditions / segments (Anaconda window)
python run_ricto.py --all --modes pre,post --solver least_squares
"""

from __future__ import annotations

import argparse
import os
import re
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

import PATH_RULE as _path  # noqa: E402
from optimization import ricto_config as cfg  # noqa: E402
from optimization.ricto_ehf import ehf_from_bk_pos, estimate_ehf_from_acc  # noqa: E402
from optimization.ricto_extload import (  # noqa: E402
    assert_no_measured_leak,
    write_ricto_mot,
)
from optimization.ricto_io import (  # noqa: E402
    extract_residual,
    mot_df_to_ext_dict,
    read_opensim_storage,
    save_csv,
    write_extload_mot,
)
from optimization.ricto_optimize import (  # noqa: E402
    baseline_theory,
    optimize_ricto,
    smooth_weight_curve,
)


def _parse_modes(raw: str) -> list[str]:
    modes = []
    for tok in raw.split(","):
        t = tok.strip().lower()
        if t in ("pre", "prericto", "original"):
            modes.append(cfg.MODE_PRE)
        elif t in ("post", "postricto", "corrected"):
            modes.append(cfg.MODE_POST)
        elif t:
            raise ValueError(f"Unknown mode {tok!r}")
    return modes or [cfg.MODE_PRE, cfg.MODE_POST]


def _make_heavyhand_template(n: int = 6000, dt: float = 0.001, grf_y: float = 350.0) -> pd.DataFrame:
    """Minimal HeavyHand-like MOT (GRF only; hands zero)."""
    t = np.arange(n) * dt
    z = np.zeros(n)
    data = {"time": t}
    for plate in (1, 2):
        data[f"ground_force{plate}_vx"] = z.copy()
        data[f"ground_force{plate}_vy"] = np.full(n, grf_y / 2)
        data[f"ground_force{plate}_vz"] = z.copy()
        for ax in ("x", "y", "z"):
            data[f"ground_force{plate}_p{ax}"] = z.copy()
            data[f"ground_torque{plate}_{ax}"] = z.copy()
        data[f"ground_force{plate}_py"] = z.copy()
    for plate in (3, 4):
        for ax in ("x", "y", "z"):
            data[f"hand_force{plate}_v{ax}"] = z.copy()
            data[f"hand_force{plate}_p{ax}"] = z.copy()
            data[f"hand_torque{plate}_{ax}"] = z.copy()
    return pd.DataFrame(data)


def run_synthetic(box_mass_kg: float, modes: list[str], solver: str) -> dict:
    """In-memory synthetic smoke test (no Analysis/_synthetic write).

    Writes only ``_validation/solver_compare_synthetic.csv`` via validate_ricto
    when that CLI is used. This helper returns dict results for console QC.
    """
    T, dt = 6.0, 0.01
    t = np.arange(0.0, T + 1e-12, dt)
    B = baseline_theory(box_mass_kg)
    truth = (1.6, 0.25, 4.1, 0.30)
    w = smooth_weight_curve(t, *truth)
    rng = np.random.default_rng(1)
    residual = B * (1.0 - w) + rng.normal(0, 1.0, size=t.shape)

    pos_r = np.zeros((len(t), 3))
    pos_l = np.zeros((len(t), 3))
    pos_r[:, 1] = 0.9 + 0.05 * np.sin(2 * np.pi * t / T)
    pos_l[:, 1] = 0.9 + 0.05 * np.sin(2 * np.pi * t / T + 0.1)
    pos_r[:, 0] = 0.2
    pos_l[:, 0] = -0.2
    pos_df = pd.DataFrame(
        {
            "time": t,
            "hand_r_X": pos_r[:, 0],
            "hand_r_Y": pos_r[:, 1],
            "hand_r_Z": pos_r[:, 2],
            "hand_l_X": pos_l[:, 0],
            "hand_l_Y": pos_l[:, 1],
            "hand_l_Z": pos_l[:, 2],
        }
    )

    ric = optimize_ricto(t, residual, box_mass_kg, solver=solver)
    ehf, hands, qc = ehf_from_bk_pos(pos_df, box_mass_kg)

    hh = _make_heavyhand_template(n=len(t), dt=float(np.median(np.diff(t))))
    hh["time"] = t
    meta = {
        "header_lines": [
            f"name synthetic_HeavyHand.mot\n",
            f"nRows={len(t)}\n",
            f"nColumns={hh.shape[1]}\n",
            "inDegrees=no\n",
            "endheader\n",
        ]
    }

    # Build MOT in memory / temp only for leak checks — do not keep _synthetic/
    import tempfile

    written = []
    with tempfile.TemporaryDirectory(prefix="ricto_syn_") as tmp:
        for mode in modes:
            mot_path = Path(tmp) / f"synthetic_ExtLoad_{mode}RiCTO.mot"
            write_ricto_mot(str(mot_path), hh, meta, ehf, hands, ric, mode=mode)
            written.append(str(mot_path))
        leak = assert_no_measured_leak(_mot_to_df(written[0]), None)

    return {
        "summary_csv": None,
        "timeseries_csv": None,
        "mots": [],
        "ric": {k: ric[k] for k in ("t1", "d1", "t2", "d2", "cost", "solver", "B")},
        "truth": {"t1": truth[0], "t2": truth[2]},
        "qc": qc,
        "leak_checks": leak,
        "note": "synthetic artifacts not written (use validate_ricto --solvers for CSV)",
    }


def _mot_to_df(path: str) -> pd.DataFrame:
    df, _ = read_opensim_storage(path)
    return df


def run_legacy_task(
    task_num: int,
    box_mass_kg: float,
    modes: list[str],
    solver: str,
    sub: str = "SUB1",
    trial_folder: str = "trial15_10_1",
    kg_bpm: str = "15_10",
    trial_num: int = 1,
) -> dict:
    from optimization.legacy_paths import legacy_extload_mot_path, legacy_onecycle_dirs

    dirs = legacy_onecycle_dirs(sub=sub, trial_folder=trial_folder)
    so1 = Path(dirs["so_postsim"]) / (
        f"{sub}_{kg_bpm}_{trial_num}_12sec_{task_num}_APP2_OneCycle_"
        f"StaticOptimization_force_1st_half.sto"
    )
    so2 = Path(dirs["so_postsim"]) / (
        f"{sub}_{kg_bpm}_{trial_num}_12sec_{task_num}_APP2_OneCycle_"
        f"StaticOptimization_force_2nd_half.sto"
    )
    # Prefer full BK pos if available; else half acc is discouraged — require pos
    pos_cands = list(Path(dirs["bk"]).glob(f"*{task_num}*pos_global*.sto"))
    hh_mot = Path(dirs["extload_dir"]) / (
        f"{kg_bpm}_trial{trial_num}_12sec_{task_num}_ExtLoadAPP2.mot"
    )
    # Some layouts only have APP1; HeavyHand may be named APP2 with zeros on hands
    if not hh_mot.is_file():
        alt = Path(dirs["extload_dir"]) / (
            f"{kg_bpm}_trial{trial_num}_12sec_{task_num}_ExtLoadAPP1.mot"
        )
        # If only APP1 exists we still refuse to use hand columns — zero them.
        if alt.is_file():
            hh_mot = alt
            use_app1_as_grf_only = True
        else:
            raise FileNotFoundError(f"Missing ExtLoad template under {dirs['extload_dir']}")
    else:
        use_app1_as_grf_only = False

    missing = [p for p in (so1, so2) if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing SO residual halves:\n  " + "\n  ".join(map(str, missing)))
    if not pos_cands:
        raise FileNotFoundError(f"No BK pos_global under {dirs['bk']}")

    def _opt_half(path: Path):
        df, _ = read_opensim_storage(path)
        t, r, tag = extract_residual(df, prefer="so")
        t = t - t[0]
        return optimize_ricto(t, r, box_mass_kg, solver=solver), tag

    ric1, tag1 = _opt_half(so1)
    ric2, tag2 = _opt_half(so2)
    # Concatenate weights on a 0..12 timeline for writing full MOT
    off = float(ric1["time"][-1] + 0.001)
    t_all = np.concatenate([ric1["time"], ric2["time"] + off])
    sw = np.concatenate([ric1["smooth_w"], ric2["smooth_w"]])
    rw = np.concatenate([ric1["rect_w"], ric2["rect_w"]])
    ric = {
        "time": t_all,
        "smooth_w": sw,
        "rect_w": rw,
        "params": np.stack([ric1["params"], ric2["params"]]),
        "t1": ric1["t1"],
        "d1": ric1["d1"],
        "t2": ric1["t2"],
        "d2": ric1["d2"],
        "B": ric1["B"],
        "B_theory": ric1["B_theory"],
        "cost": ric1["cost"] + ric2["cost"],
        "solver": solver,
        "success": ric1["success"] and ric2["success"],
        "nfev": ric1["nfev"] + ric2["nfev"],
        "residual_tag": f"{tag1}+{tag2}",
    }

    pos_df, _ = read_opensim_storage(pos_cands[0])
    ehf, hands, qc = ehf_from_bk_pos(pos_df, box_mass_kg)

    mot_df, mot_meta = read_opensim_storage(hh_mot)
    if use_app1_as_grf_only:
        # Strip measured hand forces/torques/COP — GRF only template
        for c in mot_df.columns:
            if c.startswith("hand_"):
                mot_df[c] = 0.0

    written = []
    for mode in modes:
        out_mot = legacy_extload_mot_path(
            kg_bpm=kg_bpm,
            trial_num=trial_num,
            task_num=task_num,
            mode=mode,
            sub=sub,
        )
        write_ricto_mot(out_mot, mot_df, mot_meta, ehf, hands, ric, mode=mode)
        written.append(out_mot)

    ana = Path(dirs["analysis"])
    summary = pd.DataFrame(
        [
            {
                "part": 1,
                **{k: ric1[k] for k in ("t1", "d1", "t2", "d2", "cost", "B", "B_theory", "success", "nfev")},
            },
            {
                "part": 2,
                **{k: ric2[k] for k in ("t1", "d1", "t2", "d2", "cost", "B", "B_theory", "success", "nfev")},
            },
        ]
    )
    sum_path = save_csv(ana / f"task{task_num}_summary.csv", summary)
    return {"mots": written, "summary_csv": sum_path, "qc": qc, "solver": solver}


def run_modern_segment(
    *,
    namecode: str,
    condition: str,
    seg: str,
    box_mass_kg: float,
    modes: list[str],
    solver: str,
) -> dict:
    """Modern OpenSim_Process tree via ``PATH_RULE.ResultPaths(namecode)``."""
    rp = _path.ResultPaths(namecode)
    cp = rp.for_condition(condition)

    id_path = cp.id_path(seg, "HeavyHand")
    so_path = cp.so_path(seg, "HeavyHand", "force")
    bk_path = cp.bk_path(seg, "pos_global")
    hh_path = cp.extload_path(seg, "HeavyHand")

    residual_path = id_path if os.path.isfile(id_path) else so_path
    prefer = "id" if residual_path == id_path else "so"
    for p in (residual_path, bk_path, hh_path):
        if not os.path.isfile(p):
            raise FileNotFoundError(p)

    rdf, _ = read_opensim_storage(residual_path)
    t, r, tag = extract_residual(rdf, prefer=prefer)
    ric = optimize_ricto(t, r, box_mass_kg, solver=solver)

    pos_df, _ = read_opensim_storage(bk_path)
    ehf, hands, qc = ehf_from_bk_pos(pos_df, box_mass_kg)

    hh_df, hh_meta = read_opensim_storage(hh_path)
    written = []
    for mode in modes:
        app = "preRiCTO" if mode == cfg.MODE_PRE else "postRiCTO"
        out = cp.extload_path(seg, app)
        write_ricto_mot(out, hh_df, hh_meta, ehf, hands, ric, mode=mode)
        written.append(out)

    ts = pd.DataFrame(
        {
            "time": ric["time"],
            "residual": ric["residual"],
            "w_smooth": ric["smooth_w"],
            "w_rect": ric["rect_w"],
        }
    )
    ts_path = save_csv(cp.ricto_timeseries_path(seg), ts)
    opt_row = {
        "seg": seg,
        "residual_source": tag,
        "solver": ric["solver"],
        "success": ric["success"],
        "cost": ric["cost"],
        "t1": ric["t1"],
        "d1": ric["d1"],
        "t2": ric["t2"],
        "d2": ric["d2"],
        "B": ric["B"],
        "nfev": ric["nfev"],
        "qc_warning": qc.get("warning", ""),
    }
    # Summary xlsx (no Results/ CSV). Import is local to avoid hard dep cycles.
    report_path = None
    try:
        _d_results = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "d_Results_Analysis",
        )
        if _d_results not in sys.path:
            sys.path.insert(0, _d_results)
        from run_ricto_report_sheets import upsert_optimize_row  # noqa: WPS433

        report_path = str(
            upsert_optimize_row(namecode, condition, opt_row)
        )
    except Exception as e:
        print(f"[warn] Summary xlsx upsert failed ({namecode} {condition} {seg}): {e}")

    return {
        "mots": written,
        "summary_xlsx": report_path,
        "timeseries_csv": ts_path,
        "qc": qc,
        "opt_row": opt_row,
    }


def box_mass_from_condition(condition: str, default: float = 7.0) -> float:
    """Parse leading ``Nkg`` from condition names like ``15kg_10bpm`` / ``7kg_10bpm_trial1``."""
    m = re.match(r"(\d+)\s*kg", condition, flags=re.IGNORECASE)
    return float(m.group(1)) if m else float(default)


def _csv_set(raw: Optional[str]) -> Optional[set[str]]:
    if raw is None or not str(raw).strip():
        return None
    return {x.strip() for x in str(raw).split(",") if x.strip()}


def iter_modern_jobs(
    *,
    namecodes: Optional[Iterable[str]] = None,
    protocols: Optional[Iterable[str]] = None,
    conditions: Optional[Iterable[str]] = None,
    segments: Optional[Iterable[str]] = None,
) -> list[tuple[str, str, str, float]]:
    """Enumerate ``(namecode, condition, seg, box_mass_kg)`` from ``SUB_Info``.

    Segments listed in ``error_log`` are omitted (no OpenSim outputs expected).
    """
    import SUB_Info as si

    want_nc = set(namecodes) if namecodes is not None else None
    want_proto = set(protocols) if protocols is not None else None
    want_cond = set(conditions) if conditions is not None else None
    want_seg = set(segments) if segments is not None else None

    jobs: list[tuple[str, str, str, float]] = []
    for namecode, meta in si.subjects.items():
        if want_nc is not None and namecode not in want_nc:
            continue
        protocol = meta.get("protocol")
        if want_proto is not None and protocol not in want_proto:
            continue
        rp = _path.ResultPaths(namecode)
        for cond in rp.conditions:
            if want_cond is not None and cond not in want_cond:
                continue
            mass = box_mass_from_condition(cond)
            cp = rp.for_condition(cond)
            err = {str(x).strip() for x in (cp.error_log or []) if str(x).strip()}
            for segs in cp.section_segments().values():
                for seg in segs:
                    if seg in err:
                        continue
                    if want_seg is not None and seg not in want_seg:
                        continue
                    jobs.append((namecode, cond, seg, mass))
    return jobs


def run_all_modern(
    *,
    modes: list[str],
    solver: str,
    namecodes: Optional[Iterable[str]] = None,
    protocols: Optional[Iterable[str]] = None,
    conditions: Optional[Iterable[str]] = None,
    segments: Optional[Iterable[str]] = None,
    continue_on_error: bool = True,
    dry_run: bool = False,
) -> dict:
    """Batch RiCTO over subjects / conditions / segments."""
    jobs = iter_modern_jobs(
        namecodes=namecodes,
        protocols=protocols,
        conditions=conditions,
        segments=segments,
    )
    ok, fail = 0, 0
    touched_namecodes: set[str] = set()
    print(f"[all] {len(jobs)} jobs | modes={modes} solver={solver}")
    for namecode, cond, seg, mass in jobs:
        tag = f"{namecode} {cond} {seg} ({mass:g}kg)"
        if dry_run:
            print(f"[dry-run] {tag}")
            ok += 1
            continue
        try:
            res = run_modern_segment(
                namecode=namecode,
                condition=cond,
                seg=seg,
                box_mass_kg=mass,
                modes=modes,
                solver=solver,
            )
            print(f"[ok] {tag} -> {res['mots']}")
            touched_namecodes.add(namecode)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[fail] {tag}: {e}")
            if not continue_on_error:
                traceback.print_exc()
                raise
    # Final Summary refresh (GT timing merge) per subject
    if touched_namecodes and not dry_run:
        _d_results = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "d_Results_Analysis",
        )
        if _d_results not in sys.path:
            sys.path.insert(0, _d_results)
        try:
            from run_ricto_report_sheets import build_subject_report

            for nc in sorted(touched_namecodes):
                try:
                    build_subject_report(nc)
                except Exception as e:
                    print(f"[warn] report rebuild {nc}: {e}")
        except Exception as e:
            print(f"[warn] report module import failed: {e}")
    summary = {"n_jobs": len(jobs), "ok": ok, "fail": fail}
    print(f"[all] done {summary}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate preRiCTO / postRiCTO ExtLoad MOT")
    ap.add_argument("--synthetic", action="store_true", help="Run fully synthetic demo")
    ap.add_argument("--legacy", action="store_true", help="Legacy OneCycle half-split mode")
    ap.add_argument(
        "--all",
        action="store_true",
        help="Batch all modern subjects/conditions/segments from SUB_Info",
    )
    ap.add_argument("--task", type=int, default=1)
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
        help="Box mass kg (single-run). For --all, mass is parsed from condition name.",
    )
    ap.add_argument("--modes", default="pre,post")
    ap.add_argument("--solver", default=cfg.DEFAULT_SOLVER, choices=list(cfg.SOLVERS))
    ap.add_argument(
        "--stop-on-error",
        action="store_true",
        help="For --all: abort on first failure (default: continue)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    modes = _parse_modes(args.modes)
    box_mass = 7.0 if args.box_mass is None else float(args.box_mass)

    if args.dry_run and not args.all:
        print("[dry-run] modes=", modes, "solver=", args.solver)
        print("[dry-run] ANALYSIS_DIR=", _path.ANALYSIS_DIR)
        print("[dry-run] OPENSIM_DIR=", _path.OPENSIM_DIR)
        return

    if args.all:
        proto = _csv_set(args.protocols)
        run_all_modern(
            modes=modes,
            solver=args.solver,
            namecodes=_csv_set(args.namecodes) or (_csv_set(args.namecode) if args.namecode else None),
            protocols=proto,
            conditions=_csv_set(args.conditions) or (_csv_set(args.condition) if args.condition else None),
            segments=_csv_set(args.segments),
            continue_on_error=not args.stop_on_error,
            dry_run=args.dry_run,
        )
        return

    if args.synthetic or (
        not args.legacy and not (args.namecode and args.condition and args.segments)
    ):
        # default to synthetic when no data args given
        if not args.legacy and not (args.namecode and args.condition and args.segments):
            print("[run_ricto] no data args → synthetic demo")
        res = run_synthetic(box_mass, modes, args.solver)
        print("[synthetic]", res)
        return

    if args.legacy:
        res = run_legacy_task(args.task, box_mass, modes, args.solver)
        print("[legacy]", res)
        return

    mass = (
        args.box_mass
        if args.box_mass is not None
        else box_mass_from_condition(args.condition, default=7.0)
    )
    segs = [s.strip() for s in args.segments.split(",") if s.strip()]
    for seg in segs:
        res = run_modern_segment(
            namecode=args.namecode,
            condition=args.condition,
            seg=seg,
            box_mass_kg=mass,
            modes=modes,
            solver=args.solver,
        )
        print(f"[modern {seg}]", res)


if __name__ == "__main__":
    main()
