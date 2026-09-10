# -*- coding: utf-8 -*-
"""Condition-A EHF export: marker-gated estimated hand force (HeavyHand pathway).

Pipeline (``d_Results_Analysis`` only — not ``a_Get_Exp_Data``)
--------------------------------------------------------------
1. Detect ABC grip/deposit events from rigid-body ``Marker1`` / ``Marker5``
   (6 events per cycle).
2. Estimate continuous EHF from wrist-marker acceleration
   ``fy = -(m_box/2) * (a_y - g)`` (same form as RiCTO raw / HeavyHand estimate;
   no hand load-cell).
3. Apply a **rectangular** contact window from the marker events (condition A).
4. Save under ``{COWORK}/Analysis/Asymmetric/EHF/HeavyHand/``.

Outputs per subject/condition
-----------------------------
::

    Analysis/Asymmetric/EHF/HeavyHand/SUB{n}/{cond}/
      box_events_ABC.csv
      EHF_raw_full.csv              # ungated estimate
      EHF_markerRect_full.csv       # rect_w × raw (condition A)
      segments/{k}{AB|BC|CA}.csv    # cropped [grip, deposit], t0-normalized

Usage
-----
::

    python export_ehf_marker_rect_heavyhand.py 260512_KCH
    python export_ehf_marker_rect_heavyhand.py 260512_KCH --condition 7kg_10bpm
    python export_ehf_marker_rect_heavyhand.py --dry-run
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.ndimage import median_filter

_HERE = os.path.dirname(os.path.abspath(__file__))
_CODES = os.path.dirname(_HERE)
_A_GET = os.path.join(_CODES, "a_Get_Exp_Data")
sys.path.insert(0, _CODES)
sys.path.insert(0, _A_GET)

import PATH_RULE as _path  # noqa: E402
import SUB_Info as _sub  # noqa: E402
import config_exp_settings as _lcfg  # noqa: E402
import lifting_io as _io  # noqa: E402

from abc_marker_events import detect_abc_events_from_rigidbody  # noqa: E402

GRAVITY_Y = -9.80660
LEFT_WRIST = "LWRA"
RIGHT_WRIST = "RWRA"
ANALYSIS_EHF_ROOT = os.path.join(
    _path.COWORK_ROOT_DIR, "Analysis", "Asymmetric", "EHF", "HeavyHand"
)


def _box_kg_from_cond(cond: str) -> float:
    prefix = cond.split("_", 1)[0]
    if not (prefix.endswith("kg") and prefix[:-2].replace(".", "", 1).isdigit()):
        raise ValueError(f"Cannot parse box kg from condition {cond!r}")
    return float(prefix[:-2])


def _find_rigidbody_csv(rigid_dir: str, cond: str) -> str:
    patterns = [
        os.path.join(rigid_dir, f"{cond}_rigidbody.csv"),
        os.path.join(rigid_dir, f"{cond}.csv"),
        os.path.join(rigid_dir, f"*{cond}*rigidbody*.csv"),
        os.path.join(rigid_dir, f"*{cond}*.csv"),
    ]
    hits: List[str] = []
    for pat in patterns:
        hits.extend(glob.glob(pat))
    hits = [h for h in hits if h.lower().endswith(".csv")]
    # Prefer names containing 'rigidbody'
    hits = sorted(set(hits), key=lambda p: (0 if "rigidbody" in os.path.basename(p).lower() else 1, p))
    if not hits:
        raise FileNotFoundError(f"No rigid-body CSV for {cond!r} under {rigid_dir}")
    return hits[0]


def _find_c3d(c3d_dir: str, cond: str) -> str:
    hits = sorted(glob.glob(os.path.join(c3d_dir, f"*{cond}*.c3d")))
    if not hits:
        # some subjects use subN_7_10 style stems — fall back to any c3d listing
        hits = sorted(glob.glob(os.path.join(c3d_dir, "*.c3d")))
        hits = [h for h in hits if cond.replace("kg_", "_").replace("bpm", "") in os.path.basename(h)
                or cond in os.path.basename(h)]
    if not hits:
        raise FileNotFoundError(f"No C3D for {cond!r} under {c3d_dir}")
    return hits[0]


def _marker_xyz(markers: Dict[str, np.ndarray], label: str) -> np.ndarray:
    if label not in markers:
        avail = [k for k in markers.keys() if k != "time"]
        raise KeyError(f"Marker {label!r} not in C3D. Available: {avail[:20]}...")
    return np.asarray(markers[label], dtype=float)


def _despike_acc(a: np.ndarray, thr: float = 30.0, size: int = 21) -> np.ndarray:
    mf = median_filter(a, size=(size, 1), mode="nearest")
    out = a.copy()
    m = np.abs(a) > thr
    out[m] = mf[m]
    return out


def estimate_ehf_from_wrist_markers(
    markers: Dict[str, np.ndarray],
    box_mass_kg: float,
    *,
    filter_hz: float = 10.0,
    gravity_y: float = GRAVITY_Y,
) -> Dict[str, np.ndarray]:
    """HeavyHand-style EHF estimate from wrist marker acceleration (no load-cell).

    ``markers`` is the dict returned by ``lifting_io.read_c3d_markers``.
    """
    time = np.asarray(markers["time"], dtype=float)
    if len(time) < 3:
        raise ValueError("Marker trajectory too short for acceleration EHF")
    rate = float(1.0 / np.median(np.diff(time)))
    left = _marker_xyz(markers, LEFT_WRIST).copy()
    right = _marker_xyz(markers, RIGHT_WRIST).copy()

    # fill NaNs along time
    for arr in (left, right):
        for c in range(3):
            col = arr[:, c]
            bad = ~np.isfinite(col)
            if bad.any() and (~bad).any():
                col[bad] = np.interp(time[bad], time[~bad], col[~bad])
                arr[:, c] = col

    left_f = _io.butterworth_filter(left, rate, filter_hz, _lcfg.FILTER_ORDER)
    right_f = _io.butterworth_filter(right, rate, filter_hz, _lcfg.FILTER_ORDER)

    dt = 1.0 / rate
    acc_l = np.gradient(np.gradient(left_f, dt, axis=0), dt, axis=0)
    acc_r = np.gradient(np.gradient(right_f, dt, axis=0), dt, axis=0)
    acc_l = _despike_acc(acc_l)
    acc_r = _despike_acc(acc_r)

    m = box_mass_kg / 2.0
    # same sign convention as ricto_core.compute_pre_ricto_ehf
    fx_r = -(m * acc_r[:, 0])
    fx_l = -(-m * acc_l[:, 0])
    fy_r = -(m * (acc_r[:, 1] - gravity_y))
    fy_l = -(m * (acc_l[:, 1] - gravity_y))
    fz_r = -(-m * acc_r[:, 2])
    fz_l = -(-m * acc_l[:, 2])
    return {
        "time": time,
        "fx_l": fx_l, "fy_l": fy_l, "fz_l": fz_l,
        "fx_r": fx_r, "fy_r": fy_r, "fz_r": fz_r,
    }


def rectangle_weight_from_events(
    time: np.ndarray,
    events: pd.DataFrame,
) -> np.ndarray:
    """rect_w = 1 on each [grip, deposit] interval (marker events), else 0."""
    w = np.zeros(len(time), dtype=float)
    for _, row in events.iterrows():
        t0 = float(row["grip_time"])
        t1 = float(row["deposit_time"])
        if t1 < t0:
            t0, t1 = t1, t0
        w[(time >= t0) & (time <= t1)] = 1.0
    return w


def _ehf_to_df(ehf: Dict[str, np.ndarray], rect_w: Optional[np.ndarray] = None) -> pd.DataFrame:
    out = {
        "time": ehf["time"],
        "fx_l": ehf["fx_l"], "fy_l": ehf["fy_l"], "fz_l": ehf["fz_l"],
        "fx_r": ehf["fx_r"], "fy_r": ehf["fy_r"], "fz_r": ehf["fz_r"],
    }
    if rect_w is not None:
        out["rect_w"] = rect_w
        for k in ("fx_l", "fy_l", "fz_l", "fx_r", "fy_r", "fz_r"):
            out[k] = out[k] * rect_w
    return pd.DataFrame(out)


def _crop_segments(
    gated: pd.DataFrame,
    events: pd.DataFrame,
    out_dir: str,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    t = gated["time"].to_numpy()
    for _, row in events.iterrows():
        t0 = float(row["grip_time"])
        t1 = float(row["deposit_time"])
        if t1 < t0:
            t0, t1 = t1, t0
        mask = (t >= t0) & (t <= t1)
        seg = gated.loc[mask].copy()
        if seg.empty:
            continue
        seg["time"] = seg["time"] - seg["time"].iloc[0]
        path = os.path.join(out_dir, f"{row['seg_label']}.csv")
        seg.to_csv(path, index=False)


def process_condition(
    namecode: str,
    cond: str,
    *,
    pair_threshold_m: float,
    min_peak_distance_sec: float,
    skip_first_n_cycles: int,
    dry_run: bool = False,
) -> Dict[str, str]:
    rp = _path.ResultPaths(namecode)
    if rp.protocol != "Asymmetric":
        raise ValueError(f"{namecode}: protocol={rp.protocol!r}, expected Asymmetric")

    info = _sub.subjects[namecode]
    n_cycles = int(info["conditions"][cond]["cycles"])
    # cycles in SUB_Info often include sync; event splitter skips first N already
    rigid_csv = _find_rigidbody_csv(rp.rigid_dir, cond)
    c3d_path = _find_c3d(rp.c3d_dir, cond)
    box_kg = _box_kg_from_cond(cond)

    out_dir = os.path.join(ANALYSIS_EHF_ROOT, rp.sub_label, cond)
    print(f"\n=== {namecode} / {rp.sub_label} / {cond} ===")
    print(f"  rigid : {rigid_csv}")
    print(f"  c3d   : {c3d_path}")
    print(f"  box   : {box_kg} kg")
    print(f"  out   : {out_dir}")

    # SUB_Info ``cycles`` = analysis cycles after practice/sync skip.
    events, _, pairs = detect_abc_events_from_rigidbody(
        rigid_csv,
        skiprows=_lcfg.RIGID_BODY_SKIPROWS,
        pair_threshold_m=pair_threshold_m,
        min_peak_distance_sec=min_peak_distance_sec,
        skip_first_n_cycles=skip_first_n_cycles,
        n_cycles=n_cycles,
    )
    print(
        f"  pairs_all={len(pairs)}  events_kept={len(events)}  "
        f"(cycles×3, skip_first={skip_first_n_cycles})"
    )
    if events.empty:
        raise RuntimeError(f"No ABC events detected for {namecode} {cond}")

    if dry_run:
        print(events.head(12).to_string(index=False))
        return {"out_dir": out_dir, "events": "(dry-run)"}

    markers = _io.read_c3d_markers(c3d_path, rotations=None)
    ehf = estimate_ehf_from_wrist_markers(markers, box_kg)
    # align event times onto marker time base if needed (same Motive clock expected)
    rect_w = rectangle_weight_from_events(ehf["time"], events)

    os.makedirs(out_dir, exist_ok=True)
    events_path = os.path.join(out_dir, "box_events_ABC.csv")
    events.to_csv(events_path, index=False)

    raw_df = _ehf_to_df(ehf)
    raw_path = os.path.join(out_dir, "EHF_raw_full.csv")
    raw_df.to_csv(raw_path, index=False)

    gated_df = _ehf_to_df(ehf, rect_w=rect_w)
    gated_path = os.path.join(out_dir, "EHF_markerRect_full.csv")
    gated_df.to_csv(gated_path, index=False)

    seg_dir = os.path.join(out_dir, "segments")
    _crop_segments(gated_df, events, seg_dir)
    print(f"  wrote events → {events_path}")
    print(f"  wrote raw    → {raw_path}")
    print(f"  wrote gated  → {gated_path}")
    print(f"  wrote segs   → {seg_dir} ({len(events)} files)")
    return {
        "out_dir": out_dir,
        "events": events_path,
        "raw": raw_path,
        "gated": gated_path,
        "segments": seg_dir,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export marker-rect gated HeavyHand EHF (condition A)"
    )
    parser.add_argument(
        "namecodes",
        nargs="*",
        help="Subject namecodes (default: all Asymmetric subjects)",
    )
    parser.add_argument("--condition", default=None, help="Single condition key")
    parser.add_argument(
        "--pair-threshold",
        type=float,
        default=0.05,
        help="Min |ΔY| between adjacent peaks to form a pair (m). "
             "Symmetric legacy used 0.5; Asymmetric shelves need a smaller value.",
    )
    parser.add_argument(
        "--min-peak-distance",
        type=float,
        default=0.5,
        help="Minimum peak spacing (s)",
    )
    parser.add_argument(
        "--skip-first-n-cycles",
        type=int,
        default=1,
        help="Skip first N ABC cycles (sync / practice)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.namecodes:
        namecodes = args.namecodes
    else:
        namecodes = [
            nc for nc, info in _sub.subjects.items()
            if info.get("protocol") == "Asymmetric"
        ]

    n_ok = 0
    n_fail = 0
    for nc in namecodes:
        info = _sub.subjects[nc]
        if info.get("protocol") != "Asymmetric":
            print(f"[SKIP] {nc}: not Asymmetric")
            continue
        conds = [args.condition] if args.condition else list(info["conditions"].keys())
        for cond in conds:
            if cond not in info["conditions"]:
                print(f"[SKIP] {nc}: unknown condition {cond}")
                continue
            try:
                process_condition(
                    nc,
                    cond,
                    pair_threshold_m=args.pair_threshold,
                    min_peak_distance_sec=args.min_peak_distance,
                    skip_first_n_cycles=args.skip_first_n_cycles,
                    dry_run=args.dry_run,
                )
                n_ok += 1
            except Exception as e:
                n_fail += 1
                print(f"[FAIL] {nc} {cond}: {e}")
    print(f"\nDone. ok={n_ok} fail={n_fail}  root={ANALYSIS_EHF_ROOT}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
