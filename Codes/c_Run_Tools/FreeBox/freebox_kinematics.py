"""Box pose → COM wrench (Approach-5 / ExtForceGenAPP5 adapted).

Inputs (OpenSim Analyze on free-joint box model):
- BodyKinematics ``*_vel_global.sto``  → linear velocity of box
- BodyKinematics ``*_pos_global.sto``  → COM position + orientation (deg)
- StatesReporter ``*_states.sto``     → free-joint angular speeds

Net wrench (vendor formula, kept for fidelity):
- ``F = m (a - g)`` in ground, ``g = (0, GRAVITY_Y, 0)``
- ``M = (Ixx αx, Iyy αy, Izz αz)`` from ω differentiation (**no** ω×Iω;
  products of inertia ignored — same as ExtForceGenAPP5.py)

F is then expressed in the box frame via ``R^{-1} F_ground``.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

_THIS = os.path.dirname(os.path.abspath(__file__))
_RUN_TOOLS = os.path.dirname(_THIS)
_CODES = os.path.dirname(_RUN_TOOLS)
for _p in (_CODES, _RUN_TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from optimization.ricto_io import read_opensim_storage  # noqa: E402

try:
    from . import freebox_config as cfg
    from .freebox_inertia import principal_inertia_diag
    from .freebox_rotation import batch_rotmats, rotmat_from_bk_angles
except ImportError:  # script / flat import path
    import freebox_config as cfg
    from freebox_inertia import principal_inertia_diag
    from freebox_rotation import batch_rotmats, rotmat_from_bk_angles


def _pick_body_xyz_cols(columns: Sequence[str], *, kind: str) -> Tuple[str, str, str]:
    """Pick first body translation or orientation triad from BK columns."""
    cols = list(columns)
    lower = {c: c.lower() for c in cols}

    def _find(suffixes: Tuple[str, str, str]) -> Optional[Tuple[str, str, str]]:
        # Prefer names containing 'box' or 'load'
        preferred = [c for c in cols if ("box" in lower[c] or "load" in lower[c])]
        search = preferred + [c for c in cols if c not in preferred]
        for c in search:
            cl = lower[c]
            if cl.endswith(suffixes[0]) or cl.endswith("_" + suffixes[0]):
                # try build triad from stem
                for stem_end in suffixes:
                    pass
        # Pattern: ..._X, ..._Y, ..._Z or ..._Ox ...
        axes = {
            "pos": ("_x", "_y", "_z", "x", "y", "z"),
            "ori": ("_ox", "_oy", "_oz", "ox", "oy", "oz"),
            "vel": ("_vx", "_vy", "_vz", "vx", "vy", "vz"),
        }
        # Simpler OpenSim BK labels: body_X, body_Y, body_Z / body_Ox...
        if kind == "pos":
            cands = [c for c in cols if c.lower().endswith("_x") and "o" not in c.lower()[-3:]]
            # BodyKinematics: "BOX_X" or "Load_X"
            for c in cols:
                cl = c.lower()
                if cl.endswith("_x") and not cl.endswith("_ox") and "force" not in cl:
                    stem = c[:-2]
                    cy, cz = stem + "_Y", stem + "_Z"
                    # case variants
                    for yname, zname in (
                        (stem + "_Y", stem + "_Z"),
                        (stem + "_y", stem + "_z"),
                    ):
                        if yname in cols and zname in cols:
                            return c, yname, zname
        if kind == "ori":
            for c in cols:
                cl = c.lower()
                if cl.endswith("_ox"):
                    stem = c[:-3]
                    for yname, zname in (
                        (stem + "_Oy", stem + "_Oz"),
                        (stem + "_OY", stem + "_OZ"),
                        (stem + "_oy", stem + "_oz"),
                    ):
                        if yname in cols and zname in cols:
                            return c, yname, zname
        if kind == "vel":
            for c in cols:
                cl = c.lower()
                if cl.endswith("_vx") or (cl.endswith("_x") and "vel" in "".join(lower.values())):
                    pass
            # vel file uses same _X,_Y,_Z as pos for linear velocity
            for c in cols:
                cl = c.lower()
                if cl.endswith("_x") and not cl.endswith("_ox"):
                    stem = c[:-2]
                    for yname, zname in (
                        (stem + "_Y", stem + "_Z"),
                        (stem + "_y", stem + "_z"),
                    ):
                        if yname in cols and zname in cols:
                            return c, yname, zname
        return None

    found = _find(("x", "y", "z"))
    if found is None:
        raise KeyError(f"Cannot find {kind} XYZ columns in {list(columns)[:20]}...")
    return found


def _angular_speed_cols(df: pd.DataFrame) -> Tuple[str, str, str]:
    """StatesReporter free-joint speed columns (rx_u, ry_u, rz_u)."""
    cols = list(df.columns)
    # Prefer explicit rx_u / ry_u / rz_u
    for rx in cols:
        low = rx.lower()
        if low.endswith("rx_u") or low.endswith("/rx_u") or low.endswith("_rx_u"):
            stem = rx[: -len("rx_u")] if rx.lower().endswith("rx_u") else None
            # try siblings
            candidates = []
            for name in cols:
                nl = name.lower()
                if nl.endswith("ry_u"):
                    ry = name
                if nl.endswith("rz_u"):
                    rz = name
            rys = [c for c in cols if c.lower().endswith("ry_u")]
            rzs = [c for c in cols if c.lower().endswith("rz_u")]
            rxs = [c for c in cols if c.lower().endswith("rx_u")]
            if rxs and rys and rzs:
                return rxs[0], rys[0], rzs[0]
    # Vendor fallback: columns [2,4,6] after time — fragile; use even speed slots
    # time, q0, u0, q1, u1, q2, u2, ...
    if df.shape[1] >= 7:
        return df.columns[2], df.columns[4], df.columns[6]
    raise KeyError("Cannot locate angular speed columns in StatesReporter")


def compute_box_com_motion(
    *,
    bk_vel_path: str,
    bk_pos_path: str,
    states_path: str,
    rotation_mode: str = cfg.ROTATION_MODE,
) -> Dict[str, np.ndarray]:
    """Return time, COM pos/vel/acc, orientation, ω, α, R batch."""
    vel_df, _ = read_opensim_storage(bk_vel_path)
    pos_df, _ = read_opensim_storage(bk_pos_path)
    st_df, _ = read_opensim_storage(states_path)

    t = vel_df["time"].to_numpy(dtype=float)
    vx, vy, vz = _pick_body_xyz_cols(vel_df.columns, kind="vel")
    v = np.column_stack(
        [
            vel_df[vx].to_numpy(dtype=float),
            vel_df[vy].to_numpy(dtype=float),
            vel_df[vz].to_numpy(dtype=float),
        ]
    )
    # CubicSpline derivative (vendor)
    acc = np.column_stack([CubicSpline(t, v[:, i])(t, 1) for i in range(3)])

    px, py, pz = _pick_body_xyz_cols(pos_df.columns, kind="pos")
    ox, oy, oz = _pick_body_xyz_cols(pos_df.columns, kind="ori")
    # Align pos/ori onto vel time
    tp = pos_df["time"].to_numpy(dtype=float)
    pos = np.column_stack(
        [
            np.interp(t, tp, pos_df[px].to_numpy(dtype=float)),
            np.interp(t, tp, pos_df[py].to_numpy(dtype=float)),
            np.interp(t, tp, pos_df[pz].to_numpy(dtype=float)),
        ]
    )
    ori = np.column_stack(
        [
            np.interp(t, tp, pos_df[ox].to_numpy(dtype=float)),
            np.interp(t, tp, pos_df[oy].to_numpy(dtype=float)),
            np.interp(t, tp, pos_df[oz].to_numpy(dtype=float)),
        ]
    )
    R = batch_rotmats(ori, mode=rotation_mode)

    wx_c, wy_c, wz_c = _angular_speed_cols(st_df)
    ts = st_df["time"].to_numpy(dtype=float)
    w = np.column_stack(
        [
            np.interp(t, ts, st_df[wx_c].to_numpy(dtype=float)),
            np.interp(t, ts, st_df[wy_c].to_numpy(dtype=float)),
            np.interp(t, ts, st_df[wz_c].to_numpy(dtype=float)),
        ]
    )
    alpha = np.column_stack([CubicSpline(t, w[:, i])(t, 1) for i in range(3)])

    return {
        "time": t,
        "pos_com_g": pos,
        "vel_com_g": v,
        "acc_com_g": acc,
        "ori_deg": ori,
        "R_b2g": R,
        "omega": w,
        "alpha": alpha,
        "cols_vel": (vx, vy, vz),
        "cols_pos": (px, py, pz),
        "cols_ori": (ox, oy, oz),
        "cols_omega": (wx_c, wy_c, wz_c),
    }


def compute_box_net_wrench(
    motion: Dict[str, np.ndarray],
    props: Dict[str, float],
    *,
    gravity_y: float = cfg.GRAVITY_Y,
) -> Dict[str, np.ndarray]:
    """Newton–Euler net force/moment (vendor diagonal-I simplification)."""
    m = float(props["mass"])
    Ixx, Iyy, Izz = principal_inertia_diag(props)
    a = np.asarray(motion["acc_com_g"], dtype=float)
    g = np.array([0.0, gravity_y, 0.0], dtype=float)
    # Vendor: Fx=m*ax, Fy=m*(ay - g) with g=-9.8066 → F = m (a - g_vec)
    F_g = m * (a - g)

    alpha = np.asarray(motion["alpha"], dtype=float)
    # FIXME: missing ω×(Iω); products of inertia ignored (vendor fidelity).
    M = np.column_stack([Ixx * alpha[:, 0], Iyy * alpha[:, 1], Izz * alpha[:, 2]])

    R = np.asarray(motion["R_b2g"], dtype=float)
    n = F_g.shape[0]
    F_b = np.empty_like(F_g)
    for i in range(n):
        F_b[i] = np.linalg.inv(R[i]) @ F_g[i]

    return {
        "time": np.asarray(motion["time"], dtype=float),
        "F_ground": F_g,
        "F_box": F_b,
        "M_box": M,  # vendor treats M in same frame as NonlinearConst with box COP
        "mass": np.array([m], dtype=float),
        "I_diag": np.array([Ixx, Iyy, Izz], dtype=float),
    }


def ground_force_to_box(F_ground: np.ndarray, R_b2g: np.ndarray) -> np.ndarray:
    n = len(F_ground)
    out = np.empty_like(F_ground)
    for i in range(n):
        out[i] = np.linalg.inv(R_b2g[i]) @ F_ground[i]
    return out


def box_vector_to_ground(v_box: np.ndarray, R_b2g: np.ndarray) -> np.ndarray:
    n = len(v_box)
    out = np.empty_like(v_box)
    for i in range(n):
        out[i] = R_b2g[i] @ v_box[i]
    return out
