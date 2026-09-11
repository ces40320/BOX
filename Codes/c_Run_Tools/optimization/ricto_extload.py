"""Assemble preRiCTO / postRiCTO ExtLoad MOT (sensorless hand columns)."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from . import ricto_config as cfg
from .ricto_io import mot_df_to_ext_dict, write_extload_mot, write_opensim_storage
from .ricto_optimize import rectangle_weight_curve, smooth_weight_curve


def _interp_cols(t_dst: np.ndarray, t_src: np.ndarray, y_src: np.ndarray) -> np.ndarray:
    return np.interp(t_dst, t_src, y_src)


def apply_weight_to_ehf(
    ehf: Dict[str, np.ndarray],
    weight: np.ndarray,
    t_weight: np.ndarray,
    t_out: np.ndarray,
) -> Dict[str, np.ndarray]:
    """Interpolate EHF + weight onto t_out and return weighted hand forces."""
    w = _interp_cols(t_out, t_weight, weight)
    out = {}
    for side in ("l", "r"):
        for ax in ("fx", "fy", "fz"):
            key = f"{ax}_{side}"
            raw = _interp_cols(t_out, ehf["time"], ehf[key])
            out[key] = w * raw
    out["w"] = w
    return out


def build_ricto_extload(
    heavyhand_mot_df: pd.DataFrame,
    ehf: Dict[str, np.ndarray],
    hands: Dict[str, np.ndarray],
    ric: Dict,
    *,
    mode: str = cfg.MODE_POST,
) -> Dict[str, np.ndarray]:
    """Build ExtLoad dict from HeavyHand template + kinematics EHF.

    - Ground plates 1–2: copied from HeavyHand (measured GRF).
    - Hand forces 3/4: w * f_est (all 3 axes). Mapping: 3=L, 4=R.
    - Hand points: BK hand COM (interpolated).
    - Hand torques: 0.
    MeasuredEHF is never used here.
    """
    if mode not in (cfg.MODE_PRE, cfg.MODE_POST, "pre", "post", "preRiCTO", "postRiCTO"):
        raise ValueError(f"mode must be pre/post, got {mode!r}")
    use_smooth = mode in (cfg.MODE_POST, "post", "postRiCTO")

    ext = mot_df_to_ext_dict(heavyhand_mot_df)
    t_out = ext["time"]
    t_ric = ric["time"]
    w_src = ric["smooth_w"] if use_smooth else ric["rect_w"]
    weighted = apply_weight_to_ehf(ehf, w_src, t_ric, t_out)

    # forces: 3=L, 4=R
    f3 = np.column_stack([weighted["fx_l"], weighted["fy_l"], weighted["fz_l"]])
    f4 = np.column_stack([weighted["fx_r"], weighted["fy_r"], weighted["fz_r"]])
    ext["f3"] = f3
    ext["f4"] = f4

    # COP from hand COM
    p_l = np.column_stack(
        [
            _interp_cols(t_out, hands["time"], hands["p_l"][:, 0]),
            _interp_cols(t_out, hands["time"], hands["p_l"][:, 1]),
            _interp_cols(t_out, hands["time"], hands["p_l"][:, 2]),
        ]
    )
    p_r = np.column_stack(
        [
            _interp_cols(t_out, hands["time"], hands["p_r"][:, 0]),
            _interp_cols(t_out, hands["time"], hands["p_r"][:, 1]),
            _interp_cols(t_out, hands["time"], hands["p_r"][:, 2]),
        ]
    )
    ext["p3"] = p_l
    ext["p4"] = p_r

    n = len(t_out)
    if cfg.FORCE_ZERO_HAND_TORQUE:
        ext["m3"] = np.zeros((n, 3), dtype=float)
        ext["m4"] = np.zeros((n, 3), dtype=float)

    return ext


def write_ricto_mot(
    out_path: str,
    heavyhand_mot_df: pd.DataFrame,
    heavyhand_meta: dict,
    ehf: Dict[str, np.ndarray],
    hands: Dict[str, np.ndarray],
    ric: Dict,
    *,
    mode: str = cfg.MODE_POST,
    prefer_template_meta: bool = True,
) -> str:
    """Write pre/post RiCTO MOT. Prefer template meta to keep OpenSim headers."""
    ext = build_ricto_extload(heavyhand_mot_df, ehf, hands, ric, mode=mode)

    if prefer_template_meta and heavyhand_meta:
        # Rebuild dataframe in the same column order as the template
        from .ricto_io import flatten_extload_columns

        flat = flatten_extload_columns(ext)
        cols = [c for c in heavyhand_mot_df.columns if c != "time"]
        data = {"time": ext["time"]}
        for c in cols:
            if c in flat:
                data[c] = flat[c]
            else:
                data[c] = heavyhand_mot_df[c].to_numpy(dtype=float)
        df = pd.DataFrame(data)
        write_opensim_storage(out_path, df, heavyhand_meta)
    else:
        write_extload_mot(out_path, ext)
    return out_path


def assert_no_measured_leak(
    ricto_df: pd.DataFrame,
    measured_df: Optional[pd.DataFrame],
    *,
    atol: float = 1e-6,
) -> Dict[str, bool]:
    """Sanity checks: hand torques ~0; hand forces not identical to MeasuredEHF."""
    checks = {}
    for c in (
        "hand_torque3_x",
        "hand_torque3_y",
        "hand_torque3_z",
        "hand_torque4_x",
        "hand_torque4_y",
        "hand_torque4_z",
    ):
        if c in ricto_df.columns:
            checks[f"{c}_is_zero"] = bool(np.allclose(ricto_df[c].to_numpy(), 0.0, atol=atol))
    if measured_df is not None:
        for c in (
            "hand_force3_vx",
            "hand_force3_vy",
            "hand_force3_vz",
            "hand_force4_vx",
            "hand_force4_vy",
            "hand_force4_vz",
        ):
            if c in ricto_df.columns and c in measured_df.columns:
                same = np.allclose(
                    ricto_df[c].to_numpy(dtype=float),
                    measured_df[c].to_numpy(dtype=float),
                    atol=1e-3,
                    rtol=1e-3,
                )
                checks[f"{c}_not_equal_measured"] = not same
    return checks
