"""Box / handle / Motive marker geometry from CAD excel + repo ADDBOX.

Sources (do not invent):
- ``마커 위치로 각 손잡이 중앙 좌표 구하기.xlsx`` — SW mm → lab OpenSim;
  ``from Center to L/Rhandle`` → ``config_exp_settings.D3/D4`` (**Motive RB** frame: ML on **X**).
- ``마커셋 위치 조절.xlsx`` / workflow step 8 / ``b_Build_Model/ADDBOX.py`` —
  eight corners on half bodies; handles share X, separate on **Z** in **CAD body** frame.
- Motive ``*_rigidbody.csv`` — ``RigidBody:Marker1``…``Marker8`` (mapping below).

Frame note
----------
Physical ML half-width ≈ 0.160 m. Axis label depends on frame:

- **Motive RB / MeasuredEHF** (``D3/D4``): (±0.160, 0.016, 0) on **X**
- **OpenSim BOX / ADDBOX body** (STL import): (0, 0.016, ±0.160) on **Z**

FreeBox allocation on OpenSim box BK uses the CAD body-frame handles.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

# ── Motive RB local (MeasuredEHF) — excel "Transverse … in OpenSim" / D3/D4 ─
HANDLE_L_MOTIVE_M: Tuple[float, float, float] = (-0.16001, 0.0158, 0.00041)
HANDLE_R_MOTIVE_M: Tuple[float, float, float] = (0.16007, 0.0158, 0.00041)

# ── CAD / BOX body frame (ADDBOX handle joint vs marker-cloud center) ───────
# Workflow step 6 handle translations + weld map → relative to marker mean:
#   L ≈ (0, +0.0158, −0.162), R ≈ (0, +0.0158, +0.162)
HANDLE_L_FROM_CENTER_M: Tuple[float, float, float] = (0.0, 0.0158, -0.16001)
HANDLE_R_FROM_CENTER_M: Tuple[float, float, float] = (0.0, 0.0158, 0.16007)

HANDLE_Z_NOM: float = 0.5 * (
    abs(HANDLE_L_FROM_CENTER_M[2]) + abs(HANDLE_R_FROM_CENTER_M[2])
)  # ≈ 0.16004 m
HANDLE_X_NOM: float = HANDLE_Z_NOM  # alias: ML half-width (historical name)

# ── Corner markers on half bodies (OpenSim m) — ADDBOX / workflow step 8 ────
MARKERS_HALF_L: Dict[str, Tuple[float, float, float]] = {
    "LTA_BOX": (0.3496, 0.295, 0.01539),
    "LTP_BOX": (0.0704, 0.295, 0.01539),
    "LBA_BOX": (0.3496, 0.015, -0.01461),
    "LBP_BOX": (0.0704, 0.015, -0.01461),
}
MARKERS_HALF_R: Dict[str, Tuple[float, float, float]] = {
    "RTA_BOX": (0.3496, 0.295, 0.19312),
    "RTP_BOX": (0.0704, 0.295, 0.19312),
    "RBA_BOX": (0.3496, 0.015, 0.22312),
    "RBP_BOX": (0.0704, 0.015, 0.22312),
}

WELD_OFFSET_L_M: Tuple[float, float, float] = (0.210000, 0.113030, 0.206760)
WELD_OFFSET_R_M: Tuple[float, float, float] = (0.210000, 0.113030, 0.001760)

# Motive Marker1…8 → C3D / OpenSim labels (local offsets vs RB center match CAD).
MOTIVE_MARKER_TO_BOX: Dict[int, str] = {
    1: "LTA_BOX",
    2: "LTP_BOX",
    3: "LBA_BOX",
    4: "LBP_BOX",
    5: "RTA_BOX",
    6: "RTP_BOX",
    7: "RBA_BOX",
    8: "RBP_BOX",
}


def handle_centers_from_box_center(*, frame: str = "cad") -> Dict[str, np.ndarray]:
    """L/R handle points relative to box center.

    Parameters
    ----------
    frame
        ``cad`` → OpenSim BOX / ADDBOX body (±Z ML);
        ``motive`` → MeasuredEHF / rigid-body local (±X ML).
    """
    if frame == "cad":
        l, r = HANDLE_L_FROM_CENTER_M, HANDLE_R_FROM_CENTER_M
    elif frame == "motive":
        l, r = HANDLE_L_MOTIVE_M, HANDLE_R_MOTIVE_M
    else:
        raise ValueError(f"Unknown frame {frame!r}")
    return {"L": np.asarray(l, dtype=float), "R": np.asarray(r, dtype=float)}


def markers_in_left_half_frame() -> Dict[str, Tuple[float, float, float]]:
    """Express all eight corners in ``box_15kg_half_l`` frame (weld identity).

    When weld offsets coincide: ``p_left = p_right + (offset_L - offset_R)``.
    """
    d = tuple(float(WELD_OFFSET_L_M[i] - WELD_OFFSET_R_M[i]) for i in range(3))
    out = dict(MARKERS_HALF_L)
    for name, loc in MARKERS_HALF_R.items():
        out[name] = (loc[0] + d[0], loc[1] + d[1], loc[2] + d[2])
    return out


def solidworks_mm_to_opensim_m(x_mm: float, y_mm: float, z_mm: float) -> Tuple[float, float, float]:
    """Excel axis map: SW (X,Y,Z) → lab OpenSim (Z, Y, −X), mm→m."""
    return (z_mm / 1000.0, y_mm / 1000.0, -x_mm / 1000.0)
