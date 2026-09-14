"""Rotation helpers for BoxWrench (do not import vendor RotMat at runtime).

Vendor ``_vendor/General/RotMat.py`` builds::

    R = Rx(x) @ Ry(y) @ Rz(z)   with angles in degrees

OpenSim BodyKinematics orientation is typically **body-fixed XYZ** angles
(degrees). Body-fixed XYZ composition is the same product ``Rx@Ry@Rz``, so
the vendor formula is *plausible* — but column order / sign still need
empirical checks against OpenSim ``Rotation``.

ASSUMPTION: ``R`` maps **box-body → ground** (``v_g = R @ v_b``).
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def _rx(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=float)


def _ry(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=float)


def _rz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)


def rotmat_body_fixed_xyz_deg(ox: float, oy: float, oz: float) -> np.ndarray:
    """Same composition as vendor RotMat (degrees → radians, Rx@Ry@Rz)."""
    return _rx(math.radians(ox)) @ _ry(math.radians(oy)) @ _rz(math.radians(oz))


def rotmat_from_bk_angles(
    angles_deg: Sequence[float],
    *,
    mode: str = "body_fixed_xyz_deg",
) -> np.ndarray:
    ox, oy, oz = (float(angles_deg[0]), float(angles_deg[1]), float(angles_deg[2]))
    if mode == "body_fixed_xyz_deg":
        return rotmat_body_fixed_xyz_deg(ox, oy, oz)
    raise ValueError(f"Unknown rotation mode: {mode!r}")


def batch_rotmats(ori_deg: np.ndarray, *, mode: str = "body_fixed_xyz_deg") -> np.ndarray:
    """``ori_deg`` (N,3) → ``R`` (N,3,3)."""
    ori = np.asarray(ori_deg, dtype=float)
    n = ori.shape[0]
    out = np.empty((n, 3, 3), dtype=float)
    for i in range(n):
        out[i] = rotmat_from_bk_angles(ori[i], mode=mode)
    return out
