"""Constrained L/R handle allocation (Approach-5 ExtForceGenAPP5).

Decision variables per frame (box frame)::

    x = [r_cop_x, r_cop_y, r_cop_z, l_cop_x, l_cop_y, l_cop_z,
         Fr_x, Fr_y, Fr_z, Fl_x, Fl_y, Fl_z]

Objective: ``||Fr||^2 + ||Fl||^2``
Equality: ``Fr + Fl = F_box``, ``rR×Fr + rL×Fl = M_box``
Bounds: COP near CAD handle centers (±COP_DELTA_XYZ), forces within ±FORCE_BOUND_N.

Hand forces applied to the *human* are ``-Fr``, ``-Fl`` (Newton III), then
rotated to ground for ExtLoad (our SETUP uses ground-expressed loads).
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize

try:
    from . import boxwrench_config as cfg
    from .boxwrench_kinematics import box_vector_to_ground
except ImportError:  # script / flat import path
    import boxwrench_config as cfg
    from boxwrench_kinematics import box_vector_to_ground


def moment_balance_residual(x: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Vendor NonlinearConst — r×F sum minus M."""
    ceq = np.zeros(3, dtype=float)
    ceq[0] = x[1] * x[8] - x[2] * x[7] + x[4] * x[11] - x[5] * x[10] - M[0]
    ceq[1] = x[2] * x[6] - x[0] * x[8] + x[5] * x[9] - x[3] * x[11] - M[1]
    ceq[2] = x[0] * x[7] - x[1] * x[6] + x[3] * x[10] - x[4] * x[9] - M[2]
    return ceq


def _bounds(
    *,
    handle_r: Sequence[float] = cfg.HANDLE_R_NOM,
    handle_l: Sequence[float] = cfg.HANDLE_L_NOM,
    d: float = cfg.COP_DELTA_XYZ,
    fmax: float = cfg.FORCE_BOUND_N,
) -> list[Tuple[float, float]]:
    hr = np.asarray(handle_r, dtype=float).reshape(3)
    hl = np.asarray(handle_l, dtype=float).reshape(3)
    lb = np.concatenate([hr - d, hl - d, -fmax * np.ones(6)])
    ub = np.concatenate([hr + d, hl + d, fmax * np.ones(6)])
    return list(zip(lb.tolist(), ub.tolist()))


def allocate_frame(
    F_box: np.ndarray,
    M_box: np.ndarray,
    *,
    handle_r: Sequence[float] = cfg.HANDLE_R_NOM,
    handle_l: Sequence[float] = cfg.HANDLE_L_NOM,
    d: float = cfg.COP_DELTA_XYZ,
    fmax: float = cfg.FORCE_BOUND_N,
    tol: float = cfg.ALLOC_TOL,
) -> Dict[str, np.ndarray]:
    """Solve one frame; returns COP and forces in box frame."""
    F = np.asarray(F_box, dtype=float).reshape(3)
    M = np.asarray(M_box, dtype=float).reshape(3)
    hr = np.asarray(handle_r, dtype=float).reshape(3)
    hl = np.asarray(handle_l, dtype=float).reshape(3)
    x0 = np.concatenate([hr, hl, 0.01 * np.ones(6)])

    def fun(x: np.ndarray) -> float:
        return float(x[6] ** 2 + x[7] ** 2 + x[8] ** 2 + x[9] ** 2 + x[10] ** 2 + x[11] ** 2)

    def force_eq(x: np.ndarray) -> np.ndarray:
        return np.array([x[6] + x[9] - F[0], x[7] + x[10] - F[1], x[8] + x[11] - F[2]])

    constraints = (
        {"type": "eq", "fun": force_eq},
        {"type": "eq", "fun": lambda x: moment_balance_residual(x, M)},
    )
    result = minimize(
        fun,
        x0,
        method="SLSQP",
        constraints=constraints,
        bounds=_bounds(handle_r=hr, handle_l=hl, d=d, fmax=fmax),
        options={"ftol": tol, "maxiter": cfg.ALLOC_MAXITER, "disp": False},
    )
    x = result.x
    return {
        "cop_r_box": x[0:3].copy(),
        "cop_l_box": x[3:6].copy(),
        "F_r_box": x[6:9].copy(),  # force ON box at right handle
        "F_l_box": x[9:12].copy(),
        "success": np.array([float(result.success)]),
        "cost": np.array([float(result.fun)]),
        "nit": np.array([float(getattr(result, "nit", 0))]),
    }


