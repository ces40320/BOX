# -*- coding: utf-8 -*-
"""Build rectangular HeavyHand EHF estimates from BK (+ optional marker events)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RUN_TOOLS = _CODES / "c_Run_Tools"
for _p in (str(_CODES), str(_RUN_TOOLS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from optimization.ricto_ehf import ehf_from_bk_pos  # noqa: E402
from optimization.ricto_io import read_opensim_storage  # noqa: E402
from optimization.run_ricto import box_mass_from_condition  # noqa: E402
import PATH_RULE as _path  # noqa: E402
import SUB_Info as _sub_info  # noqa: E402

from abc_marker_events import detect_abc_events_from_rigidbody  # noqa: E402
from analysis_utils import list_segments, parse_condition  # noqa: E402

# Cache Motive event tables: (namecode, cond) → DataFrame | None
_EVENTS_CACHE: Dict[tuple, Optional[pd.DataFrame]] = {}


def _rect_weight(time_s: np.ndarray, t_on: float, t_off: float) -> np.ndarray:
    t = np.asarray(time_s, dtype=float)
    w = np.zeros_like(t)
    w[(t >= t_on) & (t <= t_off)] = 1.0
    return w


def _find_rigidbody_csv(namecode: str, cond: str) -> Optional[Path]:
    rp = _path.ResultPaths(namecode)
    rigid_dir = Path(rp.rigid_dir)
    if not rigid_dir.is_dir():
        return None
    mass, tempo = parse_condition(cond)
    keys = (cond, f"{int(mass)}kg", f"{tempo}bpm", f"{int(mass)}_{tempo}")
    cands = sorted(rigid_dir.glob("*.csv"))
    for key in keys:
        for p in cands:
            if key.lower() in p.name.lower():
                return p
    return cands[0] if cands else None


def _events_for_condition(
    namecode: str,
    cond: str,
    *,
    skip_first_n_cycles: int = 1,
) -> Optional[pd.DataFrame]:
    key = (namecode, cond, skip_first_n_cycles)
    if key in _EVENTS_CACHE:
        return _EVENTS_CACHE[key]
    csv_path = _find_rigidbody_csv(namecode, cond)
    if csv_path is None:
        _EVENTS_CACHE[key] = None
        return None
    info = _sub_info.subjects[namecode]
    n_cycles = int(info["conditions"][cond]["cycles"])
    try:
        events, _rigid, _pairs = detect_abc_events_from_rigidbody(
            str(csv_path),
            skip_first_n_cycles=skip_first_n_cycles,
            n_cycles=n_cycles,
        )
    except Exception:
        _EVENTS_CACHE[key] = None
        return None
    _EVENTS_CACHE[key] = events
    return events


def marker_window_for_seg(
    namecode: str,
    cond: str,
    seg: str,
    *,
    skip_first_n_cycles: int = 1,
) -> Optional[Tuple[float, float]]:
    events = _events_for_condition(
        namecode, cond, skip_first_n_cycles=skip_first_n_cycles
    )
    if events is None or events.empty:
        return None
    hit = events[events["seg_label"] == seg]
    if hit.empty:
        return None
    row = hit.iloc[0]
    return float(row["grip_time"]), float(row["deposit_time"])


def heavyhand_ehf_for_segment(
    namecode: str,
    cond: str,
    seg: str,
    *,
    use_markers: bool = True,
) -> Dict[str, np.ndarray]:
    rp = _path.ResultPaths(namecode)
    cp = rp.for_condition(cond)
    bk_path = cp.bk_path(seg, "pos_global")
    if not os.path.isfile(bk_path):
        raise FileNotFoundError(bk_path)
    pos_df, _ = read_opensim_storage(bk_path)
    mass = box_mass_from_condition(cond)
    ehf, _hands, _qc = ehf_from_bk_pos(pos_df, mass)
    t = np.asarray(ehf["time"], dtype=float)

    win = marker_window_for_seg(namecode, cond, seg) if use_markers else None
    if win is not None:
        t0, t1 = float(t[0]), float(t[-1])
        g, d = win
        if (g >= t0 - 0.5) and (d <= t1 + 0.5) and (d > g):
            w = _rect_weight(t, g, d)
        else:
            w = np.ones_like(t)
    else:
        w = np.ones_like(t)

    return {
        "time": t,
        "hand_force3_vx": w * ehf["fx_l"],
        "hand_force3_vy": w * ehf["fy_l"],
        "hand_force3_vz": w * ehf["fz_l"],
        "hand_force4_vx": w * ehf["fx_r"],
        "hand_force4_vy": w * ehf["fy_r"],
        "hand_force4_vz": w * ehf["fz_r"],
        "rect_w": w,
    }


def heavyhand_dataframe(namecode: str, cond: str, seg: str, **kwargs) -> pd.DataFrame:
    pack = heavyhand_ehf_for_segment(namecode, cond, seg, **kwargs)
    cols = [
        "time",
        "hand_force3_vx",
        "hand_force3_vy",
        "hand_force3_vz",
        "hand_force4_vx",
        "hand_force4_vy",
        "hand_force4_vz",
        "rect_w",
    ]
    return pd.DataFrame({c: pack[c] for c in cols})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--condition", default=None)
    ap.add_argument("--segments", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    rp = _path.ResultPaths(args.namecode)
    conds = [args.condition] if args.condition else list(rp.conditions.keys())
    out_root = Path(args.out_dir) if args.out_dir else (
        Path(_path.ANALYSIS_DIR) / "Asymmetric" / "EHF" / "HeavyHand" / "_export"
    )
    out_root.mkdir(parents=True, exist_ok=True)

    for cond in conds:
        segs = (
            [s.strip() for s in args.segments.split(",") if s.strip()]
            if args.segments
            else list_segments(args.namecode, cond)
        )
        for seg in segs:
            try:
                df = heavyhand_dataframe(args.namecode, cond, seg)
            except Exception as e:
                print(f"[skip] {cond} {seg}: {e}")
                continue
            path = out_root / f"{rp.sub_label}_{cond}_{seg}_HeavyHand_EHF.csv"
            df.to_csv(path, index=False)
            print("[ok]", path)


if __name__ == "__main__":
    main()
