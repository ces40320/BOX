# -*- coding: utf-8 -*-
"""Asymmetric ABC box-event detection from Motive rigid-body Marker1 / Marker5.

Port of the findpeaks pairing logic in
``SplitLiftingPhase_from_c3d.py`` / ``detect_box_event_pairs``, adapted so that
one cycle yields **6 events** (3 grip/deposit pairs → AB, BC, CA) instead of
the Symmetric Up/Down 4-event layout.

Marker source
-------------
``*_rigidbody.csv`` columns ``RigidBody:Marker1`` and ``RigidBody:Marker5``
(left/right box corners), vertical axis = Y (OpenSim / Motive Y-up).
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
    return {
        "time": time,
        "marker1": m1,
        "marker5": m5,
        "box_xyz": 0.5 * (m1 + m5),
    }


def detect_box_event_pairs(
    box_xyz: np.ndarray,
    *,
    axis_index: int = 1,
    pair_threshold_m: float = 0.05,
    min_peak_distance_frames: int = 50,
) -> np.ndarray:
    """Findpeaks on ``-Y`` and keep adjacent peaks whose height differs by > thr.

    Returns
    -------
    pairs : (n_pairs, 2) int
        Frame indices ``[grip_or_start, deposit_or_end]`` for each transfer.
    """
    signal = -np.asarray(box_xyz, dtype=float)[:, axis_index]
    locs, _ = find_peaks(signal, distance=max(1, int(min_peak_distance_frames)))
    if len(locs) < 2:
        return np.zeros((0, 2), dtype=int)

    pks = signal[locs]
    pairs: List[Tuple[int, int]] = []
    for i in range(len(pks) - 1):
        if abs(float(pks[i] - pks[i + 1])) > float(pair_threshold_m):
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


def detect_abc_events_from_rigidbody(
    csv_path: str,
    *,
    skiprows: int = 7,
    pair_threshold_m: float = 0.05,
    min_peak_distance_sec: float = 0.5,
    skip_first_n_cycles: int = 1,
    n_cycles: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, np.ndarray], np.ndarray]:
    """Full ABC event table from a rigid-body CSV.

    Returns ``(events_df, rigid_dict, pairs_all)``.
    """
    rigid = read_rigidbody_marker15(csv_path, skiprows=skiprows)
    time = rigid["time"]
    dt = float(np.median(np.diff(time))) if len(time) > 1 else 0.01
    dist = max(1, int(round(min_peak_distance_sec / max(dt, 1e-6))))
    pairs = detect_box_event_pairs(
        rigid["box_xyz"],
        pair_threshold_m=pair_threshold_m,
        min_peak_distance_frames=dist,
    )
    events = split_abc_events(
        pairs,
        time,
        skip_first_n_cycles=skip_first_n_cycles,
        n_cycles=n_cycles,
    )
    return events, rigid, pairs
