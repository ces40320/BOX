# -*- coding: utf-8 -*-
"""Asymmetric ABC box-event detection from Motive rigid-body Marker1 / Marker5.

Port of the findpeaks pairing logic in
``MOT_TRC_UPDOWN_APP123_Modified.m`` / ``SplitLiftingPhase_from_c3d.py``,
adapted so that one cycle yields **6 events** (3 grip/deposit pairs → AB, BC, CA)
instead of the Symmetric Up/Down 4-event layout.

MATLAB reference pairs adjacent ``-Y`` peaks whose height differs by more than a
threshold. This port adds an optional **minimum grip→deposit duration** so a
near, height-qualified peak cannot be taken as deposit too soon after grip
(common false early-deposit on mid-height wiggles).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

# Motive layout after skiprows header:
# Frame, Time, RB(RotXYZ, PosXYZ, MeanErr)=7, then each marker (XYZ, Quality)=4
_RB_META_COLS = 7
_MARKER_STRIDE = 4
_MARKER1_INDEX = 0
_MARKER5_INDEX = 4

# Default: reject deposit candidates earlier than this after grip (seconds).
DEFAULT_MIN_PAIR_DURATION_S = 0.8
# Shelf-to-shelf vertical change (AB/CA) is ~0.5 m.
DEFAULT_PAIR_THRESHOLD_M = 0.25
# BC is mostly lateral (small ΔY). Still peak on -Y; gate pairs on |ΔX|.
BC_PAIR_X_THRESHOLD_M = 0.3
# If default thr under-detects, step down until segment count is met.
SHELF_PAIR_THRESHOLD_LADDER_M: Tuple[float, ...] = (
    0.25,
    0.20,
    0.15,
    0.12,
    0.10,
    0.08,
    0.06,
    0.05,
)
BC_PAIR_X_THRESHOLD_LADDER_M: Tuple[float, ...] = (
    0.30,
    0.25,
    0.20,
    0.15,
    0.12,
    0.10,
    0.08,
)


def read_rigidbody_marker15(
    csv_path: str,
    *,
    skiprows: int = 7,
) -> Dict[str, np.ndarray]:
    """Return time and Marker1/Marker5 XYZ (N×3) from a Motive rigid-body CSV."""
    df = pd.read_csv(csv_path, skiprows=skiprows, header=None)
    if df.shape[1] < 2 + _RB_META_COLS + _MARKER_STRIDE * 5:
        raise ValueError(
            f"Unexpected rigid-body columns in {csv_path!r}: got {df.shape[1]}"
        )
    time = df.iloc[:, 1].to_numpy(dtype=float)

    def _xyz(marker_index: int) -> np.ndarray:
        base = 2 + _RB_META_COLS + marker_index * _MARKER_STRIDE
        return df.iloc[:, [base, base + 1, base + 2]].to_numpy(dtype=float)

    m1 = _xyz(_MARKER1_INDEX)
    m5 = _xyz(_MARKER5_INDEX)
    box = 0.5 * (m1 + m5)
    return {
        "time": time,
        "marker1": m1,
        "marker5": m5,
        "box_xyz": box,
    }


def fill_rigidbody_gaps(
    box_xyz: np.ndarray,
    time: np.ndarray,
    *,
    max_gap_s: float = 0.5,
) -> np.ndarray:
    """Linear-fill NaN gaps shorter than ``max_gap_s`` (per axis)."""
    xyz = np.asarray(box_xyz, dtype=float).copy()
    t = np.asarray(time, dtype=float)
    n = xyz.shape[0]
    if n == 0:
        return xyz
    for ax in range(xyz.shape[1]):
        col = xyz[:, ax]
        finite = np.isfinite(col)
        if not np.any(finite):
            continue
        # Interpolate all interior NaNs from finite samples, then restore
        # long gaps as NaN so we do not invent long dropouts.
        idx = np.arange(n)
        filled = col.copy()
        filled[~finite] = np.interp(idx[~finite], idx[finite], col[finite])
        # Mask runs of missing longer than max_gap_s
        i = 0
        while i < n:
            if finite[i]:
                i += 1
                continue
            j = i
            while j < n and not finite[j]:
                j += 1
            gap_t = float(t[min(j, n - 1)] - t[i]) if j > i else 0.0
            if gap_t > float(max_gap_s):
                filled[i:j] = np.nan
            i = j
        xyz[:, ax] = filled
    return xyz


def rigidbody_track_quality(
    box_xyz: np.ndarray,
) -> Tuple[bool, str]:
    """True if box trajectory looks usable for peak pairing."""
    xyz = np.asarray(box_xyz, dtype=float)
    if xyz.size == 0:
        return False, "empty"
    finite = np.isfinite(xyz).all(axis=1)
    frac = float(np.mean(finite)) if len(finite) else 0.0
    if frac < 0.25:
        return False, f"finite_frac={frac:.3f}<0.25"
    y = xyz[finite, 1]
    x = xyz[finite, 0]
    yr = float(np.max(y) - np.min(y)) if y.size else 0.0
    xr = float(np.max(x) - np.min(x)) if x.size else 0.0
    if yr < 0.05 and xr < 0.05:
        return False, f"Y_range={yr:.4f}m X_range={xr:.4f}m (dead track)"
    return True, f"finite_frac={frac:.3f} Y_range={yr:.3f}m X_range={xr:.3f}m"


def detect_box_event_pairs(
    box_xyz: np.ndarray,
    *,
    time: Optional[np.ndarray] = None,
    axis_index: int = 1,
    pair_axis_index: Optional[int] = None,
    pair_threshold_m: float = 0.05,
    min_peak_distance_frames: int = 50,
    min_pair_duration_s: float = 0.0,
    max_pair_duration_s: Optional[float] = None,
    peak_both_signs: bool = False,
) -> np.ndarray:
    """Findpeaks and form grip→deposit pairs.

    Default (``axis_index=1``, ``pair_axis_index=None``) peaks on ``-Y`` and
    keeps consecutive peaks whose **peak-axis** value differs by more than
    ``pair_threshold_m`` (MATLAB adjacent-peak rule).

    For lateral BC transfers keep ``axis_index=1`` (vertical peaks) and set
    ``pair_axis_index=0`` so the gate is global-X travel (e.g. 0.3 m).
    ``peak_both_signs`` is only for rare X-extrema peaking, not the BC default.

    With ``min_pair_duration_s > 0``, after a grip the deposit is the first
    later peak that is far enough in time **and** passes the pair-axis
    threshold. ``max_pair_duration_s`` caps look-ahead.

    Returns
    -------
    pairs : (n_pairs, 2) int
        Frame indices ``[grip_or_start, deposit_or_end]`` for each transfer.
    """
    xyz = np.asarray(box_xyz, dtype=float)
    peak_ax = int(axis_index)
    metric_ax = peak_ax if pair_axis_index is None else int(pair_axis_index)
    dist = max(1, int(min_peak_distance_frames))

    if peak_both_signs:
        hi, _ = find_peaks(xyz[:, peak_ax], distance=dist)
        lo, _ = find_peaks(-xyz[:, peak_ax], distance=dist)
        locs = np.sort(np.unique(np.concatenate([hi, lo])))
    else:
        # Historical default: peaks of -axis (Y → local height minima).
        locs, _ = find_peaks(-xyz[:, peak_ax], distance=dist)

    if len(locs) < 2:
        return np.zeros((0, 2), dtype=int)

    metric = xyz[:, metric_ax]
    use_duration = float(min_pair_duration_s) > 0.0 or max_pair_duration_s is not None
    if use_duration:
        if time is None:
            raise ValueError(
                "time is required when min_pair_duration_s or "
                "max_pair_duration_s is set"
            )
        t = np.asarray(time, dtype=float)
        if t.shape[0] <= int(np.max(locs)):
            raise ValueError("time length must cover all peak frame indices")

        pairs: List[Tuple[int, int]] = []
        i = 0
        n = len(locs)
        min_dur = float(min_pair_duration_s)
        max_dur = (
            None
            if max_pair_duration_s is None
            else float(max_pair_duration_s)
        )
        while i < n - 1:
            hit: Optional[int] = None
            for j in range(i + 1, n):
                dt = float(t[int(locs[j])] - t[int(locs[i])])
                if dt < min_dur:
                    continue
                if max_dur is not None and dt > max_dur:
                    break
                d_metric = abs(float(metric[int(locs[j])] - metric[int(locs[i])]))
                if d_metric >= float(pair_threshold_m):
                    hit = j
                    break
            if hit is not None:
                pairs.append((int(locs[i]), int(locs[hit])))
                i = hit
            else:
                i += 1
        if not pairs:
            return np.zeros((0, 2), dtype=int)
        return np.asarray(pairs, dtype=int)

    # Legacy adjacent pairing (MATLAB).
    pairs = []
    for i in range(len(locs) - 1):
        d_metric = abs(float(metric[int(locs[i + 1])] - metric[int(locs[i])]))
        if d_metric >= float(pair_threshold_m):
            pairs.append((int(locs[i]), int(locs[i + 1])))
    if not pairs:
        return np.zeros((0, 2), dtype=int)
    return np.asarray(pairs, dtype=int)


def split_abc_events(
    pairs: np.ndarray,
    time: np.ndarray,
    *,
    skip_first_n_cycles: int = 1,
    n_cycles: Optional[int] = None,
) -> pd.DataFrame:
    """Group consecutive event pairs into ABC cycles (6 events / cycle).

    Pair order within a cycle is assumed ``AB, BC, CA``.
    """
    if pairs.ndim != 2 or pairs.shape[1] != 2:
        raise ValueError("pairs must have shape (n_pairs, 2)")

    n_full = len(pairs) // 3
    if n_full == 0:
        return pd.DataFrame(
            columns=[
                "cycle", "phase", "seg_label",
                "grip_frame", "deposit_frame",
                "grip_time", "deposit_time", "duration",
            ]
        )

    start_cycle = max(0, int(skip_first_n_cycles))
    if n_cycles is None:
        use_cycles = list(range(start_cycle, n_full))
    else:
        use_cycles = list(range(start_cycle, min(n_full, start_cycle + int(n_cycles))))

    phases = ("AB", "BC", "CA")
    rows = []
    for c_idx in use_cycles:
        out_cycle = c_idx - start_cycle + 1  # 1-based after skip
        for p_i, phase in enumerate(phases):
            g, d = pairs[3 * c_idx + p_i]
            tg = float(time[g])
            td = float(time[d])
            rows.append(
                {
                    "cycle": out_cycle,
                    "phase": phase,
                    "seg_label": f"{out_cycle}{phase}",
                    "grip_frame": int(g),
                    "deposit_frame": int(d),
                    "grip_time": tg,
                    "deposit_time": td,
                    "duration": td - tg,
                }
            )
    return pd.DataFrame(rows)


def pairs_to_dataframe(pairs: np.ndarray, time: np.ndarray) -> pd.DataFrame:
    """Unlabeled grip/deposit table from frame-index pairs."""
    if pairs.size == 0:
        return pd.DataFrame(
            columns=[
                "grip_frame",
                "deposit_frame",
                "grip_time",
                "deposit_time",
                "duration",
            ]
        )
    rows = []
    t = np.asarray(time, dtype=float)
    for g, d in np.asarray(pairs, dtype=int):
        tg = float(t[int(g)])
        td = float(t[int(d)])
        rows.append(
            {
                "grip_frame": int(g),
                "deposit_frame": int(d),
                "grip_time": tg,
                "deposit_time": td,
                "duration": td - tg,
            }
        )
    return pd.DataFrame(rows)


def detect_abc_events_from_rigidbody(
    csv_path: str,
    *,
    skiprows: int = 7,
    pair_threshold_m: float = DEFAULT_PAIR_THRESHOLD_M,
    min_peak_distance_sec: float = 0.5,
    min_pair_duration_s: float = DEFAULT_MIN_PAIR_DURATION_S,
    max_pair_duration_s: Optional[float] = None,
    axis_index: int = 1,
    pair_axis_index: Optional[int] = None,
    peak_both_signs: bool = False,
    skip_first_n_cycles: int = 1,
    n_cycles: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, np.ndarray], np.ndarray]:
    """Full ABC event table from a rigid-body CSV.

    Returns ``(events_df, rigid_dict, pairs_all)``.
    """
    rigid = read_rigidbody_marker15(csv_path, skiprows=skiprows)
    time = rigid["time"]
    rigid["box_xyz"] = fill_rigidbody_gaps(rigid["box_xyz"], time, max_gap_s=0.5)
    ok, _qmsg = rigidbody_track_quality(rigid["box_xyz"])
    if not ok:
        empty = np.zeros((0, 2), dtype=int)
        events = split_abc_events(
            empty,
            time,
            skip_first_n_cycles=skip_first_n_cycles,
            n_cycles=n_cycles,
        )
        return events, rigid, empty

    xyz = np.asarray(rigid["box_xyz"], dtype=float).copy()
    for ax in range(xyz.shape[1]):
        col = xyz[:, ax]
        finite = np.isfinite(col)
        if np.all(finite) or not np.any(finite):
            continue
        xyz[:, ax] = np.interp(
            np.arange(len(col)), np.where(finite)[0], col[finite]
        )

    dt = float(np.median(np.diff(time))) if len(time) > 1 else 0.01
    dist = max(1, int(round(min_peak_distance_sec / max(dt, 1e-6))))
    pairs = detect_box_event_pairs(
        xyz,
        time=time,
        axis_index=axis_index,
        pair_axis_index=pair_axis_index,
        pair_threshold_m=pair_threshold_m,
        min_peak_distance_frames=dist,
        min_pair_duration_s=min_pair_duration_s,
        max_pair_duration_s=max_pair_duration_s,
        peak_both_signs=peak_both_signs,
    )
    events = split_abc_events(
        pairs,
        time,
        skip_first_n_cycles=skip_first_n_cycles,
        n_cycles=n_cycles,
    )
    return events, rigid, pairs