def allocate_hand_loads(
    wrench: Dict[str, np.ndarray],
    motion: Dict[str, np.ndarray],
    *,
    active_mask: Optional[np.ndarray] = None,
    handle_r: Sequence[float] = cfg.HANDLE_R_NOM,
    handle_l: Sequence[float] = cfg.HANDLE_L_NOM,
    d: float = cfg.COP_DELTA_XYZ,
    fmax: float = cfg.FORCE_BOUND_N,
    # Deprecated alias (ML half-width); ignored if handle_r/l given.
    handle_z: Optional[float] = None,
) -> Dict[str, np.ndarray]:
    """Allocate over time; outside ``active_mask`` forces/COP stay at rest defaults.

    Returns hand forces/points in **ground** frame (force on hand = −force on box).
    """
    if handle_z is not None:
        # Legacy vendor ±Z handles; prefer CAD handle_r/l.
        handle_r = (0.0, 0.0, -float(handle_z))
        handle_l = (0.0, 0.0, float(handle_z))

    hr = np.asarray(handle_r, dtype=float).reshape(3)
    hl = np.asarray(handle_l, dtype=float).reshape(3)

    t = np.asarray(wrench["time"], dtype=float)
    n = len(t)
    F_b = np.asarray(wrench["F_box"], dtype=float)
    M_b = np.asarray(wrench["M_box"], dtype=float)
    R = np.asarray(motion["R_b2g"], dtype=float)
    p_com = np.asarray(motion["pos_com_g"], dtype=float)

    if active_mask is None:
        active_mask = np.ones(n, dtype=bool)
    else:
        active_mask = np.asarray(active_mask, dtype=bool)
        if active_mask.shape != (n,):
            raise ValueError("active_mask shape mismatch")

    Fr_b = np.zeros((n, 3), dtype=float)
    Fl_b = np.zeros((n, 3), dtype=float)
    cr_b = np.tile(hr, (n, 1))
    cl_b = np.tile(hl, (n, 1))
    ok = np.zeros(n, dtype=bool)

    for i in np.where(active_mask)[0]:
        sol = allocate_frame(
            F_b[i], M_b[i], handle_r=hr, handle_l=hl, d=d, fmax=fmax
        )
        cr_b[i] = sol["cop_r_box"]
        cl_b[i] = sol["cop_l_box"]
        Fr_b[i] = sol["F_r_box"]
        Fl_b[i] = sol["F_l_box"]
        ok[i] = bool(sol["success"][0] > 0.5)

    # Force on hand (Newton III), box → ground
    f_r_g = box_vector_to_ground(-Fr_b, R)
    f_l_g = box_vector_to_ground(-Fl_b, R)
    p_r_g = p_com + box_vector_to_ground(cr_b, R)
    p_l_g = p_com + box_vector_to_ground(cl_b, R)

    return {
        "time": t,
        "f_r": f_r_g,
        "f_l": f_l_g,
        "p_r": p_r_g,
        "p_l": p_l_g,
        "F_r_box": Fr_b,
        "F_l_box": Fl_b,
        "cop_r_box": cr_b,
        "cop_l_box": cl_b,
        "success": ok,
        "n_active": np.array([int(active_mask.sum())]),
        "n_success": np.array([int(ok.sum())]),
    }
