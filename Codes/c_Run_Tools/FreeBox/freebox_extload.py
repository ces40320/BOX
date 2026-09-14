"""Write ExtLoad.mot for FreeBox (pipeline-compatible).

Policy:
- Template: HeavyHand MOT (GRF plates 1–2 kept).
- hand3 = left, hand4 = right (forces/points from allocation × RiCTO weight).
- Torques zero (vendor ExtForceGenAPP5 also writes zeros).
- No MeasuredEHF hand-column copy.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

_THIS = os.path.dirname(os.path.abspath(__file__))
_RUN_TOOLS = os.path.dirname(_THIS)
_CODES = os.path.dirname(_RUN_TOOLS)
for _p in (_CODES, _RUN_TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from optimization.ricto_io import (  # noqa: E402
    flatten_extload_columns,
    mot_df_to_ext_dict,
    write_opensim_storage,
)
from optimization.ricto_optimize import (  # noqa: E402
    rectangle_weight_curve,
    smooth_weight_curve,
)

try:
    from . import freebox_config as cfg
except ImportError:  # script / flat import path
    import freebox_config as cfg


def apply_ricto_gate(
    forces_l: np.ndarray,
    forces_r: np.ndarray,
    weight: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Multiply L/R hand forces by RiCTO contact weight."""
    w = np.asarray(weight, dtype=float).reshape(-1, 1)
    return np.asarray(forces_l, dtype=float) * w, np.asarray(forces_r, dtype=float) * w


def _interp_vec(t_dst: np.ndarray, t_src: np.ndarray, y: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    out = np.empty((len(t_dst), y.shape[1]), dtype=float)
    for j in range(y.shape[1]):
        out[:, j] = np.interp(t_dst, t_src, y[:, j])
    return out


def resolve_ricto_weight(
    t_out: np.ndarray,
    ric: Optional[Dict[str, Any]] = None,
    *,
    weight_mode: str = cfg.RICTO_WEIGHT_MODE,
    timeseries_df: Optional[pd.DataFrame] = None,
) -> np.ndarray:
    """Build weight on ``t_out`` from RiCTO dict, timeseries CSV, or params."""
    mode = weight_mode.lower().strip()
    if mode in ("smooth", "post", "postricto"):
        col = "w_smooth"
        use_smooth = True
    elif mode in ("rect", "pre", "prericto"):
        col = "w_rect"
        use_smooth = False
    else:
        raise ValueError(f"Unknown RiCTO weight mode: {weight_mode!r}")

    if timeseries_df is not None and col in timeseries_df.columns:
        return np.interp(
            t_out,
            timeseries_df["time"].to_numpy(dtype=float),
            timeseries_df[col].to_numpy(dtype=float),
        )

    if ric is None:
        raise ValueError("Need ric dict or timeseries_df for RiCTO weight")

    if "smooth_w" in ric and "rect_w" in ric and "time" in ric:
        src = ric["smooth_w"] if use_smooth else ric["rect_w"]
        return np.interp(t_out, np.asarray(ric["time"], float), np.asarray(src, float))

    # Reconstruct from parameters
    t1, d1, t2, d2 = (float(ric["t1"]), float(ric["d1"]), float(ric["t2"]), float(ric["d2"]))
    if use_smooth:
        return smooth_weight_curve(t_out, t1, d1, t2, d2)
    return rectangle_weight_curve(t_out, t1, d1, t2, d2)


def build_freebox_extload(
    heavyhand_mot_df: pd.DataFrame,
    alloc: Dict[str, np.ndarray],
    *,
    ric: Optional[Dict[str, Any]] = None,
    timeseries_df: Optional[pd.DataFrame] = None,
    weight_mode: str = cfg.RICTO_WEIGHT_MODE,
    zero_torque: bool = cfg.FORCE_ZERO_HAND_TORQUE,
) -> Dict[str, np.ndarray]:
    """Assemble ExtLoad dict: GRF from template + gated FreeBox hands."""
    ext = mot_df_to_ext_dict(heavyhand_mot_df)
    t_out = ext["time"]
    w = resolve_ricto_weight(
        t_out, ric, weight_mode=weight_mode, timeseries_df=timeseries_df
    )

    t_a = np.asarray(alloc["time"], dtype=float)
    f_l = _interp_vec(t_out, t_a, alloc["f_l"])
    f_r = _interp_vec(t_out, t_a, alloc["f_r"])
    p_l = _interp_vec(t_out, t_a, alloc["p_l"])
    p_r = _interp_vec(t_out, t_a, alloc["p_r"])
    f_l, f_r = apply_ricto_gate(f_l, f_r, w)

    ext["f3"] = f_l  # left
    ext["f4"] = f_r  # right
    ext["p3"] = p_l
    ext["p4"] = p_r
    n = len(t_out)
    if zero_torque:
        ext["m3"] = np.zeros((n, 3), dtype=float)
        ext["m4"] = np.zeros((n, 3), dtype=float)
    ext["ricto_weight"] = w
    return ext


def write_freebox_mot(
    out_path: str,
    heavyhand_mot_df: pd.DataFrame,
    heavyhand_meta: dict,
    alloc: Dict[str, np.ndarray],
    *,
    ric: Optional[Dict[str, Any]] = None,
    timeseries_df: Optional[pd.DataFrame] = None,
    weight_mode: str = cfg.RICTO_WEIGHT_MODE,
) -> str:
    """Write ``ExtLoad_FreeBox.mot`` using HeavyHand template headers."""
    ext = build_freebox_extload(
        heavyhand_mot_df,
        alloc,
        ric=ric,
        timeseries_df=timeseries_df,
        weight_mode=weight_mode,
    )
    flat = flatten_extload_columns(ext)
    cols = [c for c in heavyhand_mot_df.columns if c != "time"]
    data = {"time": ext["time"]}
    for c in cols:
        if c in flat:
            data[c] = flat[c]
        else:
            data[c] = heavyhand_mot_df[c].to_numpy(dtype=float)
    out_df = pd.DataFrame(data)
    write_opensim_storage(out_path, out_df, heavyhand_meta)
    return out_path


def assert_no_measured_leak(
    freebox_df: pd.DataFrame,
    measured_df: Optional[pd.DataFrame] = None,
    *,
    atol: float = 1e-6,
) -> Dict[str, bool]:
    """QC: FreeBox hand torques are zero; optional ≠ MeasuredEHF hands."""
    checks: Dict[str, bool] = {}
    for plate in (3, 4):
        for ax in ("x", "y", "z"):
            col = f"hand_torque{plate}_{ax}"
            if col in freebox_df.columns:
                checks[f"zero_{col}"] = bool(
                    np.allclose(freebox_df[col].to_numpy(dtype=float), 0.0, atol=atol)
                )
    if measured_df is not None:
        for plate in (3, 4):
            for ax in ("x", "y", "z"):
                col = f"hand_force{plate}_v{ax}"
                if col in freebox_df.columns and col in measured_df.columns:
                    same = np.allclose(
                        freebox_df[col].to_numpy(dtype=float),
                        measured_df[col].to_numpy(dtype=float),
                        atol=atol,
                    )
                    checks[f"not_copy_{col}"] = not same
    return checks
