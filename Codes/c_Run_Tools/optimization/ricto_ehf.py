"""BK hand kinematics → acceleration → estimated EHF (3 axes)."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
from scipy.signal import butter, filtfilt

from . import ricto_config as cfg


def _butter_lowpass(data: np.ndarray, fs_hz: float, cutoff_hz: float, order: int) -> np.ndarray:
    if data.shape[0] < max(4 * order, 8) or cutoff_hz <= 0:
        return np.asarray(data, dtype=float).copy()
    nyq = 0.5 * fs_hz
    wn = min(cutoff_hz / nyq, 0.99)
    b, a = butter(order, wn, btype="low", analog=False)
    return filtfilt(b, a, data, axis=0)


def second_derivative(
    time_s: np.ndarray,
    pos: np.ndarray,
    *,
    lowpass_hz: float = cfg.ACC_LOWPASS_HZ,
    order: int = cfg.ACC_FILTER_ORDER,
) -> np.ndarray:
    """Numerical 2nd derivative of Nx3 positions (optional low-pass first)."""
    t = np.asarray(time_s, dtype=float)
    x = np.asarray(pos, dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    dt = float(np.median(np.diff(t)))
    if dt <= 0:
        raise ValueError("time must be strictly increasing")
    fs = 1.0 / dt
    xf = _butter_lowpass(x, fs, lowpass_hz, order)
    vel = np.gradient(xf, dt, axis=0)
    acc = np.gradient(vel, dt, axis=0)
    return acc


def extract_hand_pos(pos_df) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pull hand_r / hand_l XYZ from BK pos_global dataframe."""
    need = ["hand_r_X", "hand_r_Y", "hand_r_Z", "hand_l_X", "hand_l_Y", "hand_l_Z"]
    missing = [c for c in need if c not in pos_df.columns]
    if missing:
        raise KeyError(f"BK pos missing columns: {missing}")
    t = pos_df["time"].to_numpy(dtype=float)
    hr = np.column_stack([pos_df[c].to_numpy(dtype=float) for c in need[:3]])
    hl = np.column_stack([pos_df[c].to_numpy(dtype=float) for c in need[3:]])
    return t, hr, hl


def qc_acc_spikes(acc: np.ndarray, a_max: float = cfg.A_MAX_QC) -> Dict[str, int]:
    """Count |a| > a_max samples. Does not modify data."""
    a = np.asarray(acc, dtype=float)
    mask = np.abs(a) > a_max
    return {
        "n_samples": int(a.shape[0]),
        "n_spikes": int(mask.any(axis=1).sum()) if a.ndim == 2 else int(mask.sum()),
        "n_spike_elements": int(mask.sum()),
        "a_max_threshold": float(a_max),
    }


def estimate_ehf_from_acc(
    time_s: np.ndarray,
    hand_r_acc: np.ndarray,
    hand_l_acc: np.ndarray,
    box_mass_kg: float,
    *,
    alpha: float = cfg.MASS_SPLIT_ALPHA,
    gravity_y: float = cfg.GRAVITY_Y,
) -> Dict[str, np.ndarray]:
    """Newton II for each hand: f = -m_h (a - g_vec). No per-axis sign flips.

    Sign convention matches MeasuredEHF MOT (force of box on hand, ground frame):
    static hold → fy ≈ -m_h * |g|.
    """
    m_h = float(box_mass_kg) * float(alpha)
    g = np.array([0.0, gravity_y, 0.0], dtype=float)
    ar = np.asarray(hand_r_acc, dtype=float)
    al = np.asarray(hand_l_acc, dtype=float)
    # f = -m (a - g)  for each hand
    fr = -(m_h * (ar - g))
    fl = -(m_h * (al - g))
    return {
        "time": np.asarray(time_s, dtype=float),
        "fx_r": fr[:, 0],
        "fy_r": fr[:, 1],
        "fz_r": fr[:, 2],
        "fx_l": fl[:, 0],
        "fy_l": fl[:, 1],
        "fz_l": fl[:, 2],
        "f_r": fr,
        "f_l": fl,
        "m_hand": np.array([m_h], dtype=float),
    }


def ehf_from_bk_pos(
    pos_df,
    box_mass_kg: float,
    *,
    lowpass_hz: float = cfg.ACC_LOWPASS_HZ,
    a_max: float = cfg.A_MAX_QC,
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray], Dict]:
    """Full pipeline: BK pos → acc → EHF + hand COM positions + QC."""
    t, hr, hl = extract_hand_pos(pos_df)
    ar = second_derivative(t, hr, lowpass_hz=lowpass_hz)
    al = second_derivative(t, hl, lowpass_hz=lowpass_hz)
    qc = {
        "right": qc_acc_spikes(ar, a_max),
        "left": qc_acc_spikes(al, a_max),
    }
    if qc["right"]["n_spikes"] or qc["left"]["n_spikes"]:
        qc["warning"] = (
            f"|a|>{a_max} spikes: R={qc['right']['n_spikes']}, "
            f"L={qc['left']['n_spikes']} (despike OFF — not substituted)"
        )
    ehf = estimate_ehf_from_acc(t, ar, al, box_mass_kg)
    hands = {"time": t, "p_r": hr, "p_l": hl, "a_r": ar, "a_l": al}
    return ehf, hands, qc


def static_dummy_force(box_mass_kg: float, alpha: float = cfg.MASS_SPLIT_ALPHA) -> np.ndarray:
    """Expected static force on one hand: (0, -m_h*|g|, 0) with g_y < 0 → fy negative."""
    m_h = box_mass_kg * alpha
    a0 = np.zeros((1, 3), dtype=float)
    pack = estimate_ehf_from_acc(np.array([0.0]), a0, a0, box_mass_kg, alpha=alpha)
    return pack["f_r"][0]
