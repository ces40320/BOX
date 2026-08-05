# -*- coding: utf-8 -*-
"""
ricto_core.py — RiCTO (Residual-informed Contact Transition Optimization)

Correction algorithm for estimating lumbar (L5/S1) loading during two-handed
box lifting **without measuring the external hand force**.

Background
----------
When the external hand force (EHF) is reconstructed from hand acceleration,
the load transfer at grip and release becomes a rectangular (step-like) change.
That discontinuity drives excessive muscle co-contraction in static optimization
and substantially over-estimates the resulting L5/S1 joint load.

RiCTO estimates the contact transition timing and width from the vertical
residual (`residual_pelvis_ty`) of a model driven by ground reaction forces only,
and applies a smoothstep weighting to the reconstructed vertical hand force so
that the transition is continuous.

Algorithm components
--------------------
1. Transition weighting   smoothstep_ramp / smooth_weight_curve / rectangle_weight_curve
2. Force reconstruction   reconstruct_hand_force   (hand acceleration x box mass)
3. Transition estimation  optimize_transition      (residual-driven, no load cell)
4. External-load update   apply_correction         (vertical hand components only)
5. Per-segment driver     correct_segment

Design constraints
------------------
- Measured hand force is never used by the optimization. The inputs are the
  static-optimization vertical residual, hand acceleration, and box mass.
- Only the vertical hand force (fy) is modified. Ground reaction forces,
  horizontal hand forces, moments and CoP are left untouched.
- No constant is tied to a particular segment duration
  (e.g. 6.0 s at 10 bpm, 3.75 s at 16 bpm).

Example
-------
    from Algorithms.ricto_core import correct_segment

    result = correct_segment(
        residual_time=so_time, residual=so_residual_pelvis_ty,
        acc_time=bk_time, hand_r_acc=acc_r, hand_l_acc=acc_l,
        box_mass_kg=15.0,
        ext_time=mot_time, ext_data=mot_array, col_index=mot_columns,
    )
    corrected = result['corrected']      # RiCTO applied
    baseline  = result['rectangular']    # uncorrected reference
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter
from scipy.optimize import minimize

__all__ = [
    'smoothstep_ramp', 'smooth_weight_curve', 'rectangle_weight_curve',
    'despike_acceleration', 'reconstruct_hand_force',
    'optimize_transition', 'apply_correction', 'correct_segment',
]

GRAVITY_Y = -9.8066          # OpenSim default gravity, Y-up [m/s^2]

# Optimization bounds and numerical guards
_MIN_RAMP_S = 0.05           # lower bound of transition width [s]
_MAX_RAMP_S = 0.60           # upper bound of transition width [s]
_MIN_CONTACT_S = 0.30        # minimum contact duration [s]
_EDGE_MARGIN_S = 0.02        # margin from segment boundaries [s]
_BASELINE_MIN_N = 10.0       # lower bound for the baseline estimate [N]
_CONTACT_RATIO = 0.40        # idle if residual < baseline * this ratio
_MEDIAN_WIN_S = 0.10         # median-filter window for the residual [s]
_TOP_FRACTION = 0.30         # upper fraction used for the baseline estimate
_RESIDUAL_CAP_K = 5.0        # objective clip = max(K*|baseline|, 500 N)
_ACC_SPIKE_LIMIT = 30.0      # hand-acceleration spike threshold [m/s^2]
_ACC_MEDIAN_WIN = 21         # median window for spike replacement [frames]


# =============================================================================
# 1. Transition weighting
# =============================================================================
def smoothstep_ramp(t, t_start: float, duration: float) -> np.ndarray:
    """Cubic Hermite ramp rising from 0 to 1 over `duration` starting at `t_start`.

    S(tau) = 3*tau^2 - 2*tau^3, with tau = clip((t - t_start)/duration, 0, 1).
    The first derivative vanishes at both ends, so the load change is smooth.
    A very small duration degenerates to a step function.
    """
    t = np.asarray(t, dtype=float)
    if duration < 0.01:
        return np.where(t >= t_start, 1.0, 0.0)
    tau = np.clip((t - t_start) / duration, 0.0, 1.0)
    return 3.0 * tau ** 2 - 2.0 * tau ** 3


def smooth_weight_curve(t, t1: float, d1: float, t2: float, d2: float) -> np.ndarray:
    """Contact weighting curve: ramp up at grip, ramp down at release.

    Parameters
    ----------
    t1, d1 : onset and width of the grip transition [s]
    t2, d2 : onset and width of the release transition [s]

    Returns
    -------
    ndarray : 1 while the box is held, 0 otherwise, smooth in between.
    """
    return np.clip(smoothstep_ramp(t, t1, d1) - smoothstep_ramp(t, t2, d2), 0.0, 1.0)


def rectangle_weight_curve(t, t1: float, d1: float, t2: float, d2: float) -> np.ndarray:
    """Uncorrected rectangular weighting used as the comparison baseline.

    Equals 1 on [t1, t2 + d2] and 0 elsewhere, i.e. a discontinuous transition.
    """
    t = np.asarray(t, dtype=float)
    return np.where((t >= t1) & (t <= t2 + d2), 1.0, 0.0)


# =============================================================================
# 2. Hand force reconstruction
# =============================================================================
def despike_acceleration(acc: np.ndarray,
                         limit: float = _ACC_SPIKE_LIMIT,
                         window: int = _ACC_MEDIAN_WIN) -> np.ndarray:
    """Replace isolated hand-acceleration spikes with a local median.

    Hand acceleration is the second derivative of marker position, so marker
    noise is strongly amplified. Only samples exceeding `limit`
    (default 30 m/s^2, about 3 g) are replaced, preserving the bandwidth of the
    actual movement.
    """
    acc = np.asarray(acc, dtype=float)
    smoothed = median_filter(acc, size=(window, 1), mode='nearest')
    out = acc.copy()
    mask = np.abs(acc) > limit
    out[mask] = smoothed[mask]
    return out


def reconstruct_hand_force(time, hand_r_acc, hand_l_acc, box_mass_kg: float,
                           gravity_y: float = GRAVITY_Y,
                           despike: bool = True) -> dict:
    """Reconstruct the external hand force from hand acceleration (no load cell).

    The box mass is split evenly between the hands and Newton's second law is
    applied per hand. The vertical component includes gravity:
        fy = -m * (a_y - g)

    Parameters
    ----------
    time : (N,) time vector
    hand_r_acc, hand_l_acc : (N, 3) global hand acceleration [m/s^2]
    box_mass_kg : box mass [kg]

    Returns
    -------
    dict : time, fx_r/fx_l, fy_r/fy_l, fz_r/fz_l following the OpenSim
           external-load sign convention.
    """
    r = np.asarray(hand_r_acc, dtype=float)
    l = np.asarray(hand_l_acc, dtype=float)
    if despike:
        r, l = despike_acceleration(r), despike_acceleration(l)

    m = box_mass_kg / 2.0
    return {
        'time': np.asarray(time, dtype=float),
        'fx_r': -(m * r[:, 0]),  'fx_l': +(m * l[:, 0]),
        'fy_r': -(m * (r[:, 1] - gravity_y)),
        'fy_l': -(m * (l[:, 1] - gravity_y)),
        'fz_r': +(m * r[:, 2]),  'fz_l': +(m * l[:, 2]),
    }


# =============================================================================
# 3. Transition estimation (core of the algorithm)
# =============================================================================
def _estimate_baseline(residual_filtered: np.ndarray) -> float:
    """Estimate the residual level while the box is held (upper-quantile mean).

    The beginning of a segment is not guaranteed to be contact-free, so the mean
    of the upper 30 % is used instead of an initial-window mean. This is robust
    to outliers and to partially loaded segments.
    """
    ordered = np.sort(residual_filtered)
    n_top = max(5, int(round(_TOP_FRACTION * ordered.size)))
    baseline = float(np.mean(ordered[-n_top:]))
    if baseline < _BASELINE_MIN_N:
        baseline = max(_BASELINE_MIN_N, float(np.max(residual_filtered)))
    return baseline


def _initial_contact_guess(time: np.ndarray, residual_filtered: np.ndarray,
                           baseline: float) -> tuple[float, float]:
    """Take low-residual spans as contact-free and use the longest contact span
    between them as the initial guess."""
    idle = residual_filtered < _CONTACT_RATIO * baseline
    edges = np.diff(idle.astype(int), prepend=0, append=0)
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]

    best_start, best_end, best_len = 0, 0, 0.0
    for s, e in zip(starts, ends):
        e = min(e, time.size - 1)
        if time[e] - time[s] > best_len:
            best_start, best_end, best_len = s, e, time[e] - time[s]

    if best_len >= _MIN_CONTACT_S:
        return float(time[best_start]), float(time[best_end])
    span = float(time[-1])
    return 0.25 * span, 0.75 * span          # fallback if detection fails


def optimize_transition(time, residual, max_iter: int = 20000) -> dict:
    """Estimate the contact transition parameters (t1, d1, t2, d2) from the
    static-optimization vertical residual.

    If the weighting curve w(t) is correct, the residual drops by `baseline`
    while the box is not held. The parameters are therefore obtained by
    minimizing the squared difference `residual - baseline * (1 - w)`.
    The difference is clipped so that isolated outliers cannot dominate the fit.

    The measured hand force is not used anywhere in this function.

    Parameters
    ----------
    time : (N,) time relative to the start of the segment [s]
    residual : (N,) `residual_pelvis_ty` from static optimization [N]

    Returns
    -------
    dict : params (t1, d1, t2, d2), baseline, time, smooth_w, rect_w, cost, success
    """
    time = np.asarray(time, dtype=float)
    residual = np.asarray(residual, dtype=float)
    span = float(time[-1])
    dt = float(np.median(np.diff(time)))

    # Smooth the residual; force an odd window length
    win = max(3, int(round(_MEDIAN_WIN_S / dt)))
    win += (win % 2 == 0)
    residual_f = median_filter(residual, size=win, mode='nearest')

    baseline = _estimate_baseline(residual_f)
    t1_init, t2_init = _initial_contact_guess(time, residual_f, baseline)

    t1_lo, t1_hi = _EDGE_MARGIN_S, span - (_MIN_CONTACT_S + _EDGE_MARGIN_S * 4)
    t2_lo, t2_hi = t1_lo + _MIN_CONTACT_S, span - _EDGE_MARGIN_S
    cap = max(_RESIDUAL_CAP_K * abs(baseline), 500.0)

    def objective(p):
        t1, d1, t2, d2 = p
        if not (t1_lo <= t1 <= t1_hi):             return 1e9
        if not (t2_lo <= t2 <= t2_hi):             return 1e9
        if not (_MIN_RAMP_S <= d1 <= _MAX_RAMP_S): return 1e9
        if not (_MIN_RAMP_S <= d2 <= _MAX_RAMP_S): return 1e9
        if t1 + d1 >= t2:                          return 1e9
        w = smooth_weight_curve(time, t1, d1, t2, d2)
        diff = residual_f - baseline * (1.0 - w)
        return float(np.sum(np.clip(diff, -cap, cap) ** 2))

    result = minimize(objective, np.array([t1_init, 0.20, t2_init, 0.20]),
                      method='Nelder-Mead',
                      options={'maxiter': max_iter, 'xatol': 1e-6, 'fatol': 1e-7})

    t1, d1, t2, d2 = result.x.astype(float)
    t1 = float(np.clip(t1, t1_lo, t1_hi))
    t2 = float(np.clip(t2, t2_lo, t2_hi))
    d1 = float(np.clip(d1, _MIN_RAMP_S, _MAX_RAMP_S))
    d2 = float(np.clip(d2, _MIN_RAMP_S, _MAX_RAMP_S))

    return {
        'params': np.array([t1, d1, t2, d2]),
        'baseline': baseline,
        'time': time,
        'smooth_w': smooth_weight_curve(time, t1, d1, t2, d2),
        'rect_w': rectangle_weight_curve(time, t1, d1, t2, d2),
        'cost': float(result.fun),
        'success': bool(result.success),
    }


# =============================================================================
# 4. External-load update
# =============================================================================
def apply_correction(ext_time, ext_data, col_index, hand_force, transition,
                     mode: str = 'smooth',
                     left_column: str = 'hand_force3_vy',
                     right_column: str = 'hand_force4_vy') -> np.ndarray:
    """Replace only the vertical hand-force columns of an external-load array.

    Ground reaction forces, horizontal hand forces, moments and CoP are kept.

    Parameters
    ----------
    ext_time : (M,) time vector of the external-load file
    ext_data : (M, C) external-load array
    col_index : mapping {column name: index}
    hand_force : output of `reconstruct_hand_force`
    transition : output of `optimize_transition`
    mode : 'smooth' for the RiCTO correction, 'rect' for the rectangular baseline
    left_column, right_column : vertical force column names for each hand

    Returns
    -------
    ndarray : (M, C) copy with the vertical hand components replaced.
    """
    if mode not in ('smooth', 'rect'):
        raise ValueError("mode must be 'smooth' or 'rect'")

    ext_time = np.asarray(ext_time, dtype=float)
    t_rel = ext_time - ext_time[0]
    weight_key = 'smooth_w' if mode == 'smooth' else 'rect_w'

    w = np.interp(t_rel, transition['time'], transition[weight_key])
    fy_l = np.interp(t_rel, hand_force['time'], hand_force['fy_l'])
    fy_r = np.interp(t_rel, hand_force['time'], hand_force['fy_r'])

    out = np.array(ext_data, dtype=float, copy=True)
    out[:, col_index[left_column]] = w * fy_l
    out[:, col_index[right_column]] = w * fy_r
    return out


# =============================================================================
# 5. Per-segment driver
# =============================================================================
def correct_segment(residual_time, residual,
                    acc_time, hand_r_acc, hand_l_acc, box_mass_kg,
                    ext_time, ext_data, col_index,
                    left_column: str = 'hand_force3_vy',
                    right_column: str = 'hand_force4_vy') -> dict:
    """Apply RiCTO to a single lifting segment.

    Inputs (all obtainable without measuring the hand force)
    -------------------------------------------------------
    residual_time, residual : vertical static-optimization residual of a model
                              driven by ground reaction forces only
    acc_time, hand_r_acc, hand_l_acc : global hand acceleration
                              (second derivative of hand position)
    box_mass_kg : box mass
    ext_time, ext_data, col_index : external-load time vector, array and columns

    Returns
    -------
    dict
        transition   : estimated parameters and weighting curves
        hand_force   : reconstructed external hand force
        corrected    : external-load array with the RiCTO correction
        rectangular  : external-load array with the rectangular baseline
    """
    t = np.asarray(residual_time, dtype=float)
    transition = optimize_transition(t - t[0], residual)
    hand_force = reconstruct_hand_force(acc_time, hand_r_acc, hand_l_acc, box_mass_kg)

    kw = dict(left_column=left_column, right_column=right_column)
    return {
        'transition': transition,
        'hand_force': hand_force,
        'corrected': apply_correction(ext_time, ext_data, col_index,
                                      hand_force, transition, mode='smooth', **kw),
        'rectangular': apply_correction(ext_time, ext_data, col_index,
                                        hand_force, transition, mode='rect', **kw),
    }
