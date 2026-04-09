"""
Utilities for lifting preprocessing I/O and force assembly.

This module keeps file I/O and per-frame assembly logic in one place so
protocol-specific segmentation modules can stay focused on window selection.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import csv
import os

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, find_peaks


def euler_to_rotation_matrix(
    rot_x_deg: float,
    rot_y_deg: float,
    rot_z_deg: float,
) -> np.ndarray:
    """Build rotation matrix from XYZ Euler angles (degrees)."""
    x = np.deg2rad(rot_x_deg)
    y = np.deg2rad(rot_y_deg)
    z = np.deg2rad(rot_z_deg)

    rx = np.array(
        [[1.0, 0.0, 0.0], [0.0, np.cos(x), -np.sin(x)], [0.0, np.sin(x), np.cos(x)]],
        dtype=float,
    )
    ry = np.array(
        [[np.cos(y), 0.0, np.sin(y)], [0.0, 1.0, 0.0], [-np.sin(y), 0.0, np.cos(y)]],
        dtype=float,
    )
    rz = np.array(
        [[np.cos(z), -np.sin(z), 0.0], [np.sin(z), np.cos(z), 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    return rz @ (ry @ rx)


def _axis_rotation(axis: str, degree: float) -> np.ndarray:
    rad = np.deg2rad(degree)
    c = np.cos(rad)
    s = np.sin(rad)
    axis = axis.lower()
    if axis == "x":
        return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=float)
    if axis == "y":
        return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=float)
    if axis == "z":
        return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    raise ValueError(f"Unknown axis: {axis!r}")


def _rotation_from_sequence(
    rotations: Optional[Sequence[Tuple[str, float]]],
) -> np.ndarray:
    r_total = np.eye(3, dtype=float)
    if not rotations:
        return r_total
    for axis, degree in rotations:
        r_total = _axis_rotation(axis, degree) @ r_total
    return r_total


def _rotated_xyz(arr: np.ndarray, rotation_matrix: np.ndarray) -> np.ndarray:
    if arr.size == 0:
        return arr
    return arr @ rotation_matrix.T


def _opensim_import():
    try:
        import opensim as osim  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "opensim is required for C3D reading via C3DFileAdapter."
        ) from exc
    return osim


def _osim_table_to_dict(table) -> Dict[str, np.ndarray]:
    labels = [str(label) for label in table.getColumnLabels()]
    n_rows = int(table.getNumRows())
    n_cols = len(labels)
    data = np.zeros((n_rows, n_cols, 3), dtype=float)

    for row_idx in range(n_rows):
        row = table.getRowAtIndex(row_idx)
        for col_idx in range(n_cols):
            vec3 = row.get(col_idx)
            data[row_idx, col_idx, 0] = float(vec3.get(0))
            data[row_idx, col_idx, 1] = float(vec3.get(1))
            data[row_idx, col_idx, 2] = float(vec3.get(2))

    time = np.array([float(v) for v in table.getIndependentColumn()], dtype=float)
    out = {"time": time}
    for col_idx, label in enumerate(labels):
        out[label] = data[:, col_idx, :]
    return out


def read_c3d_markers(
    c3d_path: str,
    rotations: Optional[Sequence[Tuple[str, float]]] = None,
) -> Dict[str, np.ndarray]:
    """Read marker trajectories with OpenSim C3DFileAdapter."""
    osim = _opensim_import()
    adapter = osim.C3DFileAdapter()
    tables = adapter.read(c3d_path)
    marker_table = adapter.getMarkersTable(tables)
    markers = _osim_table_to_dict(marker_table)

    r = _rotation_from_sequence(rotations)
    for key, value in list(markers.items()):
        if key == "time":
            continue
        markers[key] = _rotated_xyz(value, r)
    return markers


def read_c3d_force_platforms(
    c3d_path: str,
    rotations: Optional[Sequence[Tuple[str, float]]] = None,
) -> Dict[str, np.ndarray]:
    """Read force plate channels and map to f/p/m arrays."""
    osim = _opensim_import()
    adapter = osim.C3DFileAdapter()
    tables = adapter.read(c3d_path)
    force_table = adapter.getForcesTable(tables)
    raw = _osim_table_to_dict(force_table)

    r = _rotation_from_sequence(rotations)
    out: Dict[str, np.ndarray] = {"time": raw["time"]}

    for label, value in raw.items():
        if label == "time":
            continue
        low = label.lower()
        if low.startswith("f"):
            prefix = "f"
        elif low.startswith("p"):
            prefix = "p"
        elif low.startswith("m"):
            prefix = "m"
        else:
            continue
        idx = "".join(ch for ch in low[1:] if ch.isdigit())
        if not idx:
            continue
        out[f"{prefix}{idx}"] = _rotated_xyz(value, r)
    return out


def butterworth_filter(
    data: np.ndarray,
    fs_hz: float,
    cutoff_hz: float,
    order: int = 4,
) -> np.ndarray:
    """Zero-phase low-pass Butterworth filter for NxC arrays."""
    if data.shape[0] < 4:
        return data.copy()
    nyquist = 0.5 * fs_hz
    wn = cutoff_hz / nyquist
    b, a = butter(order, wn, btype="low", analog=False)
    return filtfilt(b, a, data, axis=0)


def read_rigid_body_csv(
    csv_path: str,
    skiprow_num: int = 7,
) -> Dict[str, np.ndarray]:
    """Read rigid body CSV and return time/position/euler arrays."""
    df = pd.read_csv(csv_path, skiprows=skiprow_num)
    cols = {c.strip(): c for c in df.columns}

    def _pick(*cands: str) -> str:
        for c in cands:
            if c in cols:
                return cols[c]
        for c in df.columns:
            low = c.lower()
            if any(cand.lower() in low for cand in cands):
                return c
        raise KeyError(f"Missing expected rigid column: {cands}")

    t_col = _pick("Time", "Seconds")
    x_col = _pick("Position X", "Pos X", "X")
    y_col = _pick("Position Y", "Pos Y", "Y")
    z_col = _pick("Position Z", "Pos Z", "Z")
    rx_col = _pick("Rotation X", "Rot X")
    ry_col = _pick("Rotation Y", "Rot Y")
    rz_col = _pick("Rotation Z", "Rot Z")

    out = {
        "time": df[t_col].to_numpy(dtype=float),
        "center": np.stack(
            [
                df[x_col].to_numpy(dtype=float),
                df[y_col].to_numpy(dtype=float),
                df[z_col].to_numpy(dtype=float),
            ],
            axis=1,
        ),
        "euler_deg": np.stack(
            [
                df[rx_col].to_numpy(dtype=float),
                df[ry_col].to_numpy(dtype=float),
                df[rz_col].to_numpy(dtype=float),
            ],
            axis=1,
        ),
    }
    return out


def _match_rigid_length(rigid: Dict[str, np.ndarray], target_len: int) -> Dict[str, np.ndarray]:
    """Match rigid-body sequence length to force length."""
    n = rigid["center"].shape[0]
    if n == target_len:
        return rigid

    idx = np.linspace(0, n - 1, target_len)
    idx0 = np.floor(idx).astype(int)
    idx1 = np.minimum(idx0 + 1, n - 1)
    alpha = (idx - idx0)[:, None]

    center = (1.0 - alpha) * rigid["center"][idx0] + alpha * rigid["center"][idx1]
    euler = (1.0 - alpha) * rigid["euler_deg"][idx0] + alpha * rigid["euler_deg"][idx1]
    time = np.interp(np.arange(target_len), np.arange(n), rigid["time"])
    return {"time": time, "center": center, "euler_deg": euler}


def detect_box_event_pairs(
    markers: Dict[str, np.ndarray],
    left_marker: str,
    right_marker: str,
    pair_threshold: float,
    fs_hz: float = 100.0,
) -> List[Tuple[int, int]]:
    """
    Detect up/down event pairs from mean box Y trajectory.

    Returns list of (up_peak_idx, down_peak_idx) in marker sample index.
    """
    if left_marker not in markers or right_marker not in markers:
        raise KeyError(
            f"Missing box markers: {left_marker!r}, {right_marker!r}. "
            f"Available: {[k for k in markers.keys() if k != 'time']}"
        )

    y = 0.5 * (markers[left_marker][:, 1] + markers[right_marker][:, 1])    # mean of left and right box marker Y trajectory
    up_idx, _ =   find_peaks(  y, prominence=pair_threshold, distance=max(int(fs_hz * 0.4), 1))
    down_idx, _ = find_peaks( -y, prominence=pair_threshold, distance=max(int(fs_hz * 0.4), 1))

    pairs: List[Tuple[int, int]] = []
    d_ptr = 0
    for up in up_idx:
        while d_ptr < len(down_idx) and down_idx[d_ptr] <= up:
            d_ptr += 1
        if d_ptr < len(down_idx):
            pairs.append((int(up), int(down_idx[d_ptr])))
            d_ptr += 1
    return pairs


def _nan_to_zero(arr: np.ndarray) -> np.ndarray:
    out = arr.copy()
    out[~np.isfinite(out)] = 0.0
    return out


def write_trc(
    output_path: str,
    time_s: np.ndarray,
    markers_m: Dict[str, np.ndarray],
) -> None:
    """Write OpenSim-compatible TRC. Coordinates are saved in mm."""
    labels = [k for k in markers_m.keys() if k != "time"]
    n_frames = len(time_s)
    data_rate = 1.0 / np.mean(np.diff(time_s)) if n_frames > 1 else 100.0

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        f.write(f"PathFileType\t4\t(X/Y/Z)\t{os.path.basename(output_path)}\n")
        f.write(
            "DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\tOrigDataRate\tOrigDataStartFrame\tOrigNumFrames\n"
        )
        f.write(
            f"{data_rate:.6f}\t{data_rate:.6f}\t{n_frames}\t{len(labels)}\tmm\t{data_rate:.6f}\t1\t{n_frames}\n"
        )

        f.write("Frame#\tTime")
        for label in labels:
            if ":" in label:
                short = label.split(":")[-1]
                if short.startswith("Static_"):
                    short = short[len("Static_") :]
            else:
                short = label
            f.write(f"\t{short}\t\t")
        f.write("\n")

        f.write("\t")
        for i in range(len(labels)):
            f.write(f"\tX{i+1}\tY{i+1}\tZ{i+1}")
        f.write("\n")

        for i in range(n_frames):
            f.write(f"{i+1}\t{time_s[i]:.8f}")
            for label in labels:
                xyz_mm = markers_m[label][i] * 1000.0
                f.write(f"\t{xyz_mm[0]:.5f}\t{xyz_mm[1]:.5f}\t{xyz_mm[2]:.5f}")
            f.write("\n")


def write_mot(
    output_path: str,
    time_s: np.ndarray,
    columns: Dict[str, np.ndarray],
) -> None:
    """Write simple OpenSim MOT table."""
    names = list(columns.keys())
    arr = np.column_stack([time_s] + [columns[n] for n in names])

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        f.write(f"name {os.path.basename(output_path)}\n")
        f.write(f"nRows={arr.shape[0]}\n")
        f.write(f"nColumns={arr.shape[1]}\n")
        f.write("inDegrees=no\n")
        f.write("endheader\n")
        f.write("time\t" + "\t".join(names) + "\n")
        for row in arr:
            f.write("\t".join(f"{v:.8f}" for v in row) + "\n")


def _extract_fp(forces: Dict[str, np.ndarray], idx: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        _nan_to_zero(forces.get(f"f{idx}", np.zeros((len(forces["time"]), 3), dtype=float))),
        _nan_to_zero(forces.get(f"p{idx}", np.zeros((len(forces["time"]), 3), dtype=float))),
        _nan_to_zero(forces.get(f"m{idx}", np.zeros((len(forces["time"]), 3), dtype=float))),
    )


def transform_ExtLoad_MeasuredEHF(
    forces: Dict[str, np.ndarray],
    rigid: Dict[str, np.ndarray],
    cfg,
) -> Dict[str, np.ndarray]:
    """
    MeasuredEHF ExtLoad: hand load-cell force/moment/COP in global frame;
    ground reaction channels unchanged from force platform.
    """
    n = len(forces["time"])
    rigid_m = _match_rigid_length(rigid, n)

    f1, p1, m1 = _extract_fp(forces, 1)  # ground left
    f2, p2, m2 = _extract_fp(forces, 2)  # ground right
    f3_raw, p3_raw, m3_raw = _extract_fp(forces, 3)  # hand left
    f4_raw, p4_raw, m4_raw = _extract_fp(forces, 4)  # hand right

    sign_f3 = np.asarray(cfg.HAND3_FORCE_SIGN, dtype=float)
    sign_f4 = np.asarray(cfg.HAND4_FORCE_SIGN, dtype=float)
    sign_m3 = np.asarray(cfg.HAND3_MOMENT_SIGN, dtype=float)
    sign_m4 = np.asarray(cfg.HAND4_MOMENT_SIGN, dtype=float)
    sign_p3 = np.asarray(cfg.HAND3_COP_SIGN, dtype=float)
    sign_p4 = np.asarray(cfg.HAND4_COP_SIGN, dtype=float)

    p3_offset = np.asarray(cfg.P3_OFFSET_M, dtype=float)
    p4_offset = np.asarray(cfg.P4_OFFSET_M, dtype=float)
    d3_local = np.asarray(cfg.D3_CENTER_TO_HANDLE_M, dtype=float)
    d4_local = np.asarray(cfg.D4_CENTER_TO_HANDLE_M, dtype=float)

    force_threshold_n = float(cfg.FORCE_THRESHOLD_N)
    box_center = rigid_m["center"]
    euler_deg = rigid_m["euler_deg"]

    f3 = np.zeros_like(f3_raw)
    f4 = np.zeros_like(f4_raw)
    m3 = np.zeros_like(m3_raw)
    m4 = np.zeros_like(m4_raw)
    p3 = np.zeros_like(p3_raw)
    p4 = np.zeros_like(p4_raw)

    f3_signed = f3_raw * sign_f3
    f4_signed = f4_raw * sign_f4
    m3_signed = m3_raw * sign_m3
    m4_signed = m4_raw * sign_m4
    p3_signed = p3_raw * sign_p3
    p4_signed = p4_raw * sign_p4

    for t in range(n):
        r = euler_to_rotation_matrix(
            euler_deg[t, 0],
            euler_deg[t, 1],
            euler_deg[t, 2],
        )
        f3[t] = r @ f3_signed[t]
        f4[t] = r @ f4_signed[t]
        m3[t] = r @ m3_signed[t]
        m4[t] = r @ m4_signed[t]

        if abs(f3[t, 1]) < force_threshold_n:
            p3[t] = r @ d3_local + box_center[t]
        else:
            local_cop_3 = p3_signed[t] - p3_offset + d3_local
            p3[t] = r @ local_cop_3 + box_center[t]

        if abs(f4[t, 1]) < force_threshold_n:
            p4[t] = r @ d4_local + box_center[t]
        else:
            local_cop_4 = p4_signed[t] - p4_offset + d4_local
            p4[t] = r @ local_cop_4 + box_center[t]

    return {
        "time": forces["time"],
        "f1": f1,
        "p1": p1,
        "m1": m1,
        "f2": f2,
        "p2": p2,
        "m2": m2,
        "f3": _nan_to_zero(f3),
        "p3": _nan_to_zero(p3),
        "m3": _nan_to_zero(m3),
        "f4": _nan_to_zero(f4),
        "p4": _nan_to_zero(p4),
        "m4": _nan_to_zero(m4),
    }


def transform_ExtLoad_HeavyHand(forces: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """HeavyHand ExtLoad: ground reaction only; hand force/moment/COP zeroed."""
    n = len(forces["time"])
    z = np.zeros((n, 3), dtype=float)
    f1, p1, m1 = _extract_fp(forces, 1)
    f2, p2, m2 = _extract_fp(forces, 2)
    return {
        "time": forces["time"],
        "f1": f1,
        "p1": p1,
        "m1": m1,
        "f2": f2,
        "p2": p2,
        "m2": m2,
        "f3": z.copy(),
        "p3": z.copy(),
        "m3": z.copy(),
        "f4": z.copy(),
        "p4": z.copy(),
        "m4": z.copy(),
    }


def transform_ExtLoad_AddBox(
    forces: Dict[str, np.ndarray],
    markers: Dict[str, np.ndarray],
    cfg,
) -> Dict[str, np.ndarray]:
    """
    AddBox ExtLoad: hand COP from finger markers (interpolated to force rate);
    hand force/moment zero (same base as HeavyHand).
    """
    out = transform_ExtLoad_HeavyHand(forces)
    if cfg.LEFT_FINGER_MARKER not in markers or cfg.RIGHT_FINGER_MARKER not in markers:
        raise KeyError(
            "AddBox ExtLoad requires finger markers "
            f"{cfg.LEFT_FINGER_MARKER!r}/{cfg.RIGHT_FINGER_MARKER!r}."
        )

    time_f = forces["time"]
    time_m = markers["time"]
    left = markers[cfg.LEFT_FINGER_MARKER]
    right = markers[cfg.RIGHT_FINGER_MARKER]

    out["p3"] = np.column_stack(
        [
            np.interp(time_f, time_m, left[:, 0]),
            np.interp(time_f, time_m, left[:, 1]),
            np.interp(time_f, time_m, left[:, 2]),
        ]
    )
    out["p4"] = np.column_stack(
        [
            np.interp(time_f, time_m, right[:, 0]),
            np.interp(time_f, time_m, right[:, 1]),
            np.interp(time_f, time_m, right[:, 2]),
        ]
    )
    return out

